# Walkthrough 14 — cross-object pass, one level smaller: a dropped column, not a dropped table

Walkthrough 4 showed the cross-object pass catching a whole table drop with
something still pointing at it. The same mechanism runs at the column level too —
checking "did the other branch destroy a *column* I'm relying on" instead of "did
the other branch destroy a *table* I'm relying on" (design-hardening §D: "the same
problem, one level smaller... literally the same check run at a smaller scale").

## Setup: a column, then one branch drops it while the other indexes it

```
$ schemavcs init
initialized empty schemavcs repo at /tmp/schemavcs_walkthrough_14/.schemavcs

$ schemavcs migrate create-table users
created table 'users' (0853bf315609)

$ schemavcs migrate add-column users legacy_id int
added column users.legacy_id (e9a579134482)

$ schemavcs branch create branch-a
created branch 'branch-a' from 'main' at e9a579134482, switched to 'branch-a'

$ schemavcs checkout main
switched to branch 'main'

$ schemavcs branch create branch-b --from main
created branch 'branch-b' from 'main' at e9a579134482, switched to 'branch-b'

$ schemavcs migrate --branch branch-a drop-column users legacy_id
dropped column users.legacy_id (67fbe60d9a88)

$ schemavcs migrate --branch branch-b add-index users idx_legacy --columns legacy_id
added index 'idx_legacy' on users(legacy_id) (b2c4ff405035)
```

Neither operation shares an identity with the other — one is keyed by the column's
id, the other by the index's own id — so `classify.py`'s per-identity grouping never
even notices this pair. This is exactly the gap `cross_object_pass` exists to catch
separately.

## Merge

```
$ schemavcs checkout branch-a
switched to branch 'branch-a'

$ schemavcs merge branch-b --into branch-a
Conflict on identity e6bcfeab-79fb-466e-86ef-b4840b0ea7b9: branch A dropped column 'users.legacy_id' that another branch's operation still references
The dropped table/column wins; the dependent object above will also be dropped. Press enter to acknowledge. merged 'branch-b' into 'branch-a' at 09ebff0238e7 (1 conflict(s) resolved)
```

Same resolution shape as the table-level case: only one path is offered (the drop
wins, the dependent index gets a corrective drop synthesized alongside it) — "undo
the drop, keep the index" isn't offered, for the same reason walkthrough 4 explains:
this tool doesn't retain a copy of what a drop destroyed, so there's nothing to
resurrect.
