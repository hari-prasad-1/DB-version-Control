# Test run — for review

How to run this yourself:

```
poetry run pytest -v
```

Result as of this run: **95 passed, 0 failed.**

```
============================== 95 passed in 0.16s ==============================
```

Below is every test, grouped by what it's actually checking, in plain language. Each
one says: what scenario it sets up, what it expects to happen, and why that matters.

---

## Core data types (`test_model_types.py` — 8 tests)

Just "do the basic building blocks hold the data they're supposed to." No logic yet,
just shapes: a `Column` remembers its name, its type, whether it's nullable; a `Table`
holds columns/indexes/constraints; every one of the 13 migration operation types
(add column, drop table, rename column, etc.) can actually be constructed with real
values. This is the foundation everything else sits on.

| Test | Proves |
|---|---|
| `test_type_spec_str` | `TypeSpec("string", (255,))` prints as `string(255)` — the DDL/DSL text representation is right |
| `test_column_construction` | A `Column` holds id, name, type, nullable, default |
| `test_index_and_constraint_construction` | Same for `Index` and `Constraint` |
| `test_table_construction` | A `Table` holds its columns/indexes/constraints |
| `test_snapshot_construction` | A `Snapshot` (a branch's full state at one point in time) holds its tables |
| `test_operation_variants_constructible` | All 13 operation types can be built |
| `test_compound_operation` | Multiple operations can be bundled as "one edit" |
| `test_migration_node` | A `Migration` (one commit) knows its parents and whether it's a merge |

---

## The DAG — branch history and merge-base (`test_dag_walk.py` — 10 tests)

This is the git-like history graph. The single hardest piece here is **merge-base**:
given two branches that diverged, find the exact point they diverged from. Get this
wrong and merges either miss real changes or re-flag changes that were already
agreed on.

| Test | Scenario | What it proves |
|---|---|---|
| `test_ancestors_simple_chain` | r1 → r2 → r3 | Walking backwards from r3 finds all of r1, r2, r3 |
| `test_merge_base_simple_siblings` | root, then branch-a and branch-b both fork from it | The shared point is correctly found as `root` |
| `test_merge_base_fork_then_advance_past` | branch-a forks at r3; **main keeps moving** to r4, r5, r6 afterward | The shared point is still correctly r3, not wherever main happens to be now — this is the case a naive "just look at where main is" approach gets wrong |
| `test_merge_base_self` | merging a branch with itself | Shared point is itself, trivially |
| `test_merge_base_criss_cross_raises` | branch-a and branch-b are merged into each other **in both directions** before either continues | No single correct shared point exists — the tool refuses with a clear error instead of silently guessing and possibly dropping real changes |
| `test_merge_base_not_criss_cross_does_not_raise` | A second, later merge of the same two branches (not a real criss-cross) | Correctly does NOT raise — only genuine ambiguity should trigger the error |
| `test_is_fast_forward` | One branch's history entirely contains the other's | Correctly detected as "fast-forward" (no real merge needed, just move the pointer) |
| `test_operations_since_simple_chain` | Walking a plain chain | Returns exactly the operations added along the way |
| `test_operations_since_through_merge_node_follows_correct_parent` | Walking through a merge commit | Follows the correct parent, doesn't double-walk |
| `test_replay_through_merge_node` | Two branches each add a different column, then merge | Replaying the merged history shows **both** columns — proves history reconstruction correctly visits both sides of a merge, not just one |

---

## Merge classification — what kind of change is this? (`test_merge_classify.py` — 15 tests)

This is the "how do two branches' changes to the *same thing* relate to each other"
logic — the actual merge decision engine, before anything gets asked of a human.

| Test | Scenario | Verdict |
|---|---|---|
| `test_unrelated_only_one_branch_touched` | Only one branch touched this column | `UNRELATED` — nothing to reconcile |
| `test_identical_op_both_sides_dedupe` | Both branches made the exact same change | `IDENTICAL` — keep one copy, not two |
| `test_add_column_same_everything_dedupe` | Both branches added the identical column | `IDENTICAL` |
| `test_add_column_different_type_conflict` | Both branches "added" the same column id but with different types | `CONFLICT` — a human must pick |
| `test_rename_to_different_names_conflict` | Branch A renames `x`→`y`, branch B renames `x`→`z` | `CONFLICT` |
| `test_rename_vs_drop_conflict` | One branch renamed it, the other deleted it | `CONFLICT` — can't reconcile "keep it as this new name" with "it's gone" |
| `test_drop_vs_any_mutation_generalized_conflict` | One branch deletes it, the other changes *anything* about it | `CONFLICT`, no matter which specific edit the other branch made |
| `test_alter_type_same_target_dedupe` | Both branches changed the type to the *same* new type | `IDENTICAL` |
| `test_alter_type_different_target_conflict` | Both branches changed the type, but to *different* new types | `CONFLICT` |
| `test_nullability_same_target_dedupe` | Both branches made a column required (or both optional) | `IDENTICAL` |
| `test_nullability_different_target_conflict` | One branch made it required, the other made it optional | `CONFLICT` |
| `test_drop_table_both_sides_dedupe` | Both branches dropped the same table | `IDENTICAL` — already agreed, don't ask twice |
| `test_partial_conflict_agreed_rename_disagreed_retype` | Branch A does "rename AND retype" in one edit; branch B does "rename to the same new name AND retype to something else" | `PARTIAL_CONFLICT` — the rename is auto-approved since both sides already agree, only the retype gets flagged to a human. **This is the "don't make someone re-approve what they already agreed on" case.** |
| `test_compound_edits_agree_on_every_field_commuting` | A bundled edit where every individual field matches on both sides | `COMMUTING` — fully auto-mergeable |
| `test_rename_plus_retype_vs_unrelated_add_index_is_commuting` | One branch renames+retypes a column; the other adds an index that doesn't touch either of those fields | `COMMUTING` — genuinely non-overlapping, no conflict |

---

## Cross-object conflicts — "you dropped the thing I'm still using" (`test_cross_object.py` — 8 tests)

Classification above only catches conflicts on the *same* id. This catches a
different shape entirely: branch A drops a whole table; branch B, completely
unaware, adds a column (or foreign key, or index) that points at that same table.
Nothing in the per-id classification above would ever notice this, because the two
operations are keyed by two different ids (the table's id vs. the new column's id).

| Test | Scenario | Proves |
|---|---|---|
| `test_drop_table_vs_add_constraint_referencing_it` | Branch A drops `orders`; branch B adds a foreign key from `users` to `orders` | Detected as a conflict, naming the dropped table |
| `test_drop_table_vs_add_column_referencing_it` | Branch A drops a table; branch B adds a column to it | Detected |
| `test_drop_column_vs_add_index_referencing_it` | Branch A drops a column; branch B adds an index that covers it | Detected — same check, one level smaller |
| `test_drop_column_vs_add_constraint_referencing_it` | Branch A drops a column; branch B adds a uniqueness constraint on it | Detected |
| `test_checked_symmetrically_both_directions` | Same scenario, but with A and B swapped | The check works no matter which side does the dropping |
| `test_unrelated_operations_produce_no_conflict` | Two branches each add a different, unrelated column | Correctly reports **no** conflict — this pass doesn't cry wolf |
| `test_incompatible_fk_collision_is_out_of_scope` | Two branches each add a *different* foreign key to the same table | Correctly **not** flagged — this is deliberately out of scope (two independent, valid additions, not a "something got destroyed" situation) |
| `test_preserves_existing_classified_groups` | Running this pass on top of classification's own output | Doesn't lose or overwrite anything classification already decided |

---

## Same-name collisions — two branches independently add a column with the same name (`test_merge_engine.py`, `test_phase1_demo.py`)

This is a case neither classification nor the cross-object pass can see at all: each
branch mints its own fresh id when it creates something, so "column `notes` added on
branch A" and "column `notes` added on branch B" are two *completely different*
columns under the hood, even though a human looking at the table would see one name
used twice — which is invalid, since a real table can't have two columns sharing a
name.

**The rule:** keep whichever one is closer to the point the branches diverged
(fewer commits since then); drop the later one; tell the human what happened and why,
so they can fix it themselves if that's not what they wanted.

This is exercised directly inside the end-to-end demo test below (branch-a's `notes`
column loses to branch-b's, because branch-b's was added earlier relative to the
fork point) and is reported back as a plain-English note: *"column 'notes' was
independently added on both branches -- the one from branch b was kept, the one from
branch a was dropped as a duplicate name, review if that's not what you wanted."*

---

## The human-confirmation guardrail (`test_merge_resolve.py` — 6 tests)

This is the safety mechanism that makes sure a real conflict can never sneak through
without an actual human decision — enforced by the code's structure, not just by
convention/discipline.

| Test | Proves |
|---|---|
| `test_auto_resolve_handles_safe_tiers` | The three "safe" verdicts (identical/commuting/order-irrelevant) resolve without asking anyone |
| `test_auto_resolve_returns_none_for_conflict` | Real conflicts correctly refuse to auto-resolve |
| `test_commit_resolution_rejects_non_token_values` | Passing anything other than a real confirmation token (e.g. a plain string) is rejected |
| `test_commit_resolution_rejects_token_for_wrong_group` | A token issued for one conflict can't be reused on a different one |
| `test_commit_resolution_rejects_stale_or_reused_token` | The same token can't be spent twice |
| `test_llm_package_never_imports_merge_resolve_or_engine` | Static check: the LLM explanation code physically cannot reach into the part of the code that finalizes a merge decision — it can only ever explain, never decide |

---

## LLM explanation stub (`test_llm_stub.py` — 3 tests)

The (offline, deterministic, no real AI involved yet) module that writes a
human-readable explanation of a conflict. Model-agnostic by design — this stub is a
placeholder any real provider slots in behind later without anything else changing.

| Test | Proves |
|---|---|
| `test_explain_returns_conflict_explanation` | Given a real conflict, produces a sensible, readable explanation naming the table/column |
| `test_explain_is_deterministic_and_offline` | Same input always gives the same output — no randomness, no network calls |
| `test_explain_falls_back_to_raw_id_when_identity_unresolvable` | If it can't find a name for something, it still degrades gracefully (shows the raw id) instead of crashing |

---

## The full merge engine, wired together (`test_merge_engine.py` — 9 tests)

This is where classification + cross-object + the guardrail + the DAG all actually
run together to produce a real merge commit.

| Test | Scenario | Proves |
|---|---|---|
| `test_merge_self_raises_nothing_to_merge` | Merging a branch into itself | Refused, as it should be |
| `test_merge_fast_forward_advances_pointer_without_new_node` | Merging a fresh branch that hasn't diverged yet | Just moves the pointer, no pointless empty merge commit |
| `test_merge_source_already_ancestor_raises_nothing_to_merge` | The branch being merged in has nothing new to offer | Refused |
| `test_merge_diverged_branches_auto_resolves_non_overlapping_columns` | Two branches each add a different column to the same table | Merges cleanly with **zero** questions asked — genuinely non-conflicting |
| `test_merge_conflict_requires_confirm_and_uses_chosen_resolution` | Both branches rename the same column, to different names | Requires a human decision, and the merge result is exactly whichever side the human picked |
| `test_merge_with_drop_table_on_one_side_replays_without_double_apply` | One branch drops an unrelated table while the other adds a column elsewhere | The merged history replays correctly — **this test exists because an earlier version of this code crashed here** (see "Bugs found and fixed" below) |
| `test_merge_cross_object_conflict_resolves_by_dropping_the_dependent_column` | Branch A drops a table; branch B added a column to it | The only sound resolution — the dependent column is dropped along with the table — and the merged history replays cleanly afterward |
| `test_merge_result_has_two_parents` | Any real merge commit | Correctly recorded as having **two** parents (both branches), not one |

---

## The CLI, end to end (`test_cli_migrate.py`, `test_cli_current_branch.py`, `test_cli_merge_and_ddl.py`, `test_model_sync.py` — 19 tests)

Proves the command-line tool itself — not just the internal engine — actually works:
creating branches, authoring migrations by name (`rename-column users subscription_type plan_type`,
not raw ids), merging, and emitting SQL, all driven the way a real user would.

Highlights:
- `test_author_migrations_and_rename_via_cli` — author a rename+retype through the
  actual CLI verbs and confirm the exact operations landed in history correctly.
- `test_merge_cmd_via_dispatch_fast_forward` / `test_full_pipeline_branch_diverge_merge_emit_ddl`
  — the full `branch → migrate → merge → emit-ddl` pipeline run exactly as a
  terminal user would type it.
- `test_schema_file_reflects_authored_migrations` / `test_schema_file_reflects_rename`
  — every CLI-authored migration keeps the human-readable `.schema` file in sync
  automatically (the Rails-`schema.rb`-style two-way sync).

---

## DDL generation (`test_ddl_toposort.py`, `test_ddl_emitter.py` — 13 tests)

Turning the final, merged operation list into actual SQL statements, in an order that
won't break (you can't add a foreign key to a table that doesn't exist yet; you can't
drop a table while something still references it).

