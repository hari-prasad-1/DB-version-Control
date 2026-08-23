from uuid import uuid4

from schemavcs.llm import ConflictExplanation, StubExplainer
from schemavcs.merge.classify import Classification, ClassifiedGroup
from schemavcs.merge.grouping import IdentityGroup
from schemavcs.model import Column, RenameColumn, Snapshot, Table, TypeSpec


def test_explain_returns_conflict_explanation():
    col_id, table_id = uuid4(), uuid4()
    op_a = RenameColumn(column_id=col_id, old_name="x", new_name="y")
    op_b = RenameColumn(column_id=col_id, old_name="x", new_name="z")
    group = ClassifiedGroup(
        group=IdentityGroup(identity_id=col_id, ops_a=[op_a], ops_b=[op_b]),
        classification=Classification.CONFLICT,
        reason="both branches set a different name",
    )
    schema_context = Snapshot(
        branch="root",
        revision_id="root",
        tables=[
            Table(
                id=table_id,
                name="users",
                columns=[Column(id=col_id, name="x", type=TypeSpec("string"))],
            )
        ],
    )

    explainer = StubExplainer()
    result = explainer.explain(group, schema_context)

    assert isinstance(result, ConflictExplanation)
    assert "users.'x'" in result.explanation or "users.x" in result.explanation
    assert "RenameColumn" in result.explanation
    assert result.suggestion is None


def test_explain_is_deterministic_and_offline():
    col_id = uuid4()
    group = ClassifiedGroup(
        group=IdentityGroup(identity_id=col_id, ops_a=[], ops_b=[]),
        classification=Classification.CONFLICT,
        reason="test reason",
    )
    schema_context = Snapshot(branch="root", revision_id="root", tables=[])

    explainer = StubExplainer()
    result_1 = explainer.explain(group, schema_context)
    result_2 = explainer.explain(group, schema_context)
    assert result_1 == result_2


def test_explain_falls_back_to_raw_id_when_identity_unresolvable():
    unknown_id = uuid4()
    group = ClassifiedGroup(
        group=IdentityGroup(identity_id=unknown_id, ops_a=[], ops_b=[]),
        classification=Classification.CONFLICT,
        reason="test reason",
    )
    schema_context = Snapshot(branch="root", revision_id="root", tables=[])

    explainer = StubExplainer()
    result = explainer.explain(group, schema_context)
    assert str(unknown_id) in result.explanation
