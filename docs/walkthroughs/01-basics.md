# Walkthrough 1 — the basics

Init a repo, author migrations through the CLI, branch, rename+retype a column,
merge two branches with no conflicts, and emit SQL. Every command and every line
of output below is copied verbatim from a real run.

## 1. Initialize a repo

```
$ schemavcs init
initialized empty schemavcs repo at /tmp/schemavcs_walkthrough_01/.schemavcs
```

This creates `.schemavcs/` (the DAG, branch heads, current-branch pointer) and a
`schemas/` folder holding one plain-text `.schema` file per branch — the
human-readable, always-current model of what that branch's tables look like right
now. Right after `init`, `main`'s schema file is empty (there are no tables yet):

```
--- schemas/main.schema ---
--- end schemas/main.schema ---
```

## 2. Create a table and add columns

```
$ schemavcs migrate create-table users
created table 'users' (f7178a9ff058)

$ schemavcs migrate add-column users id uuid --not-null
added column users.id (b1bc1528f69f)

$ schemavcs migrate add-column users email string(255) --not-null
added column users.email (738c84b1eb1e)

$ schemavcs migrate add-column users subscription_type string(50)
added column users.subscription_type (224901ce025a)
```

Each of these is its own migration — its own node in the history graph, each one
identified by a content hash (the `(f7178a9ff058)` etc.), never a sequential number.
After all four, `schemas/main.schema` reflects the current state automatically:

```
table users {
  column id: uuid not_null
  column email: string(255) not_null
  column subscription_type: string(50)
}
```

Nobody had to run a separate "sync" step — every successful migration rewrites the
branch's schema file as a side effect.

## 3. Branch off main

```
$ schemavcs branch create feature-plan-rename
created branch 'feature-plan-rename' from 'main' at 224901ce025a, switched to 'feature-plan-rename'
```

Just like `git checkout -b`: a new branch pointing at main's current head, and the
CLI switches you onto it immediately.

## 4. Rename + retype a column on the new branch

```
$ schemavcs migrate rename-column users subscription_type plan_type
renamed column users.subscription_type -> plan_type (1d71eb84879f)

$ schemavcs migrate alter-column-type users plan_type enum
altered users.plan_type type -> enum (4b8f1659db1d)
```

This is the project's own running example: a column renamed *and* retyped. Because
`rename-column` is an explicit verb here — not something the tool has to guess at by
comparing two versions of a file — there's no ambiguity about what happened, at all.
`schemas/feature-plan-rename.schema` now shows:

```
table users {
  column id: uuid not_null
  column email: string(255) not_null
  column plan_type: enum
}
```

## 5. Switch back to main, make an unrelated change there

```
$ schemavcs checkout main
switched to branch 'main'

$ schemavcs migrate add-column users region string(10)
added column users.region (a7151a15eec7)
```

Now the two branches have genuinely diverged: `feature-plan-rename` renamed+retyped
a column; `main` independently added a different column. Neither branch knows about
the other's change yet. Here's exactly what diverged, as a real `diff -u` between
each branch's `.schema` file and the point they forked from:

```diff
--- main (at the fork point)
+++ main (now)
@@ -2,4 +2,5 @@
   column id: uuid not_null
   column email: string(255) not_null
   column subscription_type: string(50)
+  column region: string(10)
 }
```

```diff
--- main (now)
+++ feature-plan-rename (now)
@@ -1,6 +1,5 @@
 table users {
   column id: uuid not_null
   column email: string(255) not_null
-  column subscription_type: string(50)
-  column region: string(10)
+  column plan_type: enum
 }
```

(That second diff is a little misleading on its own — it makes it look like
`region` was removed, when really it's just that `main`'s copy has `region` and
`feature-plan-rename`'s copy doesn't, because `region` was never added there. A
plain two-file diff can't tell "removed" apart from "never had it" — that
distinction is exactly what the merge engine tracks properly by column id, not by
comparing schema text.)

## 6. Merge the branch back into main — clean, no conflicts

```
$ schemavcs merge feature-plan-rename --into main
merged 'feature-plan-rename' into 'main' at b49533d2147c (0 conflict(s) resolved)
```

`0 conflict(s) resolved` — nobody was asked anything, because nothing here actually
conflicts: one branch touched `subscription_type`/`plan_type`, the other touched
`region`, and those never overlap. The merged result:

```
table users {
  column id: uuid not_null
  column email: string(255) not_null
  column plan_type: enum
  column region: string(10)
}
```

