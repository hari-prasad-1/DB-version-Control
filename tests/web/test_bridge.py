"""Drives the REAL merge() and detect_renames() through WebConfirmBridge --
not a mock of either function. If a click-by-click web flow can correctly
resolve a real 2-conflict merge and a real reject-then-repool rename
scenario through this bridge, the pause mechanism actually works."""

from uuid import uuid4

from schemavcs.dag import DagStore
from schemavcs.dsl.raw import RawColumn
from schemavcs.merge.classify import ClassifiedGroup
from schemavcs.merge.engine import merge
from schemavcs.merge.resolve import HumanConfirmationToken, TokenAlreadyUsedError
from schemavcs.model import Column, CompoundOperation, RenameColumn, TypeSpec
from schemavcs.rename_detect.detector import ProposalStatus, RenameProposal, detect_renames
from schemavcs_web.bridge import BridgeError, WebConfirmBridge


def _raw(name: str, type_name: str = "string", position: int = 0) -> RawColumn:
    return RawColumn(name=name, type=TypeSpec(type_name), position=position)


def _keep_a_token(group: ClassifiedGroup) -> HumanConfirmationToken:
    return HumanConfirmationToken(
        group_id=group.group.identity_id,
        chosen_resolution=tuple(group.group.ops_a),
        _nonce=uuid4(),
    )


def test_bridge_pauses_and_resumes_a_real_two_conflict_merge():
    store = DagStore()
    col_a_id, col_b_id = uuid4(), uuid4()

    store.append("root", "main", ())
    store.append(
        "main-1",
        "main",
        ("root",),
        operations=(
            CompoundOperation(
                operations=(RenameColumn(column_id=col_a_id, old_name="x", new_name="y"),)
            ),
        ),
    )
    store.append(
        "main-2",
        "main",
        ("main-1",),
        operations=(
            CompoundOperation(
                operations=(RenameColumn(column_id=col_b_id, old_name="p", new_name="q"),)
            ),
        ),
    )
    store.append(
        "b-1",
        "branch-b",
        ("root",),
        operations=(
            CompoundOperation(
                operations=(
                    RenameColumn(column_id=col_a_id, old_name="x", new_name="z"),
                    RenameColumn(column_id=col_b_id, old_name="p", new_name="r"),
                )
            ),
        ),
    )

    bridge: WebConfirmBridge[ClassifiedGroup, HumanConfirmationToken] = WebConfirmBridge()
    bridge.run_in_background(lambda: merge(store, "main", "branch-b", confirm=bridge.ask))

    seen_identities = []
    while True:
        question = bridge.poll_question(timeout=5.0)
        if question is None:
            break
        seen_identities.append(question.group.identity_id)
        bridge.submit_answer(_keep_a_token(question))

    result = bridge.result()
    assert result.conflicts_resolved == 2
    assert set(seen_identities) == {col_a_id, col_b_id}

    merged_ops = [op for compound in result.migration.operations for op in compound.operations]
    assert RenameColumn(column_id=col_a_id, old_name="x", new_name="y") in merged_ops
    assert RenameColumn(column_id=col_b_id, old_name="p", new_name="q") in merged_ops


def test_bridge_reraises_a_real_engine_error():
    store = DagStore()
    store.append("root", "main", ())

    bridge: WebConfirmBridge = WebConfirmBridge()
    bridge.run_in_background(lambda: merge(store, "main", "main"))

    # no questions -- self-merge raises before ever reaching the confirm loop
    assert bridge.poll_question(timeout=5.0) is None
    try:
        bridge.result()
        raise AssertionError("expected NothingToMergeError to propagate")
    except Exception as exc:
        assert type(exc).__name__ == "NothingToMergeError"


def test_bridge_second_run_in_background_call_rejected():
    bridge: WebConfirmBridge = WebConfirmBridge()
    bridge.run_in_background(lambda: 1)
    bridge.result()
    try:
        bridge.run_in_background(lambda: 2)
        raise AssertionError("expected BridgeError")
    except BridgeError:
        pass


def test_bridge_submit_answer_after_done_rejected():
    bridge: WebConfirmBridge = WebConfirmBridge()
    bridge.run_in_background(lambda: 1)
    bridge.result()
    try:
        bridge.submit_answer("too late")
        raise AssertionError("expected BridgeError")
    except BridgeError:
        pass


def test_bridge_drives_a_real_reject_then_repool_rename_scenario():
    # mirrors tests/unit/test_rename_detector.py's own repool test, but
    # driven through the bridge one click at a time instead of a scripted
    # inline confirm function -- proving detect_renames()'s pool-shrinking
    # loop (which genuinely depends on each real answer, unlike merge()'s
    # answer-independent conflict list) still resolves correctly when paused
    # mid-loop by real thread-blocking rather than called synchronously.
    old = [
        Column(id=uuid4(), name="subscription_type", type=TypeSpec("string"), position=0),
        Column(id=uuid4(), name="something_unrelated", type=TypeSpec("int"), position=5),
    ]
    new = [
        _raw("plan_type", "enum", position=0),
        _raw("region", "int", position=5),
    ]

    bridge: WebConfirmBridge[RenameProposal, bool] = WebConfirmBridge()
    bridge.run_in_background(lambda: detect_renames(old, new, table_size=6, confirm=bridge.ask))

    answers_given = []
    while True:
        question = bridge.poll_question(timeout=5.0)
        if question is None:
            break
        # reject the first proposal seen, confirm every one after that --
        # same script the existing unit test uses.
        answer = len(answers_given) > 0
        answers_given.append(answer)
        bridge.submit_answer(answer)

    result = bridge.result()
    assert len(result.proposals) == 2
    assert result.proposals[0].status == ProposalStatus.REJECTED
    assert result.proposals[1].status == ProposalStatus.CONFIRMED
    rejected_pair = (result.proposals[0].old_column.name, result.proposals[0].new_column.name)
    confirmed_pair = (result.proposals[1].old_column.name, result.proposals[1].new_column.name)
    assert rejected_pair != confirmed_pair


def test_bridge_never_triggers_token_replay_protection():
    # the web path mints one real HumanConfirmationToken per group via a
    # fresh uuid4() nonce each time (confirm_adapter.py's job later) -- this
    # asserts the bridge itself never causes a token to be reused across
    # groups, which would raise TokenAlreadyUsedError inside commit_resolution.
    store = DagStore()
    col_id = uuid4()
    store.append("root", "main", ())
    store.append(
        "main-1",
        "main",
        ("root",),
        operations=(
            CompoundOperation(
                operations=(RenameColumn(column_id=col_id, old_name="x", new_name="y"),)
            ),
        ),
    )
    store.append(
        "b-1",
        "branch-b",
        ("root",),
        operations=(
            CompoundOperation(
                operations=(RenameColumn(column_id=col_id, old_name="x", new_name="z"),)
            ),
        ),
    )

    bridge: WebConfirmBridge[ClassifiedGroup, HumanConfirmationToken] = WebConfirmBridge()
    bridge.run_in_background(lambda: merge(store, "main", "branch-b", confirm=bridge.ask))

    question = bridge.poll_question(timeout=5.0)
    assert question is not None
    bridge.submit_answer(_keep_a_token(question))

    try:
        result = bridge.result()
    except TokenAlreadyUsedError:
        raise AssertionError("bridge caused a token replay") from None
    assert result.conflicts_resolved == 1
