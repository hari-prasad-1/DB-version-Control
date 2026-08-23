# Walkthrough 2 — a real merge conflict

Two branches rename the exact same column to two different new names. There's no
way to auto-merge "call it `y`" and "call it `z`" — a human has to pick. This is
what that actually looks like.

## Setup: one column, then two branches rename it differently

```
$ schemavcs init
initialized empty schemavcs repo at /tmp/schemavcs_walkthrough_02/.schemavcs

$ schemavcs migrate create-table users
created table 'users' (c474eb7c0902)

$ schemavcs migrate add-column users x string
added column users.x (ee1573d3ad6f)

$ schemavcs branch create branch-a
created branch 'branch-a' from 'main' at ee1573d3ad6f, switched to 'branch-a'

$ schemavcs migrate rename-column users x y
renamed column users.x -> y (d5557d829c5b)

$ schemavcs checkout main
switched to branch 'main'

$ schemavcs branch create branch-b --from main
created branch 'branch-b' from 'main' at ee1573d3ad6f, switched to 'branch-b'

$ schemavcs migrate rename-column users x z
renamed column users.x -> z (4e07ad19c17c)
```

Both branches forked from the same point, and both touched the *same* column `x` —
same underlying id, since neither branch dropped and recreated it, they both just
renamed it. That's exactly the shape of thing this tool tracks by id rather than by
name, specifically so this case can be recognized as "same column, disagreement," not
"two unrelated things that happen to share a name" (that second case is walkthrough
3).

## Merge — a real conflict

```
$ schemavcs checkout branch-a
switched to branch 'branch-a'

$ schemavcs merge branch-b --into branch-a <<< "a"
Conflict on identity 42a18536-5667-46a9-97c7-ede71543d688: both branches set a different name
Keep [a]/[b]/[both]? merged 'branch-b' into 'branch-a' at 0c518cae5943 (1 conflict(s) resolved)
```

(The `<<< "a"` is the answer piped into the prompt — normally you'd just type `a`
and hit enter when asked interactively. The prompt and the answer land on the same
line above only because of how the terminal output was captured; written out
separately, it reads:)

```
Conflict on identity 42a18536-5667-46a9-97c7-ede71543d688: both branches set a different name
Keep [a]/[b]/[both]? a
```

`identity 42a18536-...` is column `x`'s actual underlying id — the tool is telling
you exactly which column this is about, by its permanent identity, not by whatever
name it happens to have on either side right now (which is exactly the point: both
sides changed the name, so the name alone isn't a reliable way to refer to it here).

`(1 conflict(s) resolved)` — one real decision was required and made. The result,
after answering `a` (keep branch-a's side):

```
table users {
  column y: string
}
```

Branch-a's rename (`x` → `y`) won; branch-b's competing rename (`x` → `z`) was
discarded. If `b` had been answered instead, the column would be named `z`.
Answering `both` is also a valid choice for some conflict shapes, though not a
meaningful one for a plain rename-vs-rename disagreement like this.
