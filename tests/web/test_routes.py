"""FastAPI TestClient smoke tests for the full click-path: create branches
via forms, diverge, merge, resolve every conflict UI mode, sync a detected
rename, view DDL -- through real HTTP calls against the real app, not
direct function calls into schemavcs_web internals."""

from fastapi.testclient import TestClient

from schemavcs_web.app import app


def _client() -> TestClient:
    client = TestClient(app)
    client.get("/")  # establishes the session cookie
    return client


def test_index_creates_a_fresh_session_with_main_branch():
    client = _client()
    r = client.get("/")
    assert r.status_code == 200
    assert "main" in r.text


def test_create_table_and_add_column_round_trip_into_the_schema_editor():
    client = _client()
    client.post("/migrate/create-table", data={"table": "users"})
    client.post(
        "/migrate/add-column", data={"table": "users", "column": "email", "type_expr": "string"}
    )

    r = client.get("/")
    assert "column email: string" in r.text


def test_branch_and_checkout_round_trip():
    client = _client()
    client.post("/migrate/create-table", data={"table": "users"})
    r = client.post("/branch", data={"name": "feature", "from_branch": "main"})
    assert r.status_code in (200, 303)

    r = client.get("/")
    assert "feature" in r.text

    r = client.post("/checkout", data={"branch": "main"})
    assert r.status_code in (200, 303)
    r = client.get("/")
    assert 'class="branch-pill current">main' in r.text


def test_delete_branch_via_http_retires_the_name():
    client = _client()
    client.post("/migrate/create-table", data={"table": "users"})
    client.post("/branch", data={"name": "feature", "from_branch": "main"})
    client.post("/checkout", data={"branch": "main"})

    r = client.post("/branch/delete", data={"name": "feature"})
    assert r.status_code in (200, 303)

    r = client.get("/")
    assert "feature" not in r.text.split("Deleted")[0]  # gone from the live branch pills
    assert "Deleted (names retired" in r.text
    assert "feature" in r.text.split("Deleted (names retired")[1]  # shown as retired


def test_delete_current_branch_returns_a_friendly_400_not_a_crash():
    client = _client()
    client.post("/migrate/create-table", data={"table": "users"})
    client.post("/branch", data={"name": "feature", "from_branch": "main"})
    # still checked out on "feature" -- deleting it should be refused

    r = client.post("/branch/delete", data={"name": "feature"})
    assert r.status_code == 400
    assert "current branch" in r.text


def test_recreating_a_deleted_branch_name_returns_a_friendly_400():
    client = _client()
    client.post("/branch", data={"name": "feature", "from_branch": "main"})
    client.post("/checkout", data={"branch": "main"})
    client.post("/branch/delete", data={"name": "feature"})

    r = client.post("/branch", data={"name": "feature", "from_branch": "main"})
    assert r.status_code == 400
    assert "deleted earlier" in r.text


def test_ddl_view_renders_real_emitted_sql():
    client = _client()
    client.post("/migrate/create-table", data={"table": "users"})
    client.post(
        "/migrate/add-column", data={"table": "users", "column": "email", "type_expr": "string"}
    )

    r = client.get("/branches/main/ddl")
    assert r.status_code == 200
    assert "CREATE TABLE users" in r.text
    assert "ADD COLUMN email string" in r.text


def test_branch_graph_json_reflects_real_dag_structure():
    client = _client()
    client.post("/migrate/create-table", data={"table": "users"})
    client.post("/branch", data={"name": "feature", "from_branch": "main"})

    r = client.get("/branches/graph")
    assert r.status_code == 200
    data = r.json()
    assert set(data["heads"].keys()) == {"main", "feature"}
    assert data["heads"]["main"] == data["heads"]["feature"]  # feature hasn't diverged yet


def test_full_merge_conflict_resolution_via_http_single_valued_field():
    client = _client()
    client.post("/migrate/create-table", data={"table": "users"})
    client.post(
        "/migrate/add-column", data={"table": "users", "column": "status", "type_expr": "string"}
    )
    client.post("/branch", data={"name": "branch-a", "from_branch": "main"})
    client.post("/checkout", data={"branch": "main"})
    client.post("/branch", data={"name": "branch-b", "from_branch": "main"})

    client.post("/checkout", data={"branch": "branch-a"})
    client.post(
        "/migrate/alter-column-type",
        data={"table": "users", "column": "status", "new_type": "enum"},
    )
    client.post("/checkout", data={"branch": "branch-b"})
    client.post(
        "/migrate/alter-column-type",
        data={"table": "users", "column": "status", "new_type": "varchar"},
    )

    r = client.post("/merge/start", data={"target_branch": "branch-a", "source_branch": "branch-b"})
    assert r.status_code == 200
    session_id = r.json()["session_id"]

    r = client.get(f"/merge/{session_id}/step")
    assert r.status_code == 200
    assert "both branches set a different type" in r.text
    assert "Keep both" not in r.text  # single-valued field: no meaningless "both" choice
    assert "Keep A" in r.text and "Keep B" in r.text

    r = client.post(f"/merge/{session_id}/answer", data={"choice": "a"})
    assert r.status_code in (200, 303)

    r = client.get(f"/merge/{session_id}/step")
    assert "Merge complete" in r.text
    assert "1 conflict(s) resolved" in r.text


