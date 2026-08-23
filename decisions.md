# Decisions

This explains *why* the tool works the way it does — not a changelog, a
walkthrough of the real questions that came up and the reasoning behind each
answer. Every example below is a real scenario the tool actually handles (see
`DB-version-Control/docs/walkthroughs/` for the captured terminal sessions).

---

## 1. What problem is this actually solving?

Git version-controls *text*. This version-controls a database *schema* — the
shape of it (tables, columns, types, constraints, indexes), not the rows
inside it. The goal: branch a schema, let two people evolve it independently,
then merge their branches back together — the same workflow as branching
code, but for `CREATE TABLE` instead of `.py` files.

Two things make this genuinely hard, and neither is solved well by anything
that already exists:

**Hard part 1 — a rename looks identical to a delete-plus-add.**
If branch A renames `email` to `contact_email`, and you only look at the
before/after schema, you see one column disappear and a different one
appear. Nothing in that picture says "this is the same column, just
renamed" versus "someone deleted `email` and separately added an unrelated
`contact_email`." Get this wrong during a merge and you'll either silently
lose a rename or wrongly flag a non-conflict as one.

**Hard part 2 — merging two branches' changes isn't just combining two lists.**
Branch A and branch B each make their own changes since they diverged. Some
of those changes are safe to combine automatically (they don't touch the
same thing). Some are safe even though they *do* touch the same thing
(they agree, or they touch different, non-overlapping parts of it). And
some are real conflicts — two people made incompatible decisions about the
same thing, and a machine has no business silently picking one.

**Where existing tools stand on these two problems:**

| Tool | Handles the rename problem? | Handles the merge problem? |
|---|---|---|
| Rails migrations | No — merging two migration histories is just a Git text-merge on a generated file. No understanding of what changed. | No — no merge concept at all beyond what Git already does to text. |
| Alembic (SQLAlchemy) | No — its own docs say a rename is read as a delete + an add. | Partial — it can merge two migration *chains* into one graph, but that's bookkeeping, not understanding what each side actually changed. |
| PlanetScale | No — their public merge algorithm talks entirely in terms of add/drop/create; there's no concept of "this is the same thing, renamed." | Yes — this is genuinely the best public example of a real three-way schema merge, and this project's own merge classification is directly modeled on it (more below). |
| Django `makemigrations` | Yes — this is the closest real solution to the rename problem: when it sees a delete and an add that look similar, it asks the developer "did you rename X to Y?" | N/A — Django doesn't have branches or merging at all; it's a single-timeline tool. |

Nobody combines Django's answer to problem 1 with PlanetScale's answer to
problem 2. That combination — rename detection that survives branch
divergence, feeding a real three-way schema merge — is the actual gap this
project fills.

---

## 2. Why does every table/column/index get its own made-up ID?

**The decision:** the moment you create a table or column, it gets a UUID.
That UUID is the column's *real* identity for the rest of its life — even
across a rename, even across two branches that have never talked to each
other. Names are just a label; the UUID is what merges actually key off of.

**Why not just use Postgres's own internal bookkeeping (`oid`, `attnum`,
etc.)?** Those exist, but none of them are built to survive what this tool
needs: two *disconnected* copies of a schema, independently evolving, that
later need to recognize "we're both talking about the same column." Postgres
recycles those internal ids over time and never designed them to be
compared across two separate catalogs. This isn't a case of "there's a
clever trick we're missing" — it's a structural gap in what Postgres's own
ids are for.

**Concrete example:** branch A renames `email` → `contact_email`. Branch B,
independently, adds a completely unrelated new column also named
`contact_email`. If identity were name-based, the merge would think these
are the same thing. Because each one actually got its own UUID the moment it
was created, the tool knows immediately these are two different columns
that happen to collide on a name — see decision 8 below for how that
specific case gets resolved.

---

## 3. How do you tell a real rename from "this just happens to look similar"?

**The decision:** score every plausible old-column/new-column pair, and only
propose a rename when both sides clearly, unambiguously prefer each other.

This only comes up in the second way of authoring changes — editing the
schema file directly and letting the tool figure out what happened (see
decision 6). The scoring formula:

```
score = 0.45 × (how similar are the names)
      + 0.25 × (how compatible are the types — e.g. string→text is close, string→int isn't)
      + 0.15 × (do they share constraints, like both being unique or both nullable)
      + 0.15 × (are they in roughly the same position in the file)
```

**Why not just match same-looking types and call it done?** Because the most
common real-world rename *also* changes the type — someone renames
`subscription_type: string` to `plan_type: enum` in the same edit, tightening
free text into a fixed set of choices. If you require the type to match
exactly, you'd miss this — the single case this project's own brief calls
out as the one it has to get right.

