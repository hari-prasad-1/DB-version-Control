# Walkthrough 12 — CONFLICT: both branches set a column's nullability differently

Same shape as walkthrough 11, different field — one branch makes a column required,
the other makes it optional.

## Setup

```
$ schemavcs init
initialized empty schemavcs repo at /tmp/schemavcs_walkthrough_12/.schemavcs

$ schemavcs migrate create-table users
created table 'users' (3c2a078c0235)

$ schemavcs migrate add-column users email string
added column users.email (a88faf5075f3)

$ schemavcs branch create branch-a
created branch 'branch-a' from 'main' at a88faf5075f3, switched to 'branch-a'

$ schemavcs checkout main
switched to branch 'main'

$ schemavcs branch create branch-b --from main
created branch 'branch-b' from 'main' at a88faf5075f3, switched to 'branch-b'

$ schemavcs migrate --branch branch-a alter-column-nullability users email false
altered users.email nullable -> False (461a9acfcd13)

$ schemavcs migrate --branch branch-b alter-column-nullability users email true
altered users.email nullable -> True (ad4a33e600f2)
```

## Merge

```
$ schemavcs checkout branch-a
switched to branch 'branch-a'

$ schemavcs merge branch-b --into branch-a <<< "a"
Conflict on identity 39e75140-41db-43c5-bb99-cb652f066832: both branches set a different nullable
Keep [a]/[b]? merged 'branch-b' into 'branch-a' at 26405564c468 (1 conflict(s) resolved)
```

`AlterColumnNullability` is in the same mutation-field table as `AlterColumnType`
(`merge/classify.py`'s `_MUTATION_FIELD`) — same code path, same reasoning, just
comparing `.nullable` instead of `.new_type`. This is decision-hardening §C's row 2
made real: "email required" vs "email optional" is a genuine disagreement a human
has to settle, not something that can be safely auto-merged either way.

Same as walkthrough 11: the prompt only offers `[a]/[b]`, not `[a]/[b]/[both]` —
`nullable` is a single boolean, and it can't hold both `True` and `False` at once,
so `resolve.py` doesn't offer a choice that wouldn't mean anything.
