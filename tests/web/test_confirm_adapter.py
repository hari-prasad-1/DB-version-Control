from uuid import uuid4

from schemavcs.merge.classify import Classification, ClassifiedGroup
from schemavcs.merge.grouping import IdentityGroup
from schemavcs.model import (
    AddColumn,
    AlterColumnType,
    Column,
    RenameColumn,
    TypeSpec,
)
from schemavcs_web.confirm_adapter import (
    build_token_from_choice,
    classify_ui_mode,
    group_to_dict,
    proposal_to_dict,
)


def _free_choice_group() -> ClassifiedGroup:
    col_id = uuid4()
    op_a = RenameColumn(column_id=col_id, old_name="x", new_name="y")
    op_b = RenameColumn(column_id=col_id, old_name="x", new_name="z")
    return ClassifiedGroup(
        group=IdentityGroup(identity_id=col_id, ops_a=[op_a], ops_b=[op_b]),
        classification=Classification.CONFLICT,
        reason="both branches set a different name",
    )


def _single_valued_group() -> ClassifiedGroup:
    col_id = uuid4()
    op_a = AlterColumnType(column_id=col_id, old_type=TypeSpec("string"), new_type=TypeSpec("int"))
    op_b = AlterColumnType(
        column_id=col_id, old_type=TypeSpec("string"), new_type=TypeSpec("decimal")
    )
    return ClassifiedGroup(
        group=IdentityGroup(identity_id=col_id, ops_a=[op_a], ops_b=[op_b]),
        classification=Classification.CONFLICT,
        reason="both branches set a different type",
        single_valued_field=True,
    )


def _cross_object_group() -> ClassifiedGroup:
    table_id, col_id = uuid4(), uuid4()
    referencing_op = AddColumn(
        table_id=table_id, column=Column(id=col_id, name="notes", type=TypeSpec("text"))
    )
    return ClassifiedGroup(
        group=IdentityGroup(identity_id=table_id, ops_a=[], ops_b=[referencing_op]),
        classification=Classification.CONFLICT,
        reason="branch A dropped table that another branch's operation still references",
        cross_object_referencing_op=referencing_op,
    )


def test_classify_ui_mode_matches_confirm_from_cli_branching():
    assert classify_ui_mode(_free_choice_group()) == "free_choice"
    assert classify_ui_mode(_single_valued_group()) == "single_valued"
    assert classify_ui_mode(_cross_object_group()) == "cross_object"


def test_build_token_free_choice_a_and_b():
    group = _free_choice_group()

    token_a = build_token_from_choice(group, "a")
    assert token_a.chosen_resolution == tuple(group.group.ops_a)

    token_b = build_token_from_choice(group, "b")
    assert token_b.chosen_resolution == tuple(group.group.ops_b)
    assert token_a._nonce != token_b._nonce  # every call mints a fresh nonce


def test_build_token_free_choice_both():
    group = _free_choice_group()
    token = build_token_from_choice(group, "both")
    assert token.chosen_resolution == tuple(group.group.ops_a) + tuple(group.group.ops_b)


def test_build_token_single_valued_field_ignores_both():
    group = _single_valued_group()
    token = build_token_from_choice(group, "both")
    # "both" isn't a legal choice for a single-valued field -- falls back to
    # "a", exactly like confirm_from_cli's own single_valued_field branch,
    # which never offers "both" as an option in the first place.
    assert token.chosen_resolution == tuple(group.group.ops_a)


def test_build_token_cross_object_ignores_choice_entirely():
    group = _cross_object_group()
    referencing_op = group.cross_object_referencing_op
    assert referencing_op is not None

    token_ignoring_a = build_token_from_choice(group, "a")
    token_ignoring_anything = build_token_from_choice(group, "whatever")

    from schemavcs.model import DropColumn

    expected = DropColumn(table_id=referencing_op.table_id, column_id=referencing_op.column.id)
    assert token_ignoring_a.chosen_resolution == (expected,)
    assert token_ignoring_anything.chosen_resolution == (expected,)


def test_group_to_dict_is_json_safe_and_carries_ui_mode():
    group = _free_choice_group()
    data = group_to_dict(group)

    assert data["ui_mode"] == "free_choice"
    assert data["classification"] == "conflict"
    assert data["reason"] == group.reason
    assert isinstance(data["identity_id"], str)
    assert data["ops_a"][0]["__type__"] == "RenameColumn"
    assert data["ops_b"][0]["new_name"] == "z"

    import json

    json.dumps(data)  # must not raise -- proves it's genuinely JSON-safe


def test_proposal_to_dict_carries_structural_fallback_sentinel():
    from schemavcs.dsl.raw import RawColumn
    from schemavcs.rename_detect.detector import RenameProposal

    proposal = RenameProposal(
        old_column=Column(id=uuid4(), name="subscription_type", type=TypeSpec("string")),
        new_column=RawColumn(name="plan_type", type=TypeSpec("enum")),
        similarity=-1.0,
    )
    data = proposal_to_dict(proposal)

    assert data["similarity"] == -1.0
    assert data["old_column"]["name"] == "subscription_type"
    assert data["new_column"]["name"] == "plan_type"

    import json

    json.dumps(data)
