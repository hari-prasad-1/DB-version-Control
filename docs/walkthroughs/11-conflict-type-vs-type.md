# Walkthrough 11 — CONFLICT: both branches retype the same column, differently

The simplest real conflict shape: no renames, no bundling, just two branches
independently picking a different new type for the same column.

## Setup

```
$ schemavcs init
initialized empty schemavcs repo at /tmp/schemavcs_walkthrough_11/.schemavcs

$ schemavcs migrate create-table orders
created table 'orders' (8c5cfb1051d5)

$ schemavcs migrate add-column orders price string
added column orders.price (f6b254ab4174)

$ schemavcs branch create branch-a
created branch 'branch-a' from 'main' at f6b254ab4174, switched to 'branch-a'

$ schemavcs checkout main
switched to branch 'main'

$ schemavcs branch create branch-b --from main
created branch 'branch-b' from 'main' at f6b254ab4174, switched to 'branch-b'

$ schemavcs migrate --branch branch-a alter-column-type orders price decimal
altered orders.price type -> decimal (ae05a0a3cef7)

$ schemavcs migrate --branch branch-b alter-column-type orders price varchar
altered orders.price type -> varchar (828b15efce95)
```

## Merge

```
$ schemavcs checkout branch-a
switched to branch 'branch-a'

$ schemavcs merge branch-b --into branch-a <<< "a"
Conflict on identity edb3e2cf-297d-478a-a518-6a630552dfbe: both branches set a different type
Keep [a]/[b]? merged 'branch-b' into 'branch-a' at e7c9d04d0eb0 (1 conflict(s) resolved)
```

`_classify_single_pair` (`merge/classify.py`) looks up `AlterColumnType` in its
mutation-field table, compares `new_type` on both sides, and finds them different —
`CONFLICT`, reason `"both branches set a different type"`. If both sides had picked
the same new type instead, this would classify as `IDENTICAL` and never prompt at
all (walkthrough 15 shows that case directly).

Notice the prompt itself: `Keep [a]/[b]?`, no `both` option. A column's type is a
single value — it can't simultaneously be `decimal` and `varchar` — so `resolve.py`
marks this classification `single_valued_field=True` and the CLI only ever offers a
real, meaningful choice between the two. An earlier version of this prompt offered
`[a]/[b]/[both]` unconditionally for every conflict; "both" for a field like this one
didn't actually merge anything, it silently replayed both operations back-to-back
and let whichever one happened to apply last quietly win — technically not wrong,
but a choice that implied something it didn't deliver. Walkthrough 13 shows the one
conflict shape where "both" genuinely is meaningful (two different operation objects,
not one field with two proposed values) and stays offered.
