# Decisions — the short version

10 calls I made building this. Each one: what I chose, in one line, with
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

**7. Bugs found by running it, not by reading it.**
Two real bugs only surfaced from actually exercising the tool end to end,
not from code review.
> Example: a `load()` bug where a deleted branch's last commit still
> claimed its old branch name, silently un-deleting it on reload — found
> by a round-trip save/load test, not by inspection.

**8. Web UI is a thin layer over the same CLI functions — no parallel
engine.**
The web routes call the exact same `migrate_cmd.py` / `branch_cmd.py`
functions the CLI does.
> Example: `POST /migrate/add-column` in the browser runs the identical
> `migrate_cmd.add_column()` that `schemavcs migrate add-column` runs from
> a terminal. One engine, two front doors.

**9. Deleting a branch frees its name immediately — same as Git.**
The branch's *history* stays around (nothing is actually deleted), but the
*name* becomes reusable right away. A new branch with the old name starts
completely fresh, with no link to what used to be there.
> Example: delete `feature`, then `branch create feature` again → works,
> no error. It's a brand new branch from `main`, unrelated to the old
> `feature`'s history (which is still reachable by its old revision IDs,
> just not through this name anymore).
>
> *(Earlier version of this tool permanently blocked reusing a deleted
> name — changed after using it made clear that's not what anyone expects.)*

**10. Rollback moves a branch's head backward — no reverse SQL.**
There's no live database to run `DROP COLUMN` against, so "rollback" just
means `git reset --hard HEAD~n`: move the pointer back, nothing is deleted.
> Example: `branch rollback main --steps 1` after adding a column just
> moves `main`'s head to the commit before that add — the add-column
> commit still exists, just nothing points at it as current anymore.

---

## Bonus: errors show up where you're looking, not as a crash page

Every web form (add column, delete branch, etc.) submits through a
background request instead of a normal page load. If you do something
invalid — unknown table, duplicate branch name, bad type — you get a
readable red message right under that form. You never get dumped onto a
raw `{"detail": "..."}` JSON page or a stack trace.
> Example: try to delete the branch you're currently on → inline message:
> *"cannot delete 'main': it's the current branch — checkout another
> branch first."* Page never navigates away.
