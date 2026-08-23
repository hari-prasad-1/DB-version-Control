from uuid import uuid4

from schemavcs.merge.classify import Classification, ClassifiedGroup
from schemavcs.merge.cross_object import cross_object_pass
from schemavcs.merge.grouping import IdentityGroup
from schemavcs.model import (
    AddColumn,
    AddConstraint,
    AddIndex,
    Column,
    CompoundOperation,
    Constraint,
    DropColumn,
    DropTable,
    Index,
    Snapshot,
    Table,
    TypeSpec,
)


def _ops(*operations) -> tuple[CompoundOperation, ...]:
    return (CompoundOperation(operations=operations),)


def test_drop_table_vs_add_constraint_referencing_it():
    # the required demo case: branch-a drops `orders`, branch-b adds an FK
    # from a new column on `users` to `orders`.
    orders_id, users_id, col_id = uuid4(), uuid4(), uuid4()
    ancestor = Snapshot(
        branch="root",
        revision_id="root",
        tables=[Table(id=orders_id, name="orders"), Table(id=users_id, name="users")],
    )

    ops_a = _ops(DropTable(table_id=orders_id))
    ops_b = _ops(
        AddConstraint(
            table_id=users_id,
            constraint=Constraint(
                id=uuid4(), kind="foreign_key", columns=[col_id], references=orders_id
            ),
        )
    )

    result = cross_object_pass([], ops_a, ops_b, ancestor)
    assert len(result) == 1
    assert result[0].classification == Classification.CONFLICT
    assert "orders" in result[0].reason
    assert "branch A" in result[0].reason


def test_drop_table_vs_add_column_referencing_it():
    orders_id = uuid4()
    ancestor = Snapshot(
        branch="root", revision_id="root", tables=[Table(id=orders_id, name="orders")]
    )

    ops_a = _ops(DropTable(table_id=orders_id))
    ops_b = _ops(
        AddColumn(
            table_id=orders_id, column=Column(id=uuid4(), name="notes", type=TypeSpec("text"))
        )
    )

    result = cross_object_pass([], ops_a, ops_b, ancestor)
    assert len(result) == 1
    assert result[0].classification == Classification.CONFLICT


def test_drop_column_vs_add_index_referencing_it():
    table_id, col_id = uuid4(), uuid4()
    ancestor = Snapshot(
        branch="root",
        revision_id="root",
        tables=[
            Table(
                id=table_id,
                name="users",
                columns=[Column(id=col_id, name="legacy_id", type=TypeSpec("int"))],
            )
        ],
    )

    ops_a = _ops(DropColumn(table_id=table_id, column_id=col_id))
    ops_b = _ops(
        AddIndex(table_id=table_id, index=Index(id=uuid4(), name="idx_legacy", columns=[col_id]))
    )

    result = cross_object_pass([], ops_a, ops_b, ancestor)
    assert len(result) == 1
    assert result[0].classification == Classification.CONFLICT
    assert "legacy_id" in result[0].reason


def test_drop_column_vs_add_constraint_referencing_it():
    table_id, col_id = uuid4(), uuid4()
    ancestor = Snapshot(
        branch="root",
        revision_id="root",
        tables=[
            Table(
                id=table_id,
                name="users",
                columns=[Column(id=col_id, name="email", type=TypeSpec("string"))],
            )
        ],
    )

    ops_a = _ops(DropColumn(table_id=table_id, column_id=col_id))
    ops_b = _ops(
        AddConstraint(
            table_id=table_id, constraint=Constraint(id=uuid4(), kind="unique", columns=[col_id])
        )
    )

    result = cross_object_pass([], ops_a, ops_b, ancestor)
    assert len(result) == 1
    assert result[0].classification == Classification.CONFLICT


def test_checked_symmetrically_both_directions():
    orders_id, users_id, col_id = uuid4(), uuid4(), uuid4()
    ancestor = Snapshot(
        branch="root",
        revision_id="root",
        tables=[Table(id=orders_id, name="orders"), Table(id=users_id, name="users")],
    )
    constraint = Constraint(id=uuid4(), kind="foreign_key", columns=[col_id], references=orders_id)

    # branch-a drops, branch-b references -- branch A is the dropper
    result_ab = cross_object_pass(
        [],
        _ops(DropTable(table_id=orders_id)),
        _ops(AddConstraint(table_id=users_id, constraint=constraint)),
        ancestor,
    )
    assert "branch A" in result_ab[0].reason

    # swapped: branch-a references, branch-b drops -- branch B is the dropper
    result_ba = cross_object_pass(
        [],
        _ops(AddConstraint(table_id=users_id, constraint=constraint)),
        _ops(DropTable(table_id=orders_id)),
        ancestor,
    )
    assert "branch B" in result_ba[0].reason


def test_unrelated_operations_produce_no_conflict():
    table_id = uuid4()
    ancestor = Snapshot(
        branch="root", revision_id="root", tables=[Table(id=table_id, name="users")]
    )

    ops_a = _ops(
        AddColumn(table_id=table_id, column=Column(id=uuid4(), name="a", type=TypeSpec("int")))
    )
    ops_b = _ops(
        AddColumn(table_id=table_id, column=Column(id=uuid4(), name="b", type=TypeSpec("int")))
    )

    result = cross_object_pass([], ops_a, ops_b, ancestor)
    assert result == []


def test_incompatible_fk_collision_is_out_of_scope():
    # two branches each add a DIFFERENT fk to the same table -- no shared
    # identity, nothing destroyed -- explicitly not this pass's job.
    table_id, other_a, other_b = uuid4(), uuid4(), uuid4()
    ancestor = Snapshot(
        branch="root",
        revision_id="root",
        tables=[
            Table(id=table_id, name="orders"),
            Table(id=other_a, name="a"),
            Table(id=other_b, name="b"),
        ],
    )
    ops_a = _ops(
        AddConstraint(
            table_id=table_id,
            constraint=Constraint(
                id=uuid4(), kind="foreign_key", columns=[uuid4()], references=other_a
            ),
        )
    )
    ops_b = _ops(
        AddConstraint(
            table_id=table_id,
            constraint=Constraint(
                id=uuid4(), kind="foreign_key", columns=[uuid4()], references=other_b
            ),
        )
    )

    result = cross_object_pass([], ops_a, ops_b, ancestor)
    assert result == []


def test_preserves_existing_classified_groups():
    existing = ClassifiedGroup(
        group=IdentityGroup(identity_id=uuid4()),
        classification=Classification.IDENTICAL,
        reason="x",
    )
    ancestor = Snapshot(branch="root", revision_id="root", tables=[])
    result = cross_object_pass([existing], (), (), ancestor)
    assert result == [existing]
