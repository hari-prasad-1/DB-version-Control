# Walkthroughs

Real terminal sessions against the actual CLI — every command and every line of
output below is copied from a genuine run, not written by hand. If you're new to
this project, read these in order; each one builds on the last and shows exactly
what the tool does and why.

- [01-basics.md](01-basics.md) — init, create a table, add columns, branch, rename +
  retype a column, a clean merge with no conflicts, emit SQL, add an index/foreign
  key, drop a column and a table.
- [02-merge-conflict.md](02-merge-conflict.md) — two branches rename the *same*
  column to two different names. A real conflict a human has to resolve.
- [03-name-collision.md](03-name-collision.md) — two branches independently add a
  *different* column that happens to share the same name. Resolved automatically,
  no human needed, just an explanatory note.
- [04-cross-object-conflict.md](04-cross-object-conflict.md) — one branch drops a
  whole table while another branch adds something to it. A different kind of
  conflict than #02, caught by a separate mechanism, resolved a different way.

## How these were produced

Every command is run through the real CLI entry point
(`python -m schemavcs.cli.main --repo <path> <command>`), against a fresh, empty
repo, and the output shown is exactly what came back — nothing edited, nothing
invented. Anywhere the tool needs a yes/no or a/b answer from a human, the answer is
piped into stdin and shown explicitly, so you can see exactly what was asked and how
it was answered.

To reproduce any of these yourself:

```
poetry run python -m schemavcs.cli.main --repo /tmp/some-folder init
poetry run python -m schemavcs.cli.main --repo /tmp/some-folder migrate create-table users
# ...and so on, following the commands in whichever walkthrough you're reading
```
