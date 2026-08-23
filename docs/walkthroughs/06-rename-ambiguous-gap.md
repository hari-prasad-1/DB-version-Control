# Walkthrough 6 — Phase 2: two candidates, and the ambiguous-gap rule

Walkthrough 5 showed the one-drop-one-add fallback: exactly one column vanished,
exactly one appeared, so it got proposed regardless of score. The moment there's a
*second* pair of columns changing in the same edit, that fallback no longer applies —
detection now depends entirely on similarity scoring, and scoring has a real failure
mode worth seeing directly: two plausible candidates that are too close in score to
tell apart.

## Setup

```
$ schemavcs init
initialized empty schemavcs repo at /tmp/schemavcs_walkthrough_06/.schemavcs

$ schemavcs migrate create-table accounts
created table 'accounts' (c52e265d965b)

$ schemavcs migrate add-column accounts first_name string
added column accounts.first_name (466b4201bb62)

$ schemavcs migrate add-column accounts last_name string
added column accounts.last_name (9ad86882b9be)
```

## Edit: rename both columns in the same style, same edit

```
$ cat > schemas/main.schema <<EOF
table accounts {
  column given_name: string
  column family_name: string
}
EOF

$ schemavcs sync
generated migration cd82c0c7d7c2 from /tmp/schemavcs_walkthrough_06/schemas/main.schema
```

No prompt at all. Compare that with walkthrough 5's output, which printed a
"Detected a possible rename" line before anything got committed — here, nothing was
ever proposed, and the tool just silently treated this as two drops and two adds.

The resulting state proves it: both columns did end up with sensible new names, but
not because anything was detected as a rename —

```
given_name string
family_name string
```

## Why nothing got proposed

Running the same four pairs through the scoring function directly
(`rename_detect/similarity.py`) shows what the detector actually saw:

```
first_name  -> given_name    0.820
first_name  -> family_name   0.720
last_name   -> given_name    0.700
last_name   -> family_name   0.795
```

`first_name`'s best match (`given_name`, 0.82) is correct, and so is `last_name`'s
best match (`family_name`, 0.795) — this is a genuine mutual-best-match pair, and both
scores clear `THRESHOLD_ACCEPT` (0.6) easily. The problem is the **gap** to the
runner-up: `first_name`'s gap between its best (0.82) and second-best (0.72) is only
0.10; `last_name`'s gap between its best (0.795) and second-best (0.70) is only 0.095.
`THRESHOLD_AMBIGUOUS_GAP` requires at least 0.15 — both pairs fall short of it, so
`_best_mutual_match` (`rename_detect/detector.py`) rejects both candidates as too
ambiguous to safely guess, and the whole table falls straight through to plain
drops and adds without ever calling `confirm`.

This is a real, documented consequence of an explicitly empirical scoring formula
(decision log entries 28-29) — the gap rule exists specifically to stop the tool from
guessing wrong when two candidates are this close, but the cost of that safety margin
is that a rename this clean-looking can still slip through undetected, with no
prompt and no visible sign anything was uncertain. Worth knowing about if a rename
seems to have silently "not happened" — check the git-diff-style output on the
`.schema` file (walkthrough 1) to see the actual before/after either way, since the
final schema state is correct regardless of whether the tool called it a rename or a
drop+add.

## The same shape, but far enough apart to resolve

Walkthrough 7 runs a similar two-candidate scenario where the gap clears the
threshold on both sides — showing what a real, resolvable ambiguous case looks like
end to end, including a rejection that puts a column back in the pool.