| Test | Proves |
|---|---|
| `test_create_table_before_add_column_on_it` | A table is always created before anything is added to it |
| `test_create_table_before_fk_referencing_it` | A table exists before another table's foreign key points at it |
| `test_drop_column_before_drop_table` | A column is dropped before its table is dropped (not the other way around) |
| `test_circular_dependency_raises` | An impossible ordering (A needs B, B needs A) is detected and refused rather than silently guessed at |
| `test_create_table_with_columns` | Basic `CREATE TABLE` text is correct |
| `test_rename_column_and_alter_type_use_names_from_state` | `ALTER TABLE ... RENAME COLUMN` uses the actual column name, not a raw id |
| `test_add_foreign_key_constraint_depends_on_referenced_table_creation` | Foreign keys are emitted only after their target table exists |
| `test_dependency_ordering_is_applied_before_emission` | Even if operations are handed in the "wrong" order, the emitter fixes the order itself before generating SQL |

---

## The full Phase 1 demo — everything together (`test_phase1_demo.py` — 1 test)

**This is the big one — the proof that the whole chain holds together, entirely
through the CLI, exactly like a real user would do it.**

**Setup:**
- `main` has a `users` table with a `subscription_type` column, and an unrelated
  `legacy_reports` table.
- `branch-a` is created from `main`, and:
  - renames `subscription_type` → `plan_type`
  - changes its type to `enum`
  - adds a new column called `notes` (type `text`)
