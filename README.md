# schemavcs

Version control for database schemas: branch, diff, and merge structure (tables, columns,
types, constraints, indexes) — not row data.

See `/Users/hari_1/Personal/DB Tool/` for the design docs (`decisions.md`, `plan.md`, `todo.md`,
`considerations.md`) and `decision_log.md` in this repo for the running decision log.

Built in two phases:

- **Phase 1**: CLI-authored migrations (explicit verbs, including `rename-column` — no rename
  ambiguity) + DAG + three-way merge engine + DDL emission.
- **Phase 2**: adds a model-file diff path (edit a `.schema` file, run `generate-migration`) with
  similarity-scored rename/retype detection, layered on Phase 1's unmodified merge engine.

## Development

Uses [Poetry](https://python-poetry.org) for dependency management and local testing.

```
poetry install
poetry run pytest
poetry run ruff check .
poetry run ruff format .
```
