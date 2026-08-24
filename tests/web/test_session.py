from schemavcs.cli.commands import branch_cmd, migrate_cmd
from schemavcs.merge.engine import merge
from schemavcs_web.confirm_adapter import build_token_from_choice
from schemavcs_web.session import MergeSession, RenameSession, SessionStore


def test_create_repo_session_initializes_a_real_repo_with_main_branch():
    store_registry = SessionStore()
    repo_session = store_registry.create_repo_session()

    assert repo_session.repo_root.is_dir()
    dag_store = store_registry.load_store(repo_session)
    assert dag_store.head("main") is not None


def test_two_repo_sessions_get_independent_directories():
    store_registry = SessionStore()
    a = store_registry.create_repo_session()
    b = store_registry.create_repo_session()

    assert a.repo_root != b.repo_root
    assert a.session_id != b.session_id
    assert store_registry.get_repo_session(a.session_id) is a
    assert store_registry.get_repo_session(b.session_id) is b


def test_get_repo_session_returns_none_for_unknown_id():
    store_registry = SessionStore()
    assert store_registry.get_repo_session("does-not-exist") is None


def test_merge_session_bridge_drives_a_real_merge_against_a_repo_session():
    registry = SessionStore()
    repo_session = registry.create_repo_session()
    repo_root = repo_session.repo_root

    migrate_cmd.create_table(repo_root, "main", "users")
    migrate_cmd.add_column(repo_root, "main", "users", "email", "string", True)
    branch_cmd.create(repo_root, "feature", from_branch="main")
    migrate_cmd.rename_column(repo_root, "feature", "users", "email", "contact_email")

    dag_store = registry.load_store(repo_session)
    merge_session = MergeSession(
        session_id="m1",
        repo_root=repo_root,
        store=dag_store,
        target_branch="main",
        source_branch="feature",
    )
    registry.register_merge_session(merge_session)
    assert registry.get_merge_session("m1") is merge_session

    bridge = merge_session.bridge
    bridge.run_in_background(
        lambda: merge(
            dag_store, merge_session.target_branch, merge_session.source_branch, confirm=bridge.ask
        )
    )

    # a rename with nothing else touching that column fast-forwards --
    # no conflict, no question, just a result.
    assert bridge.poll_question(timeout=5.0) is None
    result = bridge.result()
    assert result.fast_forward is True


def test_merge_session_bridge_resolves_a_real_conflict_end_to_end():
    registry = SessionStore()
    repo_session = registry.create_repo_session()
    repo_root = repo_session.repo_root

    migrate_cmd.create_table(repo_root, "main", "users")
    migrate_cmd.add_column(repo_root, "main", "users", "status", "string", True)
    branch_cmd.create(repo_root, "branch-a", from_branch="main")
    branch_cmd.create(repo_root, "branch-b", from_branch="main")
    migrate_cmd.alter_column_type(repo_root, "branch-a", "users", "status", "enum")
    migrate_cmd.alter_column_type(repo_root, "branch-b", "users", "status", "varchar")

    dag_store = registry.load_store(repo_session)
    merge_session = MergeSession(
        session_id="m2",
        repo_root=repo_root,
        store=dag_store,
        target_branch="branch-a",
        source_branch="branch-b",
    )
    registry.register_merge_session(merge_session)
    bridge = merge_session.bridge
    bridge.run_in_background(
        lambda: merge(
            dag_store, merge_session.target_branch, merge_session.source_branch, confirm=bridge.ask
        )
    )

    question = bridge.poll_question(timeout=5.0)
    assert question is not None
    assert question.single_valued_field is True
    token = build_token_from_choice(question, "a")
    bridge.submit_answer(token)

    result = bridge.result()
    assert result.conflicts_resolved == 1


def test_rename_session_registers_and_looks_up_correctly():
    registry = SessionStore()
    session = RenameSession(session_id="r1", branch="main")
    registry.register_rename_session(session)

    assert registry.get_rename_session("r1") is session
    assert registry.get_rename_session("missing") is None
