# Walkthrough 4 — dropping something another branch is still using

One branch drops an entire table. Independently, another branch adds a column to
that very same table, having no idea it's about to be dropped elsewhere. Walkthrough
2's conflict detection can't see this at all — a table-drop and a column-add are two
completely different identities (the table's own id vs. the new column's id), so
they never land in the same per-identity comparison. This needs a separate check,
and it resolves in a fundamentally different way than a normal conflict: there's no
a/b/both choice, because "undo the drop" isn't something this tool can actually do.

## Setup: a table, then one branch drops it while another adds to it

```
$ schemavcs init
initialized empty schemavcs repo at /tmp/schemavcs_walkthrough_04/.schemavcs

$ schemavcs migrate create-table legacy_reports
created table 'legacy_reports' (92ac9784cde1)

$ schemavcs branch create branch-a
created branch 'branch-a' from 'main' at 92ac9784cde1, switched to 'branch-a'

$ schemavcs migrate drop-table legacy_reports
dropped table 'legacy_reports' (d4eaf1432fff)

$ schemavcs checkout main
switched to branch 'main'

$ schemavcs branch create branch-b --from main
created branch 'branch-b' from 'main' at 92ac9784cde1, switched to 'branch-b'

$ schemavcs migrate add-column legacy_reports notes text
added column legacy_reports.notes (4f7cbc1671d3)
```

## Merge — a real cross-object conflict, acknowledged (not a/b/both)

```
$ schemavcs checkout branch-a
switched to branch 'branch-a'

$ schemavcs merge branch-b --into branch-a <<< ""
Conflict on identity 01c3d1cd-10e0-4d71-91f1-1b396f8a0652: branch A dropped table 'legacy_reports' that another branch's operation still references
The dropped table/column wins; the dependent object above will also be dropped. Press enter to acknowledge. merged 'branch-b' into 'branch-a' at 6369401b9a3f (1 conflict(s) resolved)
```

Written out on separate lines (the piped-empty-input capture ran the prompt and the
result together above), the actual prompt reads:

```
Conflict on identity 01c3d1cd-10e0-4d71-91f1-1b396f8a0652: branch A dropped table 'legacy_reports' that another branch's operation still references
The dropped table/column wins; the dependent object above will also be dropped. Press enter to acknowledge.
```

There's no `[a]/[b]/[both]` choice here, unlike walkthrough 2. That's deliberate:
the only mechanically sound resolution is "the drop wins" — "undo the drop instead"
would mean resurrecting `legacy_reports` and its lost column definitions from
nothing, which this tool has no way to do (dropping something doesn't preserve a
copy of what it looked like). So the merge acknowledges what's about to happen and
does it: the table stays dropped, and branch-b's `notes` column — which depended on
a table that no longer exists — gets dropped right along with it.

```
--- schemas/branch-a.schema ---
--- end schemas/branch-a.schema ---
```

The schema file is empty afterward — `legacy_reports` really is gone, and nothing
references it anymore.

## How this differs from walkthrough 2's conflict

| | Walkthrough 2 (rename vs. rename) | Walkthrough 4 (drop vs. add) |
|---|---|---|
| What's colliding | Two edits to the **same** column id | A table-drop and a column-add on **different** ids (table vs. its own new column) |
| Detected by | Per-identity classification | The separate cross-object pass |
| Resolution offered | Keep A / keep B / keep both | Acknowledge — the drop always wins, the dependent object is dropped too |
| Why no a/b/both here | Because "keep the add, undo the drop" would require resurrecting a dropped object from nothing, which isn't something this tool can do |
