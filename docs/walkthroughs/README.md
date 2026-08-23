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

Phase 2 adds a second authoring path -- editing the `.schema` file directly instead
of using CLI verbs -- and the rename/retype detection heuristic that makes that
possible:

- [05-rename-detection-basics.md](05-rename-detection-basics.md) — the simplest case:
  one column renamed and retyped in the same edit, detected via the
  one-drop-one-add structural fallback.
- [06-rename-ambiguous-gap.md](06-rename-ambiguous-gap.md) — two columns renamed in
  the same edit, scored too close together to tell apart; a real, documented gap
  in the scoring formula where a clean-looking rename slips through undetected.
- [07-rename-reject-and-retry-pool.md](07-rename-reject-and-retry-pool.md) — two
  columns renamed with enough of a score gap to resolve; saying "no" to the first
  proposal puts both columns back in the pool instead of giving up on them.
- [08-rename-split-column-not-detected.md](08-rename-split-column-not-detected.md) —
  one column split into two; correctly never proposed as a rename, since neither
  candidate wins clearly enough over the other.
- [09-phase2-full-pipeline.md](09-phase2-full-pipeline.md) — the full pipeline: a
  rename detected via diffing on one branch, merged against another branch's
  directly-authored changes, DDL emitted — through the exact same merge/DDL engine
  Phase 1's walkthroughs already exercised.

An exhaustive pass over every conflict-detection and resolution case (the full
classification table, not just the two conflict shapes #02 and #04 already covered):

- [10-partial-conflict-bundled-edit.md](10-partial-conflict-bundled-edit.md) — a
  bundled rename+retype where both branches agree on the rename but disagree on the
  type. Also documents a real gap: the agreed field still gets re-litigated instead
  of only the disputed one.
- [11-conflict-type-vs-type.md](11-conflict-type-vs-type.md) — both branches retype
  the same column differently.
- [12-conflict-nullability-vs-nullability.md](12-conflict-nullability-vs-nullability.md)
  — both branches set a column's nullability differently.
- [13-conflict-delete-vs-mutation.md](13-conflict-delete-vs-mutation.md) — one branch
  drops a column while the other retypes it; also shows what "keep both" actually
  does here and why it's safe.
- [14-cross-object-column-level.md](14-cross-object-column-level.md) — the
  cross-object pass at the column level (a dropped column vs an index still
  referencing it), the smaller-scale sibling of #04's table-level case.
- [15-auto-resolve-identical-and-commuting.md](15-auto-resolve-identical-and-commuting.md)
  — the quiet cases: IDENTICAL (both branches made the exact same change) and
  COMMUTING (different, non-overlapping fields of the same column) — both resolve
  with zero prompts.

## Where this sits relative to existing tools

Two real systems were checked against this project's design, not just cited from
memory — see `decision_log.md` entries 17 and 33 for the full sourcing.

- **PlanetScale** does operation-level 3-way merging of schema changes (their own
  blog post confirms a four-bucket classification that maps directly onto this
  project's UNRELATED/IDENTICAL/COMMUTING/CONFLICT taxonomy) — but has no concept of
  rename identity at all. A rename looks like a drop+add to their merge, same as it
  would to this project's Phase 1 engine without Phase 2's detection layered on top.
- **Neon** branches storage, not schema: a branch is a copy-on-write pointer into the
  parent's WAL history, and its "Schema Diff" feature reports a past-vs-current
  schema change as a line-by-line SQL text diff — read-only, no rename detection, no
  merge, no identity model. It solves a different problem entirely (instant, cheap
  point-in-time database copies), not the one this project targets.

Between them: PlanetScale answers hard part #2 (3-way merge) with no answer to hard
part #1 (rename identity); Neon answers neither, solving a third, unrelated problem
instead. This project's actual contribution — walkthroughs 5-9 below — is combining
both: identity-preserving rename detection *and* a 3-way merge that understands it.

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
