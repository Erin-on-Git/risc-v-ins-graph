"""REST API for the RISC-V Extension Dependency Graph Explorer."""

from __future__ import annotations

import json
import sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent.parent
DATABASE = ROOT / "data" / "riscv-unified.db"
FRONTEND = ROOT / "app" / "web"


def query(sql: str, parameters: tuple = ()) -> list[dict]:
    with sqlite3.connect(DATABASE) as connection:
        connection.row_factory = sqlite3.Row
        return [dict(row) for row in connection.execute(sql, parameters)]


def traced_query(sql: str, parameters: tuple = ()) -> tuple[list[dict], str]:
    statements: list[str] = []
    with sqlite3.connect(DATABASE) as connection:
        connection.row_factory = sqlite3.Row
        connection.set_trace_callback(statements.append)
        rows = [dict(row) for row in connection.execute(sql, parameters)]
    return rows, statements[-1] if statements else sql


def graph(search: str, extension_type: str, depth: int) -> dict:
    matching = query(
        "SELECT extension_id, name, type, long_name FROM extensions "
        "WHERE (? = '' OR name LIKE ? OR long_name LIKE ?) "
        "AND (? = 'all' OR type = ?) ORDER BY name",
        (search, f"%{search}%", f"%{search}%", extension_type, extension_type),
    )
    ids = {row["extension_id"] for row in matching}
    edges: set[tuple[int, int]] = set()
    frontier = set(ids)
    for _ in range(max(0, min(depth, 5))):
        if not frontier:
            break
        placeholders = ",".join("?" for _ in frontier)
        found = query(
            f"SELECT extension_id, depends_on_extension_id FROM extension_dependencies WHERE extension_id IN ({placeholders})",
            tuple(frontier),
        )
        next_frontier = set()
        for row in found:
            edges.add((row["extension_id"], row["depends_on_extension_id"]))
            next_frontier.add(row["depends_on_extension_id"])
        frontier = next_frontier - ids
        ids.update(frontier)
    if ids:
        placeholders = ",".join("?" for _ in ids)
        nodes = query(f"SELECT extension_id, name, type, long_name FROM extensions WHERE extension_id IN ({placeholders}) ORDER BY name", tuple(ids))
    else:
        nodes = []
    return {"nodes": nodes, "edges": [{"source": source, "target": target} for source, target in sorted(edges)]}


class Handler(BaseHTTPRequestHandler):
    def send_json(self, payload: object, status: int = 200) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        request = urlparse(self.path)
        params = parse_qs(request.query)
        try:
            if request.path == "/api/summary":
                tables = ["extensions", "profiles", "extension_dependencies", "extension_requirements", "instructions", "profile_extensions", "extension_versions"]
                self.send_json({"counts": {table: query(f"SELECT count(*) AS count FROM {table}")[0]["count"] for table in tables}})
            elif request.path == "/api/extensions":
                search = params.get("search", [""])[0]
                kind = params.get("type", ["all"])[0]
                self.send_json(query("SELECT extension_id, name, type, long_name FROM extensions WHERE (? = '' OR name LIKE ? OR long_name LIKE ?) AND (? = 'all' OR type = ?) ORDER BY name", (search, f"%{search}%", f"%{search}%", kind, kind)))
            elif request.path == "/api/graph":
                self.send_json(graph(params.get("search", [""])[0], params.get("type", ["all"])[0], int(params.get("depth", [1])[0])))
            elif request.path == "/api/matches":
                self.send_json(query("""
                    WITH dependency_counts AS (
                        SELECT extension_id, COUNT(*) AS count
                        FROM extension_dependencies GROUP BY extension_id
                    ), dependant_counts AS (
                        SELECT depends_on_extension_id AS extension_id, COUNT(*) AS count
                        FROM extension_dependencies GROUP BY depends_on_extension_id
                    )
                    SELECT e.name, dc.count AS dependencies, xc.count AS dependants
                    FROM extensions e
                    JOIN dependency_counts dc ON dc.extension_id = e.extension_id
                    JOIN dependant_counts xc ON xc.extension_id = e.extension_id
                    WHERE dc.count BETWEEN 4 AND 5 AND xc.count BETWEEN 2 AND 3
                    ORDER BY e.name
                """))
            elif request.path.startswith("/api/extensions/"):
                name = request.path.rsplit("/", 1)[-1]
                executed = []
                def detail_query(sql: str, parameters: tuple = ()) -> list[dict]:
                    rows, actual_sql = traced_query(sql, parameters)
                    executed.append({"sql": actual_sql})
                    return rows

                extension = detail_query("SELECT * FROM extensions WHERE name = ?", (name,))
                if not extension:
                    self.send_json({"error": "Extension not found"}, 404)
                    return
                extension_id = extension[0]["extension_id"]
                dependencies = detail_query("SELECT e.name, e.type, d.depends_on_extension_id FROM extension_dependencies d JOIN extensions e ON e.extension_id = d.depends_on_extension_id WHERE d.extension_id = ? ORDER BY e.name", (extension_id,))
                dependents = detail_query("SELECT e.name, e.type FROM extension_dependencies d JOIN extensions e ON e.extension_id = d.extension_id WHERE d.depends_on_extension_id = ? ORDER BY e.name", (extension_id,))
                versions = detail_query("SELECT version, state, ratification_date FROM extension_versions WHERE extension_id = ? ORDER BY version", (extension_id,))
                instructions = detail_query("SELECT name, long_name, assembly FROM instructions WHERE extension_id = ? ORDER BY name", (extension_id,))
                profiles = detail_query("SELECT p.name, pe.presence, pe.version_constraint FROM profile_extensions pe JOIN profiles p ON p.profile_id = pe.profile_id WHERE pe.extension_id = ? ORDER BY p.name", (extension_id,))
                self.send_json({
                    "extension": extension[0],
                    "versions": versions,
                    "dependencies": dependencies,
                    "dependents": dependents,
                    "instructions": instructions,
                    "profiles": profiles,
                    "queries": executed,
                })
            elif request.path == "/" or request.path == "/index.html":
                self.path = "/index.html"
                content = (FRONTEND / "index.html").read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)
            elif request.path in {"/app.js", "/styles.css"}:
                content = (FRONTEND / request.path[1:]).read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/javascript" if request.path.endswith("js") else "text/css")
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)
            else:
                self.send_json({"error": "Not found"}, 404)
        except (ValueError, sqlite3.Error) as error:
            self.send_json({"error": str(error)}, 500)

    def log_message(self, format: str, *args: object) -> None:
        print(format % args)


if __name__ == "__main__":
    import os

    port = int(os.environ.get("PORT", 8000))
    print(f"RISC-V graph explorer running on port {port}")
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
