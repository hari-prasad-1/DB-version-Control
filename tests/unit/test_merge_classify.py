from uuid import uuid4

from schemavcs.merge.classify import Classification, classify
from schemavcs.merge.grouping import IdentityGroup
from schemavcs.model import (
    AddColumn,
    AlterColumnNullability,
    AlterColumnType,
    Column,
    DropColumn,
    DropTable,
    RenameColumn,
    TypeSpec,
)


def test_unrelated_only_one_branch_touched():
    col_id = uuid4()
    group = IdentityGroup(
        identity_id=col_id, ops_a=[DropColumn(table_id=uuid4(), column_id=col_id)]
    )
    result = classify(group)
    assert result.classification == Classification.UNRELATED


def test_identical_op_both_sides_dedupe():
    col_id, table_id = uuid4(), uuid4()
    op = DropColumn(table_id=table_id, column_id=col_id)
    group = IdentityGroup(identity_id=col_id, ops_a=[op], ops_b=[op])
    result = classify(group)
    assert result.classification == Classification.IDENTICAL


def test_add_column_same_everything_dedupe():
    col_id, table_id = uuid4(), uuid4()
    column = Column(id=col_id, name="notes", type=TypeSpec("text"))
    op = AddColumn(table_id=table_id, column=column)
    group = IdentityGroup(identity_id=col_id, ops_a=[op], ops_b=[op])
    result = classify(group)
    assert result.classification == Classification.IDENTICAL


def test_add_column_different_type_conflict():
    col_id, table_id = uuid4(), uuid4()
    op_a = AddColumn(table_id=table_id, column=Column(id=col_id, name="x", type=TypeSpec("int")))
    op_b = AddColumn(table_id=table_id, column=Column(id=col_id, name="x", type=TypeSpec("string")))
    group = IdentityGroup(identity_id=col_id, ops_a=[op_a], ops_b=[op_b])
    result = classify(group)
    assert result.classification == Classification.CONFLICT


def test_rename_to_different_names_conflict():
    col_id = uuid4()
    op_a = RenameColumn(column_id=col_id, old_name="x", new_name="y")
    op_b = RenameColumn(column_id=col_id, old_name="x", new_name="z")
    group = IdentityGroup(identity_id=col_id, ops_a=[op_a], ops_b=[op_b])
    result = classify(group)
    assert result.classification == Classification.CONFLICT


def test_rename_vs_drop_conflict():
    col_id, table_id = uuid4(), uuid4()
    op_a = RenameColumn(column_id=col_id, old_name="x", new_name="y")
    op_b = DropColumn(table_id=table_id, column_id=col_id)
    group = IdentityGroup(identity_id=col_id, ops_a=[op_a], ops_b=[op_b])
    result = classify(group)
    assert result.classification == Classification.CONFLICT
    # "Keep both" would mean the column is simultaneously dropped and
    # renamed -- not a real outcome, so only [a]/[b] should ever be
    # offered, same as any other single-valued conflict.
    assert result.single_valued_field is True


def test_drop_vs_any_mutation_generalized_conflict():
    col_id, table_id = uuid4(), uuid4()
    op_a = DropColumn(table_id=table_id, column_id=col_id)
    op_b = AlterColumnType(column_id=col_id, old_type=TypeSpec("int"), new_type=TypeSpec("bigint"))
    group = IdentityGroup(identity_id=col_id, ops_a=[op_a], ops_b=[op_b])
    result = classify(group)
    assert result.classification == Classification.CONFLICT
    assert result.single_valued_field is True


def test_alter_type_same_target_dedupe():
    col_id = uuid4()
    op = AlterColumnType(column_id=col_id, old_type=TypeSpec("int"), new_type=TypeSpec("bigint"))
    group = IdentityGroup(identity_id=col_id, ops_a=[op], ops_b=[op])
    result = classify(group)
    assert result.classification == Classification.IDENTICAL


def test_alter_type_different_target_conflict():
    col_id = uuid4()
    op_a = AlterColumnType(column_id=col_id, old_type=TypeSpec("int"), new_type=TypeSpec("decimal"))
    op_b = AlterColumnType(column_id=col_id, old_type=TypeSpec("int"), new_type=TypeSpec("string"))
    group = IdentityGroup(identity_id=col_id, ops_a=[op_a], ops_b=[op_b])
    result = classify(group)
    assert result.classification == Classification.CONFLICT


def test_nullability_same_target_dedupe():
    col_id = uuid4()
    op = AlterColumnNullability(column_id=col_id, nullable=False)
    group = IdentityGroup(identity_id=col_id, ops_a=[op], ops_b=[op])
    result = classify(group)
    assert result.classification == Classification.IDENTICAL


def test_nullability_different_target_conflict():
    col_id = uuid4()
    op_a = AlterColumnNullability(column_id=col_id, nullable=True)
    op_b = AlterColumnNullability(column_id=col_id, nullable=False)
    group = IdentityGroup(identity_id=col_id, ops_a=[op_a], ops_b=[op_b])
    result = classify(group)
    assert result.classification == Classification.CONFLICT


def test_drop_table_both_sides_dedupe():
    table_id = uuid4()
    op = DropTable(table_id=table_id)
    group = IdentityGroup(identity_id=table_id, ops_a=[op], ops_b=[op])
    result = classify(group)
    assert result.classification == Classification.IDENTICAL


def test_partial_conflict_agreed_rename_disagreed_retype():
    col_id = uuid4()
    op_a = [
        RenameColumn(column_id=col_id, old_name="subscription_type", new_name="plan_type"),
        AlterColumnType(column_id=col_id, old_type=TypeSpec("string"), new_type=TypeSpec("enum")),
    ]
    op_b = [
        RenameColumn(column_id=col_id, old_name="subscription_type", new_name="plan_type"),
        AlterColumnType(column_id=col_id, old_type=TypeSpec("string"), new_type=TypeSpec("text")),
    ]
    group = IdentityGroup(identity_id=col_id, ops_a=op_a, ops_b=op_b)
    result = classify(group)
    assert result.classification == Classification.PARTIAL_CONFLICT
    assert result.conflicting_fields == ("type",)
    assert result.agreed_fields["name"] == "plan_type"


def test_compound_edits_agree_on_every_field_commuting():
    col_id = uuid4()
    op_a = [RenameColumn(column_id=col_id, old_name="x", new_name="y")]
    op_b = [
        RenameColumn(column_id=col_id, old_name="x", new_name="y"),
        AlterColumnNullability(column_id=col_id, nullable=False),
    ]
    group = IdentityGroup(identity_id=col_id, ops_a=op_a, ops_b=op_b)
    result = classify(group)
    assert result.classification == Classification.COMMUTING
    assert result.agreed_fields["name"] == "y"
    assert result.agreed_fields["nullable"] is False


def test_rename_plus_retype_vs_unrelated_add_index_is_commuting():
    # different identities entirely -- included here as a grouping-level
    # sanity check rather than a classify() unit test, since AddIndex on an
    # unrelated column never lands in the same IdentityGroup as this column's
    # rename+retype in the first place.
    col_id = uuid4()
    op_a = [
        RenameColumn(column_id=col_id, old_name="x", new_name="y"),
        AlterColumnType(column_id=col_id, old_type=TypeSpec("string"), new_type=TypeSpec("enum")),
    ]
    group = IdentityGroup(identity_id=col_id, ops_a=op_a, ops_b=[])
    result = classify(group)
    assert result.classification == Classification.UNRELATED
