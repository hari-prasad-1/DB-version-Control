from uuid import uuid4

from schemavcs.dag import DagStore
from schemavcs.dag.persistence import load, save
from schemavcs.model import AddColumn, Column, CompoundOperation, CreateTable, Table, TypeSpec
from schemavcs.storage.paths import init_storage


def test_save_and_load_round_trip(tmp_path):
    init_storage(tmp_path)

    table_id, col_id = uuid4(), uuid4()
    store = DagStore()
    store.append(
        "root",
        "main",
        (),
        operations=(
            CompoundOperation(operations=(CreateTable(table=Table(id=table_id, name="orders")),)),
        ),
    )
    store.append(
        "a1",
        "branch-a",
        ("root",),
        operations=(
            CompoundOperation(
                operations=(
                    AddColumn(
                        table_id=table_id,
                        column=Column(id=col_id, name="total", type=TypeSpec("int")),
                    ),
                )
            ),
        ),
    )

    save(store, tmp_path)
    restored = load(tmp_path)

    assert restored.head("main") == "root"
    assert restored.head("branch-a") == "a1"
    assert restored.get_node("a1") == store.get_node("a1")
    assert restored.get_node("root") == store.get_node("root")


def test_load_empty_repo_returns_empty_store(tmp_path):
    init_storage(tmp_path)
    store = load(tmp_path)
    assert store.all_revision_ids() == []
    assert store.all_heads() == {}


def test_deleted_branch_survives_a_save_and_load_round_trip(tmp_path):
    init_storage(tmp_path)
    store = DagStore()
    store.append("root", "main", ())
    store.append("b1", "feature", ("root",))
    store.delete_branch("feature")

    save(store, tmp_path)
    restored = load(tmp_path)

    assert restored.has_branch("feature") is False
    assert restored.has_node("b1") is True  # history stays, only the head pointer is gone
