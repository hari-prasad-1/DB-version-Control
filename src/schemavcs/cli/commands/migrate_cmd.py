"""Authoring verbs: one subcommand per Operation variant. Each resolves
names against the branch's current state, builds the typed Operation, and
appends a new Migration node."""

import logging
from pathlib import Path
from uuid import UUID, uuid4

from schemavcs.cli.resolve import UnknownColumnError, find_column_id, find_index_id, find_table
from schemavcs.cli.typespec_arg import parse_type_spec
from schemavcs.dag import replay
from schemavcs.dag.persistence import load, save
from schemavcs.dag.revision_id import make_revision_id
from schemavcs.model import (
    AddColumn,
    AddConstraint,
    AddIndex,
    AlterColumnNullability,
    AlterColumnType,
    Column,
    CompoundOperation,
    Constraint,
    CreateTable,
    DropColumn,
    DropConstraint,
    DropIndex,
    DropTable,
    Index,
    Operation,
    RenameColumn,
    RenameIndex,
    Table,
)
from schemavcs.model_sync.sync import sync_model_file

logger = logging.getLogger(__name__)


def _commit(repo_root: Path, branch: str, operation: Operation) -> str:
    store = load(repo_root)
    parent = store.head(branch)
    compound = CompoundOperation(operations=(operation,))
    revision_id = make_revision_id((parent,), (compound,))
    store.append(revision_id, branch, (parent,), (compound,))
    save(store, repo_root)
    sync_model_file(repo_root, store, branch)
    return revision_id


def create_table(repo_root: Path, branch: str, table_name: str) -> None:
    store = load(repo_root)
    snapshot = replay(store, store.head(branch), branch)
    if any(t.name == table_name for t in snapshot.tables):
        raise ValueError(f"table {table_name!r} already exists")
    op = CreateTable(table=Table(id=uuid4(), name=table_name))
    rev = _commit(repo_root, branch, op)
    logger.info(f"created table {table_name!r} ({rev})")


def drop_table(repo_root: Path, branch: str, table_name: str) -> None:
    store = load(repo_root)
    snapshot = replay(store, store.head(branch), branch)
    table = find_table(snapshot, table_name)
    rev = _commit(repo_root, branch, DropTable(table_id=table.id))
    logger.info(f"dropped table {table_name!r} ({rev})")


def add_column(
    repo_root: Path,
    branch: str,
    table_name: str,
    column_name: str,
    type_expr: str,
    nullable: bool,
) -> None:
    store = load(repo_root)
    snapshot = replay(store, store.head(branch), branch)
    table = find_table(snapshot, table_name)
    column = Column(
        id=uuid4(),
        name=column_name,
        type=parse_type_spec(type_expr),
        nullable=nullable,
        position=len(table.columns),
    )
    rev = _commit(repo_root, branch, AddColumn(table_id=table.id, column=column))
    logger.info(f"added column {table_name}.{column_name} ({rev})")


def drop_column(repo_root: Path, branch: str, table_name: str, column_name: str) -> None:
    store = load(repo_root)
    snapshot = replay(store, store.head(branch), branch)
    table = find_table(snapshot, table_name)
    column_id = find_column_id(table, column_name)
    rev = _commit(repo_root, branch, DropColumn(table_id=table.id, column_id=column_id))
    logger.info(f"dropped column {table_name}.{column_name} ({rev})")


def rename_column(
    repo_root: Path, branch: str, table_name: str, old_name: str, new_name: str
) -> None:
    store = load(repo_root)
    snapshot = replay(store, store.head(branch), branch)
    table = find_table(snapshot, table_name)
    column_id = find_column_id(table, old_name)
    rev = _commit(
        repo_root, branch, RenameColumn(column_id=column_id, old_name=old_name, new_name=new_name)
    )
    logger.info(f"renamed column {table_name}.{old_name} -> {new_name} ({rev})")


def alter_column_type(
    repo_root: Path, branch: str, table_name: str, column_name: str, new_type_expr: str
) -> None:
    store = load(repo_root)
    snapshot = replay(store, store.head(branch), branch)
    table = find_table(snapshot, table_name)
    try:
        column = next(c for c in table.columns if c.name == column_name)
    except StopIteration:
        raise UnknownColumnError(column_name) from None
    rev = _commit(
        repo_root,
        branch,
        AlterColumnType(
            column_id=column.id, old_type=column.type, new_type=parse_type_spec(new_type_expr)
        ),
    )
    logger.info(f"altered {table_name}.{column_name} type -> {new_type_expr} ({rev})")


def alter_column_nullability(
    repo_root: Path, branch: str, table_name: str, column_name: str, nullable: bool
) -> None:
    store = load(repo_root)
    snapshot = replay(store, store.head(branch), branch)
    table = find_table(snapshot, table_name)
    column_id = find_column_id(table, column_name)
    rev = _commit(repo_root, branch, AlterColumnNullability(column_id=column_id, nullable=nullable))
    logger.info(f"altered {table_name}.{column_name} nullable -> {nullable} ({rev})")


def add_index(
    repo_root: Path, branch: str, table_name: str, index_name: str, columns: list[str], unique: bool
) -> None:
    store = load(repo_root)
    snapshot = replay(store, store.head(branch), branch)
    table = find_table(snapshot, table_name)
    column_ids = [find_column_id(table, name) for name in columns]
    index = Index(id=uuid4(), name=index_name, columns=column_ids, unique=unique)
    rev = _commit(repo_root, branch, AddIndex(table_id=table.id, index=index))
    logger.info(f"added index {index_name!r} on {table_name}({', '.join(columns)}) ({rev})")


def drop_index(repo_root: Path, branch: str, table_name: str, index_name: str) -> None:
    store = load(repo_root)
    snapshot = replay(store, store.head(branch), branch)
    table = find_table(snapshot, table_name)
    index_id = find_index_id(table, index_name)
    rev = _commit(repo_root, branch, DropIndex(index_id=index_id))
    logger.info(f"dropped index {index_name!r} ({rev})")


def rename_index(
    repo_root: Path, branch: str, table_name: str, old_name: str, new_name: str
) -> None:
    store = load(repo_root)
    snapshot = replay(store, store.head(branch), branch)
    table = find_table(snapshot, table_name)
    index_id = find_index_id(table, old_name)
    rev = _commit(
        repo_root, branch, RenameIndex(index_id=index_id, old_name=old_name, new_name=new_name)
    )
    logger.info(f"renamed index {old_name!r} -> {new_name!r} ({rev})")


def add_foreign_key(
    repo_root: Path, branch: str, table_name: str, columns: list[str], references_table: str
) -> None:
    store = load(repo_root)
    snapshot = replay(store, store.head(branch), branch)
    table = find_table(snapshot, table_name)
    ref_table = find_table(snapshot, references_table)
    column_ids = [find_column_id(table, name) for name in columns]
    constraint = Constraint(
        id=uuid4(), kind="foreign_key", columns=column_ids, references=ref_table.id
    )
    rev = _commit(repo_root, branch, AddConstraint(table_id=table.id, constraint=constraint))
    logger.info(
        f"added foreign key {table_name}({', '.join(columns)}) -> {references_table} ({rev})"
    )


def drop_constraint(repo_root: Path, branch: str, constraint_id: str) -> None:
    rev = _commit(repo_root, branch, DropConstraint(constraint_id=UUID(constraint_id)))
    logger.info(f"dropped constraint {constraint_id} ({rev})")
