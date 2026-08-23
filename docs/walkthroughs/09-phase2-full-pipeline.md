# Walkthrough 9 — Phase 2 end to end: detected rename, merged through the unmodified Phase 1 engine

This is the whole point of Phase 2's design: a rename **detected** by editing a
schema file feeds the exact same merge/DDL engine that walkthroughs 1-4 already
proved correct against **authored** renames. Nothing in `merge/` or `ddl/` was
touched to make this work — Phase 2 only adds a second producer of the same
`Operation` types.

Same shape of scenario as walkthrough 1's demo and the project's own end-to-end
tests: one branch renames+retypes a column and adds a new one, another branch
independently adds a colliding column with the same name plus an unrelated column,
and drops an unrelated table.

## Setup: base state, then fork two branches

```
$ schemavcs init
initialized empty schemavcs repo at /tmp/schemavcs_walkthrough_09/.schemavcs

$ schemavcs migrate create-table users
created table 'users' (5ce8f3ba20c9)

$ schemavcs migrate add-column users subscription_type string
added column users.subscription_type (d268000782ec)

$ schemavcs migrate create-table legacy_reports
created table 'legacy_reports' (e17d84e7e65e)

$ schemavcs branch create branch-a
created branch 'branch-a' from 'main' at e17d84e7e65e, switched to 'branch-a'

$ schemavcs checkout main
switched to branch 'main'

$ schemavcs branch create branch-b --from main
created branch 'branch-b' from 'main' at e17d84e7e65e, switched to 'branch-b'
```

## branch-a: edit the schema file, detect the rename+retype

```
$ schemavcs checkout branch-a
switched to branch 'branch-a'

$ cat > schemas/branch-a.schema <<EOF
table users {
  column plan_type: enum
}
table legacy_reports {
}
EOF

$ schemavcs sync --branch branch-a
Detected a possible rename: 'subscription_type' -> 'plan_type' (no ambiguity, only one candidate on each side)
Confirm rename? [y/n] y
generated migration 38a1aca6f845 from /tmp/schemavcs_walkthrough_09/schemas/branch-a.schema
```

A second, separate edit adds `notes` — kept as its own `sync` call rather than
bundled into the rename edit, so the rename detector's pool stays 1-old/1-new
(walkthrough 5's clean fallback case) instead of 1-old/2-new (walkthrough 6's harder,
score-only case):

```
$ cat > schemas/branch-a.schema <<EOF
table users {
  column plan_type: enum
  column notes: text
}
table legacy_reports {
}
EOF

$ schemavcs sync --branch branch-a
generated migration 256ea2c625de from /tmp/schemavcs_walkthrough_09/schemas/branch-a.schema
```

## branch-b: independent, ordinary CLI-authored changes

No file editing here at all — this branch uses the direct Phase 1 verbs, same as
walkthrough 1, to show the two authoring paths coexisting on sibling branches:

```
$ schemavcs migrate --branch branch-b add-column users notes string
added column users.notes (7d196fe77dc0)

$ schemavcs migrate --branch branch-b add-column users region string
added column users.region (71ecf33c210e)

$ schemavcs migrate --branch branch-b drop-table legacy_reports
dropped table 'legacy_reports' (7740f420a166)
```

## Merge — the same engine, the same collision-resolution rule

```
$ schemavcs checkout branch-a
switched to branch 'branch-a'

$ schemavcs merge branch-b --into branch-a
merged 'branch-b' into 'branch-a' at 1d7e3c2fdb0b (0 conflict(s) resolved)
note: column 'notes' was independently added on both branches -- the one from branch b was kept, the one from branch a was dropped as a duplicate name, review if that's not what you wanted
```

Same name-collision mechanism as walkthrough 3, resolving automatically by
DAG-distance — completely indifferent to the fact that one side's `notes` column
came from a detected diff and the other came from a direct CLI verb. The merge
engine only ever sees `Operation` values; it has no idea which authoring path
produced either one.

## Emit DDL — the exact same code path walkthrough 1 and the Phase 1 demo already exercised

```
$ schemavcs emit-ddl --branch branch-a
CREATE TABLE users ();
ALTER TABLE users ADD COLUMN subscription_type string;
CREATE TABLE legacy_reports ();
ALTER TABLE users RENAME COLUMN subscription_type TO plan_type;
ALTER TABLE users ALTER COLUMN plan_type TYPE enum;
ALTER TABLE users ADD COLUMN notes text;
ALTER TABLE users ADD COLUMN notes string;
ALTER TABLE users ADD COLUMN region string;
DROP TABLE legacy_reports;
ALTER TABLE users DROP COLUMN notes;
```

Reading this in order: `users` and `legacy_reports` are created, `subscription_type`
is added then renamed and retyped (all from branch-a's *detected* edits), both
`notes` columns are added (the collision, before resolution) and then the losing one
(branch-a's `text` column) is dropped at the end — the dependency ordering and the
collision resolution are identical in shape to the Phase 1 demo, because it's
literally the same `toposort`/`emit_ddl` code (`ddl/toposort.py`, `ddl/emitter.py`)
running over a `CompoundOperation` list, regardless of which sub-phase produced the
individual operations inside it.

This is the strongest evidence in this project that the two authoring paths really
are interchangeable at the `Operation` boundary, per the plan's own framing of what
sub-phase 2.5's demo test needed to prove (`tests/e2e/test_phase2_demo.py`).