Both branches' changes are present. `subscription_type` is gone (renamed), replaced
by `plan_type` with its new `enum` type, and `region` is there too. Diffing each
branch's pre-merge state against the merged result shows precisely what each side
actually contributed:

```diff
--- main (just before merge)
+++ main (merged result)
@@ -1,6 +1,6 @@
 table users {
   column id: uuid not_null
   column email: string(255) not_null
-  column subscription_type: string(50)
+  column plan_type: enum
   column region: string(10)
 }
```

```diff
--- feature-plan-rename (just before merge)
+++ main (merged result)
@@ -2,4 +2,5 @@
   column id: uuid not_null
   column email: string(255) not_null
   column plan_type: enum
+  column region: string(10)
 }
```

Read together: main's diff shows its own `subscription_type` line replaced by
`plan_type` (the rename+retype it never made itself, brought in from the other
branch), and feature-plan-rename's diff shows `region` newly appearing (the add it
never made itself, brought in from main). Each branch's diff against the merge
result shows exactly, and only, what the *other* branch contributed.

## 7. Emit DDL for main's full history

```
$ schemavcs emit-ddl --branch main
CREATE TABLE users ();
ALTER TABLE users ADD COLUMN id uuid NOT NULL;
ALTER TABLE users ADD COLUMN email string(255) NOT NULL;
ALTER TABLE users ADD COLUMN subscription_type string(50);
ALTER TABLE users RENAME COLUMN subscription_type TO plan_type;
ALTER TABLE users ALTER COLUMN plan_type TYPE enum;
ALTER TABLE users ADD COLUMN region string(10);
```

This walks the *entire* history — both branches and the merge — and prints valid,
correctly-ordered SQL. Notice the table is created empty and every column is added
one statement at a time, in the order it was actually authored; the rename and
retype show up as their own explicit statements, not as a diff against some other
version of the table.

## 8. Add a table, index, and foreign key

```
$ schemavcs migrate create-table organizations
created table 'organizations' (058d8ad86f99)

$ schemavcs migrate add-column organizations id uuid --not-null
added column organizations.id (cc42d933f37a)

$ schemavcs migrate add-column users org_id uuid
added column users.org_id (cc8df5e2c587)

$ schemavcs migrate add-index users idx_users_email --columns=email --unique
added index 'idx_users_email' on users(email) (344d87f8b8ca)

$ schemavcs migrate add-foreign-key users --columns=org_id --references=organizations
added foreign key users(org_id) -> organizations (b810bfd59acf)
```

```
table users {
  column id: uuid not_null
  column email: string(255) not_null
  column plan_type: enum
  column region: string(10)
  column org_id: uuid
  index idx_users_email on (email) unique
  foreign_key (org_id) references organizations
}

table organizations {
  column id: uuid not_null
}
```

```
$ schemavcs emit-ddl --branch main
CREATE TABLE users ();
ALTER TABLE users ADD COLUMN id uuid NOT NULL;
ALTER TABLE users ADD COLUMN email string(255) NOT NULL;
ALTER TABLE users ADD COLUMN subscription_type string(50);
ALTER TABLE users ADD COLUMN region string(10);
ALTER TABLE users RENAME COLUMN subscription_type TO plan_type;
ALTER TABLE users ALTER COLUMN plan_type TYPE enum;
CREATE TABLE organizations ();
ALTER TABLE organizations ADD COLUMN id uuid NOT NULL;
ALTER TABLE users ADD COLUMN org_id uuid;
CREATE UNIQUE INDEX idx_users_email ON users (email);
ALTER TABLE users ADD FOREIGN KEY (org_id) REFERENCES organizations;
```

Notice `organizations` is created, and its `id` column added, *before* the foreign
key statement that references it — the DDL emitter works this ordering out on its
own; it isn't relying on the operations already being in a safe order.

## 9. Drop a column, then create and drop a table

```
$ schemavcs migrate drop-column users region
dropped column users.region (2ea3abbacba7)

$ schemavcs migrate create-table temp_scratch
created table 'temp_scratch' (2cde2e79abb9)

$ schemavcs migrate drop-table temp_scratch
dropped table 'temp_scratch' (61974c32db79)
```

```
table users {
  column id: uuid not_null
  column email: string(255) not_null
  column plan_type: enum
  column org_id: uuid
  index idx_users_email on (email) unique
  foreign_key (org_id) references organizations
}

table organizations {
  column id: uuid not_null
}
```

`region` is gone, and `temp_scratch` never shows up at all in the current state —
even though its full history (create, then drop) is still permanently recorded and
inspectable in `.schemavcs/dag/nodes/`.
