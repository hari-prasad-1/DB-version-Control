# schemavcs

Version control for database schemas: branch, diff, and merge structure —
tables, columns, types, constraints, indexes. Row data is out of scope; the
artifact under version control is the schema itself.

**Live demo:** <REPLACE_WITH_DEPLOYED_URL>

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
poetry run pytest        # 188 tests, should all pass
```

## Run the web app locally

```
poetry run uvicorn schemavcs_web.app:app --reload
```

Open http://127.0.0.1:8000. Each browser session gets its own throwaway
repo (a temp directory, gone when the process exits) — create a table,
branch, diverge, merge, resolve conflicts, and view the emitted DDL, all in
the browser. This is a thin layer over the same engine the CLI drives —
see `decisions.md`'s entry on why a background-thread bridge was needed to
turn the engine's blocking confirm-callback loops into a click-by-click web
flow without touching the engine itself.

## Try the CLI

```
poetry run schemavcs --repo /tmp/demo init
poetry run schemavcs --repo /tmp/demo migrate create-table users
poetry run schemavcs --repo /tmp/demo migrate add-column users email string
poetry run schemavcs --repo /tmp/demo branch create feature --from main
poetry run schemavcs --repo /tmp/demo migrate --branch feature rename-column users email contact_email
poetry run schemavcs --repo /tmp/demo checkout main
poetry run schemavcs --repo /tmp/demo merge feature --into main
poetry run schemavcs --repo /tmp/demo emit-ddl

# undo the last migration on a branch (like git reset --hard HEAD^)
poetry run schemavcs --repo /tmp/demo branch rollback main --steps 1

# delete a branch -- its history stays reachable, the name is retired forever
poetry run schemavcs --repo /tmp/demo branch delete feature
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

Built in three phases — see `decisions.md` for why:

- **Phase 1**: CLI-authored migrations (explicit verbs, including
  `rename-column` — no rename ambiguity by construction) + a DAG of
  migration history + a three-way merge engine + DDL emission.
- **Phase 2**: adds a second authoring path — edit the tracked `.schema`
  file directly, run `sync` — with similarity-scored rename/retype
  detection, layered on Phase 1's unmodified merge engine.
- **Phase 3**: a thin web application over the unmodified engine — the same
  branch/sync/merge/DDL flow, in a browser, with a background-thread bridge
  that turns the engine's blocking confirm callbacks into a real
  click-by-click flow.

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

src/schemavcs_web/
├── bridge.py           pauses a blocking confirm() call on a background thread
├── confirm_adapter.py  the CLI's confirm_from_cli logic, as data instead of stdin
├── session.py          one throwaway repo + in-flight merge/sync session per browser
├── routes_repo.py       branches, direct CLI-verb forms, the schema-file editor
├── routes_merge.py      the merge click-by-click flow
├── routes_rename.py     the sync/rename-detection click-by-click flow
├── routes_ddl.py         emitted DDL for a branch
└── templates/            server-rendered pages (Jinja2, no JS framework)
```
