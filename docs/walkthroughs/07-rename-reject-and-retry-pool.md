# Walkthrough 7 — Phase 2: rejecting a proposal puts columns back in the pool

Two columns renamed in the same edit, scored far enough apart this time that both
clear the ambiguous-gap threshold — a genuinely resolvable case. This walkthrough
also shows what happens when a human says "no" to a proposal: the two columns
involved go back into the pool to be checked against whatever's left, rather than
being immediately finalized as a plain drop and a plain add.

## Setup

```
$ schemavcs init
initialized empty schemavcs repo at /tmp/schemavcs_walkthrough_07/.schemavcs

$ schemavcs migrate create-table accounts
created table 'accounts' (e74c9d99b4e1)

$ schemavcs migrate add-column accounts subscription_type string
added column accounts.subscription_type (a26d29c7eaaf)

$ schemavcs migrate add-column accounts account_status string
added column accounts.account_status (0d252a400fb9)
```

## Edit both columns, then sync, saying no to the first proposal

```
$ cat > schemas/main.schema <<EOF
table accounts {
  column plan_type: enum
  column status: enum
}
EOF

$ schemavcs sync
Detected a possible rename: 'account_status' -> 'status' (similarity 0.62)
Confirm rename? [y/n] n
Detected a possible rename: 'subscription_type' -> 'plan_type' (similarity 0.61)
Confirm rename? [y/n] y
generated migration 220ddc4dbeaa from /tmp/schemavcs_walkthrough_07/schemas/main.schema
```

Scoring both pairs directly shows why these two — and not the diagonal pairing —
were the ones proposed:

```
subscription_type -> plan_type   0.610
subscription_type -> status      0.429
account_status    -> plan_type   0.446
account_status    -> status      0.618
```

`account_status` <-> `status` is the strongest mutual match (0.618, gap 0.172 over
the runner-up), so it's proposed first. Saying "n" rejects that *specific pairing* —
per `rename_detect/detector.py`, `account_status` and `status` both go back into the
pool rather than being finalized immediately. On the next iteration, the only
mutual-best-match left standing is `subscription_type` <-> `plan_type` (0.61, gap
0.181), which gets proposed and confirmed.

## The result: one rename, one plain drop+add

```
$ python -c "
from schemavcs.dag.persistence import load
from schemavcs.dag.walk import replay
from pathlib import Path
store = load(Path('/tmp/schemavcs_walkthrough_07'))
snap = replay(store, store.head('main'), 'main')
for c in snap.tables[0].columns:
    print(c.name, c.type, c.position)
"
plan_type enum 0
status enum 1
```

Both columns land with the right final name and type either way — but only
`subscription_type` -> `plan_type` is recorded in history as an actual `RenameColumn`
+ `AlterColumnType` compound operation with identity preserved (same `column_id`
before and after). `account_status` -> `status` is recorded as a `DropColumn` +
`AddColumn` pair instead — a brand-new column id, no identity link to the old one —
because once `account_status` and `status` were the only pair left in the pool with
nothing else to compare against, and the human had already rejected pairing them
with each other, there was nothing left to propose. This is the correct, intentional
outcome per the design (rejecting a proposal is a real "no," not just "ask me again
later" for the exact same pairing) — but it's worth knowing that a real identity
distinction hides behind what looks like an identical-looking final result.
