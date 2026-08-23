# Decisions

A running log of the real calls made building this — what was chosen, what
was seriously considered instead, why, and what was deliberately left out.
Every example below is a real scenario the tool actually handles; see
`docs/walkthroughs/` for the captured terminal sessions behind each one.

---

## The brief (problem statement 2, as given)

**The problem.** Build branch/diff/merge for database schemas — the way Git
does for source code, but for structure (tables, columns, types,
constraints, indexes), not row data. Two people evolve the same schema on
separate branches; see exactly what diverged; merge it back.

**The hard part.** Two sub-problems compound into one hard problem:

1. **Identity across divergence.** If branch A renames `email` to
   `contact_email`, comparing before/after schemas alone can't tell "this is
   the same column, renamed" from "an unrelated column was deleted and a
   different one added." Get this wrong and a merge either silently loses a
   rename or wrongly flags a non-conflict as one.
2. **Three-way semantic merge.** Combining two branches' changes isn't list
   concatenation — some pairs of changes are safe to auto-combine, some are
   safe only because they don't actually contradict each other, and some are
   genuine conflicts a machine has no business silently resolving.

**The slice shipped.** Branch a schema, evolve two branches independently
(including a rename+retype on one, a colliding add and a table drop on the
other), merge them — showing at least one auto-resolved pair and at least
one real conflict a human has to confirm — then emit valid, dependency-
ordered DDL for the result. The specific edge case handled deliberately:
rename+retype on the same column, where the type also changing must not
cause identity to be lost (exact-property matching alone would misread this
as delete+create).

**Why this instead of the other two prompts.** This lets the hard part be
the actual center of the build — rename identity across independently-
diverged branches is a problem Alembic and PlanetScale each partially punt
on (see the comparison table below), so there's a real, citable gap to fill
rather than a known reference implementation to reproduce.

---

## Decision 1 — Two authoring paths, not one

**The decision.** Support both an explicit CLI verb per operation
(`schemavcs migrate rename-column users email contact_email`) *and* editing
a tracked schema file directly and running `sync`, which diffs the edit and
figures out what changed.

**Alternatives considered.**
- CLI-verbs only, matching a Rails-style imperative migration file — every
  change is unambiguous, but doesn't match how anyone actually wants to work
  day to day (nobody wants to type a CLI verb for every column tweak).
- File-diffing only (Django/Alembic-`autogenerate`-style), matching the
  brief's original framing — realistic day-to-day workflow, but reopens the
  identity-loss problem for every single change, including the ones that
  don't need to be ambiguous at all.

**Reasoning and trade-offs.** Building CLI-verbs first meant the merge
engine — the genuinely hard, novel part — could be built and fully tested
against real branch/merge scenarios *before* the rename-detection heuristic
existed at all, with zero rename ambiguity to worry about while doing it.
File-diffing then layers on as an additive second producer of the same
underlying operations, proven interchangeable by running a rename detected
via file-edit through the exact same merge and DDL code a CLI-verb-authored
rename already went through (`docs/walkthroughs/09-phase2-full-pipeline.md`).
The cost: two authoring surfaces to maintain instead of one.

**What was deliberately cut.** A `--and`-chained compound-verb CLI syntax
(e.g. `rename-column ... --and alter-column-type ...` in one invocation) —
the plan called for it, but two separate verb calls against the same column
already produce the same compound identity group during merge, so the
extra parsing surface wasn't worth building for a purely cosmetic
convenience.

---

## Decision 2 — Identity is a synthetic UUID, not a Postgres internal id

**The decision.** Every table/column/index/constraint gets its own UUID the
moment it's created. That UUID — never the name — is what merges key off of.

**Alternatives considered.** Postgres's own internal identifiers:
`pg_class.oid`, `pg_attribute.attnum`, logical replication's `REPLICA
IDENTITY`.

**Reasoning and trade-offs.** All three were actually investigated, not
assumed unusable. None of them are built to survive what this tool needs:
two *disconnected* copies of a schema, independently evolving, that later
need to recognize "we're both talking about the same column." Postgres
reuses OIDs over time and has no concept of comparing identity across two
separate catalogs — this is a structural gap in what those ids are *for*,
not a research gap on this project's part. The cost of the synthetic-UUID
approach: this tool's identity model is invisible to Postgres itself, so
nothing about it can be inspected via `psql` — it only exists in this
tool's own tracked metadata.

**What was deliberately cut.** Any attempt to derive identity from
Postgres's own catalog — abandoned early, once the investigation above
confirmed there was no real signal to derive it from.

---

## Decision 3 — Rename detection: similarity-scored, human-confirmed

**The decision.** For the file-diffing authoring path only, score every
plausible old/new column pair and propose a rename only when both sides
clearly prefer each other, always still requiring human confirmation.

```
score = 0.45·name_similarity + 0.25·type_compatibility
      + 0.15·constraint_overlap + 0.15·position_proximity
