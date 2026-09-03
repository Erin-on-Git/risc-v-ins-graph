# UnifiedDB YAML to SQLite

`udb_parser.py` loads the official YAML documents from this repository into a
queryable SQLite database. Use the repository root as the source to include
both `spec/` and generated `cfgs/` documents:

```powershell
uv run python tools/python/udb_parser.py . data/riscv-unified.db
```

The generated database is intentionally not checked in. The normalized tables
include `extensions`, `instructions`, `csrs`, `versions`, `requirements`,
`defined_by`, `architecture_configurations`, and `configuration_extensions`.
`documents`, `document_values`, and `document_references` retain every scalar
field and YAML reference so new upstream kinds can be queried without changing
the loader. Rebuild the database after updating the official YAML checkout.