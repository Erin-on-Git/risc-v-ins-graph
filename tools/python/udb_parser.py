"""Load UnifiedDB YAML into seven queryable SQLite tables."""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML


def scalar(value: Any) -> str | None:
    return None if value is None else str(value)


def find_extension_name(value: Any) -> str | None:
    if isinstance(value, dict) and isinstance(value.get("extension"), dict):
        extension = value["extension"]
        return str(extension["name"]) if extension.get("name") else None
    return None


def requirement_rows(value: Any, path: str = "") -> list[tuple[str, str, str | None, str | None, str | None]]:
    rows = []
    if isinstance(value, dict):
        if value.get("name") is not None and any(operator in value for operator in ("version", "equal", "includes", "not_equal")):
            requirement_kind = "extension" if "extension" in path else "param"
            for operator in ("version", "equal", "includes", "not_equal"):
                if operator in value:
                    rows.append((path, requirement_kind, str(value["name"]), operator, scalar(value[operator])))
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else key
            if isinstance(child, dict) and child.get("name") is not None and any(operator in child for operator in ("version", "equal", "includes", "not_equal")):
                requirement_kind = "extension" if "extension" in path else key
                for operator in ("version", "equal", "includes", "not_equal"):
                    if operator in child:
                        rows.append((child_path, requirement_kind, str(child["name"]), operator, scalar(child[operator])))
            rows.extend(requirement_rows(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            rows.extend(requirement_rows(child, f"{path}[{index}]"))
    return rows


def load(source: Path, output: Path) -> int:
    yaml = YAML(typ="safe")
    output.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(output) as db:
        db.executescript(Path(__file__).with_name("schema.sql").read_text(encoding="utf-8"))
        documents = []
        for path in sorted(source.rglob("*.yaml")):
            data = yaml.load(path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get("kind") and data.get("name"):
                documents.append((path, data))

        extension_ids: dict[str, int] = {}
        for path, data in documents:
            if data["kind"] == "extension":
                cursor = db.execute(
                    "INSERT INTO extensions(name, type, long_name, description, source_path) VALUES (?, ?, ?, ?, ?)",
                    (data["name"], data.get("type"), data.get("long_name"), data.get("description"), path.relative_to(source).as_posix()),
                )
                extension_ids[str(data["name"])] = cursor.lastrowid

        profile_ids: dict[str, int] = {}
        for path, data in documents:
            kind = str(data["kind"])
            relative_path = path.relative_to(source).as_posix()
            if kind in {"profile", "profile family", "profile release"}:
                cursor = db.execute(
                    "INSERT INTO profiles(name, kind, long_name, mode, base, source_path) VALUES (?, ?, ?, ?, ?, ?)",
                    (data["name"], kind, data.get("long_name"), data.get("mode"), data.get("base"), relative_path),
                )
                profile_ids[relative_path] = cursor.lastrowid
            elif kind == "instruction":
                extension_name = find_extension_name(data.get("definedBy"))
                encoding = data.get("encoding") or {}
                db.execute(
                    "INSERT INTO instructions(name, extension_id, long_name, assembly, description, encoding_match, source_path) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (data["name"], extension_ids.get(extension_name), data.get("long_name"), data.get("assembly"), data.get("description"), encoding.get("match"), relative_path),
                )

        for path, data in documents:
            kind = str(data["kind"])
            if kind == "extension":
                extension_id = extension_ids[str(data["name"])]
                for version_index, version in enumerate(data.get("versions", [])):
                    if isinstance(version, dict) and version.get("version") is not None:
                        db.execute(
                            "INSERT INTO extension_versions(extension_id, version, state, ratification_date) VALUES (?, ?, ?, ?)",
                            (extension_id, str(version["version"]), version.get("state"), scalar(version.get("ratification_date"))),
                        )
                    for requirement_path, requirement_kind, required_name, operator, value in requirement_rows(version.get("requirements"), f"versions[{version_index}].requirements"):
                        insert_requirement(db, extension_id, requirement_path, requirement_kind, required_name, operator, value, extension_ids)
                for requirement_path, requirement_kind, required_name, operator, value in requirement_rows(data.get("requirements")):
                    insert_requirement(db, extension_id, requirement_path, requirement_kind, required_name, operator, value, extension_ids)

            elif kind in {"profile", "profile family", "profile release"}:
                profile_id = profile_ids[path.relative_to(source).as_posix()]
                for extension_name, details in (data.get("extensions") or {}).items():
                    if extension_name.startswith("$") or not isinstance(details, dict):
                        continue
                    db.execute(
                        "INSERT INTO profile_extensions VALUES (?, ?, ?, ?, ?, ?)",
                        (profile_id, extension_name, extension_ids.get(extension_name), scalar(details.get("presence")), scalar(details.get("version")), scalar(details.get("note"))),
                    )
        db.commit()
        return len(documents)


def insert_requirement(db: sqlite3.Connection, extension_id: int, requirement_path: str, requirement_kind: str, required_name: str | None, operator: str | None, value: str | None, extension_ids: dict[str, int]) -> None:
    db.execute(
        "INSERT OR IGNORE INTO extension_requirements(extension_id, requirement_path, requirement_kind, required_name, operator, value) VALUES (?, ?, ?, ?, ?, ?)",
        (extension_id, requirement_path, requirement_kind, required_name, operator, value),
    )
    requirement_id = db.execute(
        "SELECT extension_requirement_id FROM extension_requirements WHERE extension_id=? AND requirement_path=? AND required_name IS ? AND operator IS ? AND value IS ?",
        (extension_id, requirement_path, required_name, operator, value),
    ).fetchone()[0]
    if requirement_kind == "extension" and required_name in extension_ids:
        db.execute(
            "INSERT OR IGNORE INTO extension_dependencies VALUES (?, ?, ?)",
            (extension_id, extension_ids[required_name], requirement_id),
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    print(f"Loaded {load(args.source, args.output)} YAML documents into {args.output}")


if __name__ == "__main__":
    main()
