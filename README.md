# schemavcs

Version control for database schemas: branch, diff, and merge structure —
tables, columns, types, constraints, indexes. Row data is out of scope; the
artifact under version control is the schema itself.

Two ways to author a change, both feeding the same merge engine:

- **CLI verbs** — `schemavcs migrate rename-column users email contact_email`.
  Explicit, unambiguous, no guessing involved.
- **Edit the tracked schema file directly**, then run `schemavcs sync` — the
  tool diffs your edit and detects renames via similarity scoring, the way
  Django's `makemigrations` does for a single timeline.

See [`decisions.md`](decisions.md) for the reasoning behind every design
choice, and [`docs/walkthroughs/`](docs/walkthroughs/) for 16 real captured
terminal sessions covering every conflict shape the merge engine handles.

## Setup

Requires Python 3.11+ and [Poetry](https://python-poetry.org).

```
git clone <this repo>
cd DB-version-Control
poetry install
poetry run pytest        # 157 tests, should all pass
```

## Try it

```
poetry run schemavcs --repo /tmp/demo init
poetry run schemavcs --repo /tmp/demo migrate create-table users
poetry run schemavcs --repo /tmp/demo migrate add-column users email string
poetry run schemavcs --repo /tmp/demo branch create feature --from main
poetry run schemavcs --repo /tmp/demo migrate --branch feature rename-column users email contact_email
poetry run schemavcs --repo /tmp/demo checkout main
poetry run schemavcs --repo /tmp/demo merge feature --into main
poetry run schemavcs --repo /tmp/demo emit-ddl
```

Walk through `docs/walkthroughs/01-basics.md` for the same thing narrated, or
jump straight to `docs/walkthroughs/09-phase2-full-pipeline.md` for the full
detect → merge → emit pipeline.

## Development

```
poetry run pytest              # tests
poetry run ruff check .        # lint
poetry run ruff format .       # format
```

## Structure

Built in two phases — see `decisions.md` for why:

- **Phase 1**: CLI-authored migrations (explicit verbs, including
  `rename-column` — no rename ambiguity by construction) + a DAG of
  migration history + a three-way merge engine + DDL emission.
- **Phase 2**: adds a second authoring path — edit the tracked `.schema`
  file directly, run `sync` — with similarity-scored rename/retype
  detection, layered on Phase 1's unmodified merge engine.

```
src/schemavcs/
├── model/          core types: Table, Column, the Operation ADT
├── dag/            migration history as a DAG, merge-base, replay
├── merge/          classification, cross-object pass, human-confirmation guardrail
├── llm/            conflict-explainer interface (stub by default, model-agnostic)
├── ddl/            dependency ordering + SQL emission
├── dsl/            schema-file grammar (Lark) and parser
├── snapshot/       diffs a parsed schema file against tracked state
├── rename_detect/  similarity scoring + the rename-detection state machine
└── cli/            the schemavcs command
```
