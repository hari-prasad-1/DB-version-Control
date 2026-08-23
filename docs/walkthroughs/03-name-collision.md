# Walkthrough 3 — same name, different column, no conflict asked

Two branches each independently add a column called `notes` to the same table.
Under the hood these are two *completely different* columns — each branch minted
its own fresh id the moment it created its column — so this never becomes a
per-identity conflict the way walkthrough 2's rename disagreement did. Left alone,
though, both would survive a merge and produce a table with two columns sharing one
name, which isn't valid. This is resolved automatically, with an explanatory note,
and no human confirmation.

## Setup: two branches, each independently adds a column called 'notes'

```
$ schemavcs init
initialized empty schemavcs repo at /tmp/schemavcs_walkthrough_03/.schemavcs

$ schemavcs migrate create-table users
created table 'users' (46fc8a6a38e0)

$ schemavcs branch create branch-a
created branch 'branch-a' from 'main' at 46fc8a6a38e0, switched to 'branch-a'

$ schemavcs migrate add-column users notes text
added column users.notes (98a462f7be62)

$ schemavcs checkout main
switched to branch 'main'

$ schemavcs branch create branch-b --from main
created branch 'branch-b' from 'main' at 46fc8a6a38e0, switched to 'branch-b'

$ schemavcs migrate add-column users notes string(500)
added column users.notes (a5cf8bceb30e)
```

Branch-a's `notes` is type `text`. Branch-b's `notes` is type `string(500)`. Same
name, same table, but two different ids and two different types — a genuine name
collision, not a case where both sides did the same thing.

## Merge — resolved automatically, no prompt, just a note

```
$ schemavcs checkout branch-a
switched to branch 'branch-a'

$ schemavcs merge branch-b --into branch-a
merged 'branch-b' into 'branch-a' at f2e6692db965 (0 conflict(s) resolved)
note: column 'notes' was independently added on both branches -- the one from branch a was kept, the one from branch b was dropped as a duplicate name, review if that's not what you wanted
```

`0 conflict(s) resolved` — nobody was asked a yes/no or a/b question — but the
`note:` line still tells you exactly what happened and why, so this doesn't pass
silently. The merged result:

```
table users {
  column notes: text
}
```

Only one `notes` column survived (branch-a's, type `text`). The rule that decided
this: whichever add is *closer to the point the branches diverged* wins. Since
branch-a's add was that branch's very first commit after the fork (same distance as
branch-b's), the tie broke toward the branch being merged into (`branch-a`, the
target of this merge) — the same "target branch wins ties" rule used elsewhere in
this tool, and never based on wall-clock time, since clocks aren't meaningfully
comparable across independent branches.
