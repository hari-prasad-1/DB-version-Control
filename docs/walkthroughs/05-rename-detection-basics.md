# Walkthrough 5 — Phase 2: detecting a rename by editing the schema file

Everything up to here (walkthroughs 1-4) authored every change through an explicit
CLI verb — `rename-column`, `alter-column-type`, and so on — so there was never any
ambiguity about what happened. Phase 2 adds a second way to author changes: edit the
tracked `.schema` file directly, by hand, the way you'd edit a Rails `schema.rb`, then
run `sync` and let the tool figure out what changed.

This walkthrough shows the simplest case: one column renamed and retyped in the same
edit, with nothing else around it to create ambiguity.

## Setup

```
$ schemavcs init
initialized empty schemavcs repo at /tmp/schemavcs_walkthrough_05/.schemavcs

$ schemavcs migrate create-table users
created table 'users' (95dd0e5c026b)

$ schemavcs migrate add-column users subscription_type string
added column users.subscription_type (3227410c58fe)

$ cat schemas/main.schema
table users {
  column subscription_type: string
}
```

The `.schema` file lives at `schemas/<branch>.schema` — a plain visible file, not
buried under `.schemavcs/` — kept in sync after every CLI-authored change specifically
so a human can open and edit it directly (the two-way-sync design, decision 9).

## Edit the file directly, then `sync`

```
$ cat > schemas/main.schema <<EOF
table users {
  column plan_type: enum
}
EOF

$ schemavcs sync
Detected a possible rename: 'subscription_type' -> 'plan_type' (no ambiguity, only one candidate on each side)
Confirm rename? [y/n] y
generated migration 4483989fd8c1 from /tmp/schemavcs_walkthrough_05/schemas/main.schema
```

## Why this got proposed at all

`sync` diffs the edited file against the tracked snapshot (`snapshot/diff.py`).
`subscription_type` disappeared, `plan_type` appeared — same table, one column
missing, one column new. That's the **one-drop-one-add structural fallback**
(`rename_detect/detector.py`): with exactly one candidate on each side, there's no
ambiguity to guess wrong about, so it's always proposed for confirmation regardless
of similarity score. That's why the prompt above says "no ambiguity" instead of a
percentage — there was nothing else to score it against.

Type changing too (`string` -> `enum`) doesn't block the rename proposal; the rename
and the retype are two independent facts about the same column, and the tool bundles
both into one compound operation once the rename itself is confirmed:

```
$ python -c "
from schemavcs.dag.persistence import load
from schemavcs.dag.walk import replay
from pathlib import Path
store = load(Path('/tmp/schemavcs_walkthrough_05'))
snap = replay(store, store.head('main'), 'main')
for c in snap.tables[0].columns:
    print(c.name, c.type)
"
plan_type enum
```

## A real gap this surfaced: two candidates, not one

The structural fallback above only fires with *exactly* one unmatched column on each
side. The moment there's a second column in the mix — even one that's a plain,
unrelated add with no rename involved — the pool has 1 old / 2 new, the fallback
doesn't apply, and detection falls back to pure similarity scoring instead. Walkthrough
6 shows what that path looks like, including a case where scoring alone isn't
confident enough to propose anything at all.