- `branch-b` is created from `main`, and:
  - adds a column *also* called `notes` (type `string`, different id — a genuine
    name collision, not the same column)
  - adds an unrelated `region` column
  - drops the unrelated `legacy_reports` table

**Then `branch-a` is merged with `branch-b`.**

**What's proven:**
1. **Zero human decisions were required** (`conflicts_resolved == 0`) — everything
   here is genuinely non-conflicting once you look closely, even though at a glance
   it looks like a lot happened on both sides.
2. **Exactly one note was surfaced** — the `notes` name collision — explaining in
   plain English which one was kept and which was dropped, and why.
3. **The final merged state is correct:** `legacy_reports` is gone, `plan_type`
   exists with type `enum` (not `subscription_type` anymore), `region` exists,
   and there's exactly one `notes` column (branch-b's, per the tie-break rule) —
   not two.
4. **The generated SQL is valid and in the right order:** `users` is created before
   its rename statement runs, and `legacy_reports`'s own creation still correctly
   precedes its drop, even walking the *entire* history including both branches
   and the merge itself.

If a confirmation prompt had been unexpectedly triggered anywhere in this scenario,
the test would fail immediately and loudly (`_fail_if_asked` raises on any surprise
request) — so passing this test is also proof that nothing here silently asked a
question it shouldn't have.

