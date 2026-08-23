# Walkthrough 15 — the quiet cases: IDENTICAL and COMMUTING, no prompt at all

Every prior walkthrough in this section showed a human being asked something. Most
real merges don't need that at all — the majority of the classification table
(design-hardening §C) exists specifically to auto-resolve safely and say nothing.
This walkthrough shows both of those quiet paths directly, so the difference between
"nothing to ask" and "something to ask" is visible side by side.

## IDENTICAL — both branches made the exact same change

```
$ schemavcs init
initialized empty schemavcs repo at /tmp/schemavcs_walkthrough_15/.schemavcs

$ schemavcs migrate create-table users
created table 'users' (b97f685bfb4d)

$ schemavcs migrate add-column users status string
added column users.status (f433dbbdc2c4)

$ schemavcs branch create branch-a
created branch 'branch-a' from 'main' at f433dbbdc2c4, switched to 'branch-a'

$ schemavcs checkout main
switched to branch 'main'

$ schemavcs branch create branch-b --from main
created branch 'branch-b' from 'main' at f433dbbdc2c4, switched to 'branch-b'

$ schemavcs migrate --branch branch-a alter-column-nullability users status false
altered users.status nullable -> False (cc11fbb49342)

$ schemavcs migrate --branch branch-b alter-column-nullability users status false
altered users.status nullable -> False (d4d594304c85)

$ schemavcs checkout branch-a
switched to branch 'branch-a'

$ schemavcs merge branch-b --into branch-a
merged 'branch-b' into 'branch-a' at 98214dcc7c91 (0 conflict(s) resolved)
```

`0 conflict(s) resolved`, no prompt of any kind. `_classify_single_pair`
(`merge/classify.py`) checks `op_a == op_b` before anything else — both branches
independently made the identical `AlterColumnNullability(nullable=False)` change to
the same column, so there's genuinely nothing to decide. `auto_resolve`
(`merge/resolve.py`) returns `()` for `IDENTICAL` specifically because the change is
already reachable through either parent's own history — re-storing it in the merge
node would apply it a second time.

## COMMUTING — different, non-overlapping fields of the same identity

```
$ schemavcs init
initialized empty schemavcs repo at /tmp/schemavcs_walkthrough_16/.schemavcs

$ schemavcs migrate create-table users
created table 'users' (114cb944aa7e)

$ schemavcs migrate add-column users bio string
added column users.bio (9bd5d89cbc7d)

$ schemavcs branch create branch-a
created branch 'branch-a' from 'main' at 9bd5d89cbc7d, switched to 'branch-a'

$ schemavcs checkout main
switched to branch 'main'

$ schemavcs branch create branch-b --from main
created branch 'branch-b' from 'main' at 9bd5d89cbc7d, switched to 'branch-b'

$ schemavcs migrate --branch branch-a rename-column users bio biography
renamed column users.bio -> biography (fb27fbd249ad)

$ schemavcs migrate --branch branch-b alter-column-nullability users bio false
altered users.bio nullable -> False (f9c3cc3f42da)

$ schemavcs checkout branch-a
switched to branch 'branch-a'

$ schemavcs merge branch-b --into branch-a
merged 'branch-b' into 'branch-a' at 7e0e06ba6209 (0 conflict(s) resolved)
```

Again `0 conflict(s) resolved`, no prompt. branch-a renamed the column; branch-b,
independently, made that same column non-nullable. Two different operation types
(`RenameColumn`, `AlterColumnNullability`) touching different, non-overlapping
fields of the same column — `_classify_single_pair` falls through to `COMMUTING`,
`"different, non-overlapping fields touched on each side"`. Unlike `IDENTICAL`,
`auto_resolve` re-stores *both* operations here (each side only carries its own
half of the story), and the merged result correctly has both:

```
biography string False
```

The rename took effect (branch-a's contribution) and the column is non-nullable
(branch-b's contribution) — both survived, neither needed a human, because neither
one actually contradicts the other.
