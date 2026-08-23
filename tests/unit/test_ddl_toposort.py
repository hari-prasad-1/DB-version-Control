from uuid import uuid4

import pytest

from schemavcs.ddl.toposort import CircularDependencyError, toposort
from schemavcs.model import (
    AddColumn,
    AddConstraint,
    Column,
    Constraint,
    CreateTable,
    DropColumn,
    DropTable,
    Table,
    TypeSpec,
)


def test_create_table_before_add_column_on_it():
    table_id = uuid4()
    create = CreateTable(table=Table(id=table_id, name="orders"))
    add = AddColumn(
        table_id=table_id, column=Column(id=uuid4(), name="total", type=TypeSpec("int"))
    )

    ordered = toposort((add, create))
    assert ordered == [create, add]


def test_create_table_before_fk_referencing_it():
    orders_id, users_id = uuid4(), uuid4()
    create_orders = CreateTable(table=Table(id=orders_id, name="orders"))
    create_users = CreateTable(table=Table(id=users_id, name="users"))
    add_fk = AddConstraint(
        table_id=users_id,
        constraint=Constraint(
            id=uuid4(), kind="foreign_key", columns=[uuid4()], references=orders_id
        ),
    )

    ordered = toposort((add_fk, create_users, create_orders))
    assert ordered.index(create_orders) < ordered.index(add_fk)
    assert ordered.index(create_users) < ordered.index(add_fk)


def test_drop_column_before_drop_table():
    table_id, column_id = uuid4(), uuid4()
    drop_table = DropTable(table_id=table_id)
    drop_column = DropColumn(table_id=table_id, column_id=column_id)

    ordered = toposort((drop_table, drop_column))
    assert ordered == [drop_column, drop_table]


def test_unrelated_operations_keep_stable_order():
    op_a = DropTable(table_id=uuid4())
    op_b = DropTable(table_id=uuid4())
    assert toposort((op_a, op_b)) == [op_a, op_b]


def test_circular_dependency_raises():
    # Kahn's algorithm itself, exercised directly against a synthetic cycle
    # -- real Operations can't produce a cycle through build_dependency_edges
    # (creation always originates from outside a same-batch cycle), so this
    # isolates the "detect a cycle, don't try to resolve it" behavior.
    import sys

    import schemavcs.ddl.toposort  # noqa: F401 (ensures it's in sys.modules)

    toposort_module = sys.modules["schemavcs.ddl.toposort"]

    op_a, op_b = DropTable(table_id=uuid4()), DropTable(table_id=uuid4())
    original = toposort_module.build_dependency_edges
    toposort_module.build_dependency_edges = lambda ops: [
        toposort_module.DependencyEdge(before=0, after=1),
        toposort_module.DependencyEdge(before=1, after=0),
    ]
    try:
        with pytest.raises(CircularDependencyError):
            toposort((op_a, op_b))
    finally:
        toposort_module.build_dependency_edges = original
