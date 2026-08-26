# Decisions — the short version

8 calls I made building this. Each one: what I chose, in one line, with
an example. Full reasoning in `decisions.md`.

---

**1. Two ways to author a change.**
Either tell the tool directly (`migrate add-column users email string`), or
just edit the `.schema` file by hand and let the tool diff it against the
last known state to figure out what you did.
> Example: edit `users.schema`, add a `bio` column by hand, save. Tool
> detects it, asks you to confirm "add column bio", commits it.

**2. Every table/column/index gets a permanent internal ID.**
Names are just labels attached to that ID. This is *why* renames work.
> Example: rename `email` → `contact_email`. Internally it's still the
> same column ID — so a merge knows it's a rename, not "delete + add".

**3. Renames are detected by matching everything except the name.**
Old snapshot has a column gone, new snapshot has one appeared, same table,
same type/position/etc → it's a rename, not delete+create.
> Example: `email` (string, position 3) disappears, `contact_email`
> (string, position 3) appears → flagged as a rename automatically.

**Why this is the gap, not just a feature.** Most schema tools don't even
attempt this — Alembic's own docs say a rename is read as a plain
delete+add; Atlas/Liquibase/pg-schema-diff are two-way structural diffs
with no identity concept at all. Django's `makemigrations` is the closest
prior art (it heuristic-matches a likely rename and asks you to confirm),
but Django has no branches — it's one linear timeline, so it never has to
ask "did *two people, independently*, do something to what's really the
same column?" PlanetScale solves *that* half (real three-way schema
merge) but its public merge model is framed purely in add/drop/create —
no rename identity either. So the actual gap is: nobody has both halves
at once — an identity model *and* a branch/merge model that has to reason
about that identity across divergence. Makes sense why: each half is a
real, separately hard problem, and most tools only had reason to solve
one of them for their use case (Django: linear history is enough for a
single team; PlanetScale: branching databases don't need to preserve
column-level identity through a rename the way this does). Combining both
is the actual hard part I built for.

**4. Merge conflicts are classified, not guessed.**
Two branches touching the *same* thing differently = conflict, needs a
human. Two branches touching *different* things = auto-merge.
> Example: branch A renames `email`→`contact_email`, branch B adds an
> index on `email` → conflict (index refers to the old name). Branch A
> renames `email`, branch B adds an unrelated `phone` column → auto-merges.

**5. Object-level conflicts and cross-object conflicts are two separate
passes.**
First pass: did two branches touch the *same* column/table differently?
Second pass: did a *table*-level change (like a drop) break something a
*column*-level change on the other branch depends on?
> Example: branch A drops `users` table, branch B adds a column to
> `users` → object-level diff sees no shared column edit, but the
> cross-object pass catches "you're adding to a table that no longer
> exists."

**6. Rules are enforced in code, not just documented.**
E.g. "the LLM only explains conflicts, it never decides one" is an actual
function boundary, not a comment.
> Example: there's no code path where the summarizer's output can flip a
> conflict to auto-resolved — it can only produce text a human reads.

**7. Web UI is a thin layer over the same CLI functions — no parallel
engine.**
The web routes call the exact same `migrate_cmd.py` / `branch_cmd.py`
functions the CLI does.
> Example: `POST /migrate/add-column` in the browser runs the identical
> `migrate_cmd.add_column()` that `schemavcs migrate add-column` runs from
> a terminal. One engine, two front doors.

**8. Deleting a branch frees its name immediately — same as Git.**
The branch's *history* stays around (nothing is actually deleted), but the
*name* becomes reusable right away. A new branch with the old name starts
completely fresh, with no link to what used to be there.
> Example: delete `feature`, then `branch create feature` again → works,
> no error. It's a brand new branch from `main`, unrelated to the old
> `feature`'s history (which is still reachable by its old revision IDs,
> just not through this name anymore).
