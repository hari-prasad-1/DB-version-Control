# Walkthrough 13 — CONFLICT: one branch deletes a column, the other mutates it

There's no sensible way to auto-merge "delete this" with "change this" — this is
decision-hardening §C's row 3, generalized to cover any mutation (retype, rename,
nullability), not just the narrower "renamed vs deleted" case the original plan
started with.

This is also the one conflict shape in this section where `[both]` genuinely stays
on the menu (unlike walkthroughs 11/12's single-field conflicts): `DropColumn` and
`AlterColumnType` are two real, separate operation objects, not one field with two
proposed values, so "keep both" has an actual, if unusual, meaning here.

## Setup

```
$ schemavcs init
initialized empty schemavcs repo at /tmp/schemavcs_walkthrough_13/.schemavcs

$ schemavcs migrate create-table users
created table 'users' (095d956bdf65)

$ schemavcs migrate add-column users legacy_id int
added column users.legacy_id (5e2f5431c559)

$ schemavcs branch create branch-a
created branch 'branch-a' from 'main' at 5e2f5431c559, switched to 'branch-a'

$ schemavcs checkout main
switched to branch 'main'

$ schemavcs branch create branch-b --from main
created branch 'branch-b' from 'main' at 5e2f5431c559, switched to 'branch-b'

$ schemavcs migrate --branch branch-a drop-column users legacy_id
dropped column users.legacy_id (fcd68756b75e)

$ schemavcs migrate --branch branch-b alter-column-type users legacy_id bigint
altered users.legacy_id type -> bigint (b95d2cdce3a2)
```

## Merge — "keep a" (the drop wins)

```
$ schemavcs checkout branch-a
switched to branch 'branch-a'

$ schemavcs merge branch-b --into branch-a <<< "a"
Conflict on identity 1de4f64d-55e2-4079-856a-b71ee9e2bfc7: one branch removed this identity while the other mutated it
Keep [a]/[b]/[both]? merged 'branch-b' into 'branch-a' at af88a8df7f52 (1 conflict(s) resolved)
```

`_classify_single_pair` (`merge/classify.py`) checks the destructive-variant list
first, before ever comparing field values — `DropColumn` on one side plus *any*
mutation on the other always lands here, regardless of which specific mutation type
branch-b picked. `legacy_id` doesn't exist in the merged result either way "a" is
chosen: `DropColumn` wins.

## What "both" actually does here — a real, load-bearing safety net

```
$ schemavcs merge branch-b --into branch-a <<< "both"
...
```

Choosing "both" here re-stores *both* `DropColumn` and `AlterColumnType` for the same
column. Replaying that in either order still ends with the column gone —
`AlterColumnType` silently no-ops when its target column no longer exists (decision
log entry 24: every mutation op except `CreateTable`/`DropTable` tolerates a missing
target). That no-op rule was originally added to make merge-node replay safe after a
cross-object correction; here it quietly does double duty, making an otherwise
order-dependent "both" choice for a delete-vs-mutate conflict resolve safely to "the
delete wins" regardless of which operation replays first — not something that was
specifically designed for this case, but a real consequence of it worth knowing
about.
