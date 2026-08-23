# Walkthrough 10 — PARTIAL_CONFLICT: a bundled edit, agreeing on one field, disagreeing on another

`rename-column` + `alter-column-type` on the same column is one bundled edit — a
rename and a retype, both about the same identity. When both branches make the
*same* rename but *different* retypes, the classifier is built to notice that the
rename part isn't actually in dispute — only the type is (`merge/classify.py`'s
`_classify_compound_pair`, `Classification.PARTIAL_CONFLICT`). This walkthrough
shows what that looks like for real, including a real gap in how it's resolved.

## Setup: same rename, different retype, on both branches

```
$ schemavcs init
initialized empty schemavcs repo at /tmp/schemavcs_walkthrough_10/.schemavcs

$ schemavcs migrate create-table users
created table 'users' (ed6fcf113cad)

$ schemavcs migrate add-column users email string
added column users.email (e9e22f0ccbbf)

$ schemavcs branch create branch-a
created branch 'branch-a' from 'main' at e9e22f0ccbbf, switched to 'branch-a'

$ schemavcs checkout main
switched to branch 'main'

$ schemavcs branch create branch-b --from main
created branch 'branch-b' from 'main' at e9e22f0ccbbf, switched to 'branch-b'

$ schemavcs migrate --branch branch-a rename-column users email contact_email
renamed column users.email -> contact_email (2dd37e45e46e)

$ schemavcs migrate --branch branch-a alter-column-type users contact_email text
altered users.contact_email type -> text (03203bbe2801)

$ schemavcs migrate --branch branch-b rename-column users email contact_email
renamed column users.email -> contact_email (69fb9dac2c52)

$ schemavcs migrate --branch branch-b alter-column-type users contact_email varchar
altered users.contact_email type -> varchar (cfcd367314a5)
```

Both branches renamed `email` to the exact same new name, `contact_email` — that part
was never really in dispute. They picked different types (`text` vs `varchar`).

## Merge

```
$ schemavcs checkout branch-a
switched to branch 'branch-a'

$ schemavcs merge branch-b --into branch-a <<< "a"
Conflict on identity 5cf2fab5-514b-44a0-b17f-7d621049e37a: compound edits disagree on: type
Keep [a]/[b]/[both]? merged 'branch-b' into 'branch-a' at bd945bfe9f28 (1 conflict(s) resolved)
```

The reason line correctly says `disagree on: type` — not "these two bundles don't
match" — proof `_classify_compound_pair` really did decompose the bundle field by
field and correctly saw the rename as agreed. Final state:

```
contact_email text
```

## The real gap this surfaces

Look closely at the prompt: it's still the plain `Keep [a]/[b]/[both]?` — the exact
same generic prompt an ordinary whole-object CONFLICT gets. The design intent
written into the plan before any code existed (§C.4) was specifically to avoid
re-litigating a field both sides already agreed on — only the disagreeing field
(`type`, here) was supposed to need a human decision, with the agreed rename applying
automatically regardless of which side got picked.

That narrower behavior isn't actually wired up. `ClassifiedGroup.agreed_fields` and
`.conflicting_fields` are computed correctly by `classify.py` (you can see it in the
accurate reason string above), but `merge/engine.py` and `merge/resolve.py` never
read either field — `PARTIAL_CONFLICT` is routed through the exact same
`auto_resolve` → `None` → generic `confirm_from_cli` → whole-bundle `chosen_resolution`
path as an ordinary `CONFLICT`. Choosing "a" or "b" here keeps that *entire branch's*
bundle for this identity, not just its answer to the disputed field.

In this specific example the end result is still correct, because both branches
happened to bundle the exact same rename with their disagreeing retype — so keeping
"a" wholesale still keeps the (identical) agreed rename along with it. But the
narrower, field-level resolution the design called for isn't there: a human is asked
to re-decide something that was never actually in question, and if a future case ever
bundled the agreed field differently between the two sides (not just "the same value
twice"), picking a whole side could silently lose the other side's own contribution
to that already-agreed field. Documented as decision log entry 34 — a real
implementation gap between what was designed and what actually shipped, not a bug in
what's there, but worth fixing before leaning on this classification's promise.