```

**Alternatives considered.**
- Exact-property matching (same type + same constraints, just a different
  name → propose a rename). Rejected: fails on the project's own headline
  case, `subscription_type: string` → `plan_type: enum` — a rename that
  *also* retypes, which is a common real pattern (tightening free text into
  a fixed set of choices), not an edge case.
- Solving optimal bipartite matching algorithmically for ambiguous cases
  (multiple plausible candidates on each side). Rejected as overkill: a
  2-second human confirmation per ambiguous pair is cheaper than building
  and validating an optimal-matching solver for a case this rare.

**Reasoning and trade-offs.** This is Django `makemigrations`'s own
approach (heuristic match, human confirms) — the closest existing, working
solution to this exact problem, extended here to survive independently
diverged branches, which Django (a single-timeline tool) never had to
handle. The formula is explicitly empirical, not derived — documented as a
tuning target, not a constant, and calibrated against the project's own
demo pair as the first real test written against it. A same-typed,
similarly-positioned but semantically unrelated column can score above a
better name match purely on non-name signals outweighing a modest lead —
documented as an accepted, known weakness of an empirical formula, not
silently patched, because the mutual-best-match + ambiguous-gap-threshold
mechanism (below) still prevents it from silently mis-proposing anything.

**What was deliberately cut.**
- **The swap blind spot.** If two columns' names are swapped with literally
  nothing else different — same type, same constraints, same position —
  there is no signal anywhere in a file diff that anything happened. No
  algorithm that only reads file contents can catch this; documented as an
  accepted limitation rather than engineered around.
- **Warning on a near-miss.** When two candidate renames in the same edit
  both clear the acceptance threshold individually but the gap between them
  is too small to safely pick one, the tool currently says nothing at all —
  not even a low-confidence note — and quietly falls back to plain
  drop+add. The final schema state ends up correct either way; only the
  fact that a rename happened is lost from history. Surfacing every
  near-miss was cut because it would add noise to the common case (an
  ordinary edit with two similarly-named unrelated columns) to cover a
  rarer one.
- **Requiring exact type match for a rename proposal** — cut specifically
  because it would have broken the headline demo case above.

---

## Decision 4 — Merge classification, modeled on PlanetScale, extended for renames

**The decision.** Group every operation from both branches by what it
touches, classify each group, and only ask a human about groups that are
genuinely ambiguous or contradictory.

**Alternatives considered.** Naively unioning both branches' migration
lists and applying them in some fixed order. Rejected outright — this
silently applies contradictory operations and produces a result that
depends on merge direction, which the brief explicitly calls out as a
correctness failure, not a style preference.

**Reasoning and trade-offs.** This project's own classification enum
(same/different/conflicting) is directly modeled on PlanetScale's publicly
documented four-bucket merge algorithm — verified against their actual blog
post, not assumed from memory. But PlanetScale's model has a real gap this
project had to fill on its own: their public description talks entirely in
terms of add/drop/create, with no rename-identity concept at all, so the
classification here had to add an explicit "one side deleted this, the
other side changed it" rule that PlanetScale's model doesn't need. A
bundled edit (e.g. both branches rename a column to the same new name but
disagree on its new type) is correctly *classified* as "half agreed, half
disputed" — but the resolution UI doesn't yet act on that distinction; a
human is still asked to re-approve the entire bundle, including the part
that was never actually in question. Documented as a known implementation
gap rather than silently worked around, since fixing it properly changes
how the merge engine resolves things, not just what a prompt says.

**What was deliberately cut.**
- **Reasoning about what's inside a CHECK constraint.** Stored and passed
  through as an opaque string, never parsed. Real expression parsing was
  judged disproportionate scope for what this project needs to demonstrate.
- **Two branches adding different, non-conflicting foreign keys to the same
  table** — checked explicitly, confirmed this doesn't produce invalid SQL
  either way, so it was left as an ordinary auto-merge rather than building
  a more elaborate compatibility checker for a case that isn't actually
  broken.
- **Index/constraint enforcement coupling at the Postgres implementation
  level** (e.g. whether a UNIQUE constraint happens to be backed by a
  particular index internally) — this tool deliberately never reasons at
  that level, consistent with decision 2's stance on Postgres internals.

---

## Decision 5 — A cross-object pass, separate from per-identity classification

**The decision.** A second pass specifically checks: did the other branch
destroy (drop a table, drop a column) something this branch's operation
still depends on — a foreign key's target, an index's covered columns?

**Alternatives considered.** Extending the per-identity classifier to catch
this. Rejected: it's structurally impossible there — a table drop and a
column-add-to-that-table touch two *different* ids (the table's, and the
column's), so grouping by identity never puts them in the same bucket to
compare. This needed its own separate mechanism, not a wider version of the
existing one.

**Reasoning and trade-offs.** Runs the same check at two scales (a whole
table, or a single column) rather than two separate algorithms — the column-
level version costs almost nothing extra once the table-level version
exists. When triggered, only one resolution is offered: the drop wins, and
the dependent object gets a corrective drop synthesized alongside it.
"Undo the drop instead, keep my new column" is deliberately *not* offered,
even though a user might reasonably want it — honoring that choice would
mean resurrecting a dropped table/column from nothing, and this tool keeps
no copy of what a drop destroyed. Rather than leave a resolution option in
the UI that can't mechanically work, it was removed from the choices
entirely instead of built as a broken promise.

**What was deliberately cut.** Retaining a snapshot of every dropped
object specifically so a future "undo the drop" resolution could be built —
cut because it would mean the DAG carrying dead weight (data for objects
that no longer exist) for a feature not in this project's actual scope.

---

## Decision 6 — A structural guardrail, not a documented convention

**The decision.** The only thing that can finalize a real conflict's
resolution is a `HumanConfirmationToken` — a one-time-use object only the
function that blocks on real terminal input can create. Nothing else,
including the LLM-explanation helper, is allowed to manufacture one, and
this is enforced by a static import-boundary check, not just a comment.

**Alternatives considered.** Trusting call sites to "just always call the
confirmation step before committing" as a documented convention, without a
structural mechanism forcing it.

**Reasoning and trade-offs.** The convention-only approach is strictly less
code, but the actual failure mode being guarded against — an automated
system silently picking the wrong side of a real schema conflict — is bad
enough that "please remember to ask" isn't a strong enough guarantee. This
mirrors how Git itself handles text merge conflicts: it refuses to guess
and forces a human to resolve the markers, rather than trusting every
caller to remember to check. The cost: a real state-tracking layer (a
spent-nonce set, to reject a replayed or stale token) that a convention-only
design wouldn't need at all.

**What was deliberately cut.** Any path for the LLM explainer to influence
which resolution gets chosen — it can describe what each side probably
intended, in plain English, and that's the entire extent of its role. It
was never given a way to propose a ranked "best" resolution, on purpose,
because that's one step away from quietly becoming a decision-maker.

---

## Decision 7 — Two real bugs, found only by running the tool for real

Not a design decision, but the reasoning behind treating "run the real CLI
end to end" as a genuinely different check from "the unit tests pass,"
worth recording because both bugs would have shipped past every existing
unit test:

- **A merge's own history could double-apply a drop.** The merge node
  originally stored a full copy of everything both branches did — simpler
  to write, but any drop already reachable through one branch's own parent
  chain got applied a second time during replay, and this project's code
  doesn't tolerate deleting something twice. Cut in favor of: a merge node
  stores only what it genuinely had to newly decide.
- **Replaying history could silently corrupt its own permanent record.**
  Because of how column data was stored during replay, running the same
  branch's history through replay more than once (which happens naturally —
  every CLI command replays history first to resolve names) was mutating
  the *original* stored operation in place, duplicating columns on every
  later replay. Fixed by copying data on the way in rather than handing out
  a live reference to the permanently stored version.

Both were found by running real, multi-step CLI scenarios and watching them
fail — not by writing more synthetic unit tests. This is why every sub-phase
of this build included an actual end-to-end CLI run, not just a green test
suite, before being considered done.

---

## Prior art (researched, not guessed)

| Tool | Handles rename identity? | Handles 3-way merge? |
|---|---|---|
| Rails migrations | No — merging is a plain Git text-merge on a generated file. No semantic awareness at all. | No — no diff/merge concept beyond what Git already does to text. |
| Alembic (SQLAlchemy) | No — its own docs state a rename is read as a delete + an add. | Partial — merges the migration *graph*, not schema *semantics*. |
| Atlas / Liquibase / pg-schema-diff | No — two-way structural diff only. | No — compare-and-sync, no branching/merge concept. |
| Django `makemigrations` | Yes — the closest existing solved analog: heuristic-matches a candidate rename, prompts the developer to confirm. | N/A — single-timeline tool, no branches. |
| PlanetScale | No — public merge algorithm is framed purely in add/drop/create, no rename identity in the public model. | Yes — the closest existing solved analog for real three-way schema merging. |
| Neon | No — branches storage (copy-on-write WAL pointers), not schema operations; its "Schema Diff" feature is a read-only line-by-line SQL text diff between two points in time. | No — solves a different problem entirely (cheap, fast point-in-time database copies). |

Nobody combines Django's answer to the rename problem with PlanetScale's
answer to the merge problem. That combination is the gap this project fills.

---

## Out of scope, on purpose

- **Row data** — this tool version-controls the shape of a database, never
  what's inside it.
- **Rollback** — undoing an applied migration isn't handled.
- **More than two branches merging at once** — always exactly two.
- **Reconciling a live, already-migrated database against a newly merged
  history** — this tool assumes a clean baseline to apply DDL against;
  bridging a messy live database into that state is a separate, later
  problem, not solved here.
- **The LLM ever deciding a merge on its own** — explicitly, permanently
  rejected. Explaining and suggesting, yes. Deciding, never.