---

## Bugs found and fixed while building this test

Building the full end-to-end demo surfaced two real bugs that none of the smaller,
piece-by-piece tests had caught on their own — worth being upfront about, since this
is exactly the kind of thing an end-to-end test is supposed to catch:

1. **Same-name collisions were never actually implemented.** The design had always
   called for this (two branches independently adding a column with the same name),
   but no code existed for it yet. Added `merge/name_collision.py` plus the
   corrective-drop logic in the merge engine.

2. **Merging crashed on any merge involving a drop, once more than a plain
   add-only merge was tested.** The merge engine was re-storing operations in the
   merge commit that were *already* reachable through one of the two parent
   branches — so replaying history applied some operations twice (e.g. trying to
   delete an already-deleted table). Fixed in two places:
   - The merge engine now only stores genuinely new information in a merge commit
     (a real conflict's resolution), not a full copy of everything both branches did.
   - As a safety net, operations that target something already gone (e.g. adding a
     column to a table that's since been dropped by the other branch) now quietly
     do nothing instead of crashing — since by the time that's reached, the outcome
     has already been decided elsewhere.

Both are now covered by dedicated regression tests
(`test_merge_with_drop_table_on_one_side_replays_without_double_apply`,
`test_merge_cross_object_conflict_resolves_by_dropping_the_dependent_column`) so they
can't silently come back.