def test_full_merge_with_no_conflict_fast_forwards_via_http():
    client = _client()
    client.post("/migrate/create-table", data={"table": "users"})
    client.post("/branch", data={"name": "feature", "from_branch": "main"})
    client.post("/checkout", data={"branch": "feature"})
    client.post(
        "/migrate/add-column", data={"table": "users", "column": "email", "type_expr": "string"}
    )
    client.post("/checkout", data={"branch": "main"})

    r = client.post("/merge/start", data={"target_branch": "main", "source_branch": "feature"})
    session_id = r.json()["session_id"]

    r = client.get(f"/merge/{session_id}/step")
    assert "Merge complete" in r.text
    assert "0 conflict(s) resolved" in r.text


def test_merge_switches_current_branch_to_the_target_after_completion():
    # regression: a user who starts a merge while still checked out on the
    # SOURCE branch must land on the TARGET branch afterward -- otherwise
    # "back to repo" shows the source's unrelated state and the merge
    # looks like it did nothing, even though the target really did update.
    client = _client()
    client.post("/migrate/create-table", data={"table": "users"})
    client.post("/branch", data={"name": "feature", "from_branch": "main"})
    # still checked out on "feature" (branch creation auto-switches to it)
    client.post(
        "/migrate/add-column", data={"table": "users", "column": "email", "type_expr": "string"}
    )

    r = client.get("/")
    assert 'current">feature' in r.text

    r = client.post("/merge/start", data={"target_branch": "main", "source_branch": "feature"})
    session_id = r.json()["session_id"]
    r = client.get(f"/merge/{session_id}/step")
    assert "Merge complete" in r.text
    assert "You're now on <strong>main</strong>" in r.text

    r = client.get("/")
    assert 'current">main' in r.text
    assert "column email: string" in r.text  # main's post-merge state, not feature's


def test_unknown_merge_session_returns_404():
    client = _client()
    r = client.get("/merge/does-not-exist/step")
    assert r.status_code == 404


def test_answering_before_a_question_exists_returns_409():
    client = _client()
    client.post("/migrate/create-table", data={"table": "users"})
    client.post("/branch", data={"name": "feature", "from_branch": "main"})
    client.post("/checkout", data={"branch": "feature"})
    client.post(
        "/migrate/add-column", data={"table": "users", "column": "email", "type_expr": "string"}
    )
    client.post("/checkout", data={"branch": "main"})

    r = client.post("/merge/start", data={"target_branch": "main", "source_branch": "feature"})
    session_id = r.json()["session_id"]
    client.get(f"/merge/{session_id}/step")  # drains to completion, fast-forward, no question

    r = client.post(f"/merge/{session_id}/answer", data={"choice": "a"})
    assert r.status_code == 409


def test_full_sync_rename_detection_via_http():
    client = _client()
    client.post("/migrate/create-table", data={"table": "users"})
    client.post(
        "/migrate/add-column",
        data={"table": "users", "column": "subscription_type", "type_expr": "string"},
    )

    new_text = "table users {\n  column plan_type: enum\n}\n"
    r = client.post("/schema/save", data={"text": new_text})
    assert r.status_code in (200, 303)

    r = client.post("/sync/start")
    assert r.status_code == 200
    session_id = r.json()["session_id"]

    r = client.get(f"/sync/{session_id}/step")
    assert r.status_code == 200
    assert "subscription_type" in r.text
    assert "plan_type" in r.text
    assert "no ambiguity" in r.text

    r = client.post(f"/sync/{session_id}/answer", data={"accept": "yes"})
    assert r.status_code in (200, 303)

    r = client.get(f"/sync/{session_id}/step")
    assert "Sync complete" in r.text
    assert "Generated migration" in r.text

    r = client.get("/branches/main/ddl")
    assert "RENAME COLUMN subscription_type TO plan_type" in r.text


def test_sync_with_no_edit_reports_no_changes():
    client = _client()
    client.post("/migrate/create-table", data={"table": "users"})

    r = client.post("/sync/start")
    session_id = r.json()["session_id"]
    r = client.get(f"/sync/{session_id}/step")
    assert "No changes detected" in r.text


def test_unknown_sync_session_returns_404():
    client = _client()
    r = client.get("/sync/does-not-exist/step")
    assert r.status_code == 404