**Why require *both* sides to agree, not just "close enough"?** Picture a
column `full_name` getting split into `first_name` and `last_name`. A naive
scorer might see `full_name` is "somewhat similar" to `first_name` and guess
it was renamed there — which is wrong, it was split into two columns. By
requiring `full_name`'s best match to *also* think `full_name` is its own
best match back, this exact wrong guess never happens: neither `first_name`
nor `last_name` "wins" clearly enough, so the tool correctly gives up and
treats it as an honest delete-and-two-adds instead of guessing.

**What happens when a human says no?** If the tool proposes `x → y` and the
answer is "no, wrong guess," `x` and `y` don't get thrown away as instant
drop/add — they go back into the pool and get compared against whatever
else is still unmatched. Only once something has been checked against every
remaining candidate and nothing fits does it finally become a plain drop or
plain add.

**A known, accepted blind spot:** if someone swaps two columns' names and
changes absolutely nothing else about them — same type, same constraints,
same position — there is no signal anywhere in the file that anything
happened. No algorithm that only reads file contents can catch this; it's
documented as an accepted limitation, not something worth over-engineering
around.

**A second, more subtle blind spot found while testing this for real:**
if two renames happen in the same edit and they're *individually* confident
but not confident enough relative to each other (the gap between the best
match and the second-best match is too small), the tool currently says
nothing at all — no prompt, no "this looked uncertain" note, it just quietly
treats both as plain drops and adds. The end result is still correct (the
right columns end up with the right names either way), but the *history*
loses the fact that a rename happened. This is a real, documented trade-off:
warning about every near-miss would add noise to the common case just to
cover a rarer one.

---

## 4. Why did every conflict decision go through a token, not just a yes/no?

**The decision:** the only thing that can actually finalize a conflict
resolution is a `HumanConfirmationToken` — a one-time-use object that can
only be created by the function that blocks on real terminal input. Nothing
else in the codebase, including the LLM-explanation helper, is allowed to
manufacture one.

**Why go this far, instead of just trusting the code to "remember" to ask?**
Because the actual failure mode being guarded against — an automated system
silently picking the wrong side of a real schema conflict — is bad enough
that "please remember to ask" isn't a strong enough guarantee. A merge that
silently drops someone's intended change is far worse than the extra work of
building a real enforcement mechanism. This is the same reasoning Git itself
leans on for merge conflicts in text: it refuses to guess, and forces a human
to resolve the markers.

**Where does the AI actually fit in, then?** Strictly as an explainer, never
a decision-maker. When a real conflict comes up, the LLM's only job is to
read both sides and describe in plain English what each branch was probably
trying to do — never to pick a winner. The interface is written so that a
completely different LLM provider could be swapped in later with a one-line
config change, and it structurally can't import the code that actually
commits a resolution.

---

## 5. How does a merge actually decide what's safe to auto-combine?

**The decision:** group every operation from both branches by what it
actually touches (which table, which column), then classify each group.
This is directly modeled on PlanetScale's own published merge algorithm —
verified against their real blog post, not assumed — which classifies every
pair of changes into four buckets: invalid (a real conflict), valid-but-
order-dependent (also a conflict, since the result would differ depending on
who merges into whom), valid-and-order-independent (safe), or identical
overlap (also safe, just redundant). This project's own classification
values map onto that almost exactly:

- **Same thing done on both sides** (e.g. both branches made `email`
  required) → nothing to ask, just keep it once.
- **Different, non-overlapping things done to the same column** (branch A
  renamed it, branch B separately made it non-nullable) → both changes are
  kept, automatically — neither one actually contradicts the other.
- **Genuinely incompatible decisions** (branch A says the column is now a
  `decimal`, branch B says it's now a `varchar`) → this is a real conflict, a
  human has to pick.
- **A bundled edit that's half-agreed** (both branches renamed the same
  column to the same new name, but picked different new types) → the tool
  correctly *recognizes* that only the type is actually in dispute — but
  honestly, this is where the implementation currently falls short of the
  design: it still asks the human to re-approve the entire bundle (including
  the part that was never in question) instead of just the disputed piece.
  Documented as a known gap rather than quietly worked around, because
  fixing it properly means changing how the merge engine resolves things,
  not just relabeling a prompt.

**Where PlanetScale's own model has a gap this project had to fill on its
own:** none of PlanetScale's public description mentions renames at all —
their model only knows about add/drop/create. So the classification above
had to be extended with an explicit "one side deleted this, the other side
changed it" rule (always a conflict, regardless of *what* the other side
changed — retype, rename, or nullability, it's the same underlying problem:
you can't safely combine "get rid of this" with "here's a change to it").

