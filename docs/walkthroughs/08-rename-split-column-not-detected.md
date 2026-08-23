# Walkthrough 8 — Phase 2: a column split correctly does NOT get proposed as a rename

One column disappears, two appear. This is the case the mutual-best-match rule exists
specifically to get right: `full_name` shouldn't be guessed as "renamed to
`first_name`" just because it's somewhat similar to it — it was split into two
columns, not renamed into one.

## Setup

```
$ schemavcs init
initialized empty schemavcs repo at /tmp/schemavcs_walkthrough_08/.schemavcs

$ schemavcs migrate create-table people
created table 'people' (94e829e99e23)

$ schemavcs migrate add-column people full_name string
added column people.full_name (d76690115d1f)

$ cat schemas/main.schema
table people {
  column full_name: string
}
```

## Edit: split into two columns, then sync

```
$ cat > schemas/main.schema <<EOF
table people {
  column first_name: string
  column last_name: string
}
EOF

$ schemavcs sync
generated migration 195c81d2d073 from /tmp/schemavcs_walkthrough_08/schemas/main.schema
```

No prompt — nothing was proposed at all, and that's correct. `full_name`'s pool
here has two candidates, and the 1-old/2-new shape means the one-drop-one-add
structural fallback doesn't apply. Scoring `full_name` against both `first_name` and
`last_name`, neither one wins clearly enough over the other for `_best_mutual_match`
to treat it as a confident pairing. Nothing looks unambiguous enough to safely guess,
so the detector correctly gives up and finalizes it as a plain drop (`full_name`)
plus two plain adds (`first_name`, `last_name`) rather than propose a wrong rename.

```
$ python -c "
from schemavcs.dag.persistence import load
from schemavcs.dag.walk import replay
from pathlib import Path
store = load(Path('/tmp/schemavcs_walkthrough_08'))
snap = replay(store, store.head('main'), 'main')
for c in snap.tables[0].columns:
    print(c.name, c.type)
"
first_name string
last_name string
```

This is the same behavior documented as a locked design decision before any code was
written (design-hardening review, §B) — split/merge cases are expected to degrade
gracefully to plain drop+add, never a guessed rename, because guessing wrong here is
worse than not guessing at all.