**A conflict that per-identity comparison structurally can't see:** branch A
drops an entire table; branch B, independently, adds a column to that same
table. These touch *different* ids (a table's id, and a column's id), so the
grouping step above never even notices them as related. A second pass walks
every reference — a foreign key's target, an index's columns — and checks
whether the other branch destroyed something it depends on. Only one
resolution is offered when this happens: the drop wins, and the dependent
thing gets a corrective drop too. "Undo the drop instead" is deliberately
*not* offered — the tool never keeps a copy of what a drop destroyed, so
there's nothing to bring back. Rather than leave a resolution option in the
UI that can't actually work, it was removed from the choices entirely.

**A real UX bug found and fixed while writing this document:** the merge
prompt used to offer `Keep [a]/[b]/[both]?` for every kind of conflict,
including ones where "both" doesn't mean anything — a column's type is a
single value, it can't be `decimal` *and* `varchar` at once. "Both" was
silently just applying whichever change happened to replay second and
calling that the answer, dressed up as if a real three-way choice had been
offered. Fixed so that a conflict over one single-valued field only ever
offers a genuine `[a]/[b]` choice — "both" only stays on the table for the
one conflict shape where it's actually meaningful (a delete competing
against a real, separate change, not two proposed values for the same
field).

---

## 6. Why are there two completely different ways to make a change?

**The decision:** the tool supports both an explicit-verb CLI (`schemavcs
migrate rename-column users email contact_email`) *and* editing the tracked
schema file directly and running `sync`, which diffs your edit and figures
out what you meant.

**Why build both instead of picking one?** Because they solve two different
problems, and building them in that order made the harder problem
independently testable:

- The CLI-verb path has **zero rename ambiguity by construction** — if you
  type `rename-column`, there's no guessing involved, the human already told
  the tool exactly what happened. This let the merge engine (the genuinely
  hard, novel part) get built and fully tested against real branch/merge
  scenarios *before* the rename-detection heuristic existed at all.
- The file-edit path is the realistic day-to-day workflow — nobody wants to
  type a CLI verb for every column change, they want to edit a schema file
  like a normal person and have the tool figure out the rest, the way
  Django's `makemigrations` already does for a single timeline.

**The strongest proof they're actually interchangeable:** a change detected
by editing a file on one branch, merged against a change authored via a
direct CLI verb on a different branch, runs through the *exact same* merge
and DDL-emission code — no special-casing either path. Both authoring
methods just produce the same underlying operations; the merge engine has no
idea, and no need to know, which one produced what it's looking at.

---

## 7. What did testing this against the real CLI find that the design missed?

Several real bugs only surfaced by actually running the tool against real
multi-step scenarios, not by writing more unit tests against hand-built
data. Worth calling out because they're the kind of bug that a
"looks correct on paper" review wouldn't catch:

- **A merge could double-apply a table drop.** Early on, a merge's own
  history recorded a full copy of everything both branches did — simpler to
  write, but it meant a drop already reachable through one branch's own
  history got applied a *second* time during replay, and code doesn't
  tolerate deleting something twice. Fixed by having a merge only record
  what it genuinely had to decide, not a redundant copy of everything.
- **Replaying history could quietly corrupt its own permanent record.**
  Because of how column data was being stored during replay, running the
  same branch's history through the replay logic more than once (which
  happens naturally — every CLI command replays history first to resolve
  names) was silently mutating the *original* stored operation, duplicating
  columns every time it happened again. Fixed by copying data on the way in,
  never handing out a live reference to the permanently stored version.
- **A CLI-authored column never got a real position.** Every column added
  through the direct CLI verb defaulted to position zero — which quietly
  degraded the rename detector's position-similarity signal for any table
  with more than one CLI-authored column, without ever crashing or
  complaining. Found only by running the actual detector against a
  real two-column table, since every existing test had either used one
  column or built test data by hand with explicit positions already set.

None of these were found by asking "does this look right" — they were found
by actually running the tool end to end and watching it fail, which is the
same reason this project treats "run it for real" as a genuinely different
kind of check than "the unit tests pass."

---

## Out of scope, on purpose

- **Row data** — this tool version-controls the shape of a database, never
  what's inside it.
- **Rollback** — undoing a migration once applied isn't handled.
- **More than two branches merging at once** — always exactly two.
- **A live, already-partially-migrated database reconciling against a newly
  merged history** — this tool assumes a clean baseline to apply DDL against;
  bridging a messy live database into that state is a different, later
  problem.
- **Understanding what's actually inside a CHECK constraint** — stored and
  passed through as an opaque string, never parsed or reasoned about. Real
  expression parsing was judged disproportionate scope for what this project
  needs to demonstrate.
- **The LLM ever deciding a merge on its own** — explicitly, permanently
  rejected. Explaining and suggesting, yes. Deciding, never.
