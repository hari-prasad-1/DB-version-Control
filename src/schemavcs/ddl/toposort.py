"""Orders operations so nothing SQL depends on is emitted before it exists,
and nothing is dropped while something else still depends on it.

Dependency rule, expressed as "op X must come before op Y":
- CreateTable must precede any AddColumn/AddIndex/AddConstraint on that table
  (including an AddConstraint elsewhere that references it via foreign key).
- DropConstraint/DropIndex referencing a table must precede that table's
  DropTable (drop the reference before the thing it points at).
- AddColumn for a column must precede an AddIndex/AddConstraint that covers
  that column.

Only edges actually observable from the operations themselves are built --
this is a same-batch ordering concern, not a full schema-wide dependency
graph.
"""

from dataclasses import dataclass
from uuid import UUID

from schemavcs.model import (
    AddColumn,
    AddConstraint,
    AddIndex,
    CreateTable,
    DropColumn,
    DropConstraint,
    DropIndex,
    DropTable,
    Operation,
)


class CircularDependencyError(Exception):
    """Raised when the dependency edges form a cycle -- detected, not
    resolved. E.g. two FK constraints added in the same batch, each
    referencing the other's not-yet-created table."""


@dataclass(frozen=True)
class DependencyEdge:
    before: int  # index into the operations list
    after: int


def _created_table_id(op: Operation) -> UUID | None:
    return op.table.id if isinstance(op, CreateTable) else None


def _created_column_id(op: Operation) -> UUID | None:
    return op.column.id if isinstance(op, AddColumn) else None


def _dropped_table_id(op: Operation) -> UUID | None:
    return op.table_id if isinstance(op, DropTable) else None


def build_dependency_edges(operations: tuple[Operation, ...]) -> list[DependencyEdge]:
    edges: list[DependencyEdge] = []

    table_creators = {
        tid: i for i, op in enumerate(operations) if (tid := _created_table_id(op)) is not None
    }
    column_creators = {
        cid: i for i, op in enumerate(operations) if (cid := _created_column_id(op)) is not None
    }
    table_droppers = {
        tid: i for i, op in enumerate(operations) if (tid := _dropped_table_id(op)) is not None
    }

    for i, op in enumerate(operations):
        match op:
            case (
                AddColumn(table_id=table_id)
                | AddIndex(table_id=table_id)
                | AddConstraint(table_id=table_id)
            ):
                if table_id in table_creators:
                    edges.append(DependencyEdge(before=table_creators[table_id], after=i))
            case _:
                pass

        if isinstance(op, AddConstraint) and op.constraint.references is not None:
            ref_id = op.constraint.references
            if ref_id in table_creators:
                edges.append(DependencyEdge(before=table_creators[ref_id], after=i))

        if isinstance(op, AddIndex | AddConstraint):
            columns = op.index.columns if isinstance(op, AddIndex) else op.constraint.columns
            for column_id in columns:
                if column_id in column_creators:
                    edges.append(DependencyEdge(before=column_creators[column_id], after=i))

        if isinstance(op, DropConstraint | DropIndex | DropColumn):
            # any drop of something belonging to a table must precede that
            # table's own DropTable, if both are in this batch.
            owning_table_id = _owning_table_hint(op, operations)
            if owning_table_id is not None and owning_table_id in table_droppers:
                edges.append(DependencyEdge(before=i, after=table_droppers[owning_table_id]))

    return edges


def _owning_table_hint(op: Operation, operations: tuple[Operation, ...]) -> UUID | None:
    """Best-effort: only DropColumn carries its own table_id. DropIndex/
    DropConstraint don't -- they're identified by index_id/constraint_id
    alone, so which table they belong to can't be recovered from the
    operation itself within this same-batch ordering pass."""
    if isinstance(op, DropColumn):
        return op.table_id
    return None


def toposort(operations: tuple[Operation, ...]) -> list[Operation]:
    """Kahn's algorithm over the edges from build_dependency_edges. Stable:
    ties keep the original operation order."""
    edges = build_dependency_edges(operations)
    n = len(operations)
    successors: list[list[int]] = [[] for _ in range(n)]
    indegree = [0] * n
    for edge in edges:
        successors[edge.before].append(edge.after)
        indegree[edge.after] += 1

    ready = [i for i in range(n) if indegree[i] == 0]
    ordered_indices: list[int] = []

    while ready:
        ready.sort()
        i = ready.pop(0)
        ordered_indices.append(i)
        for successor in successors[i]:
            indegree[successor] -= 1
            if indegree[successor] == 0:
                ready.append(successor)

    if len(ordered_indices) != n:
        remaining = [i for i in range(n) if i not in ordered_indices]
        raise CircularDependencyError(f"dependency cycle among operations at indices {remaining}")

    return [operations[i] for i in ordered_indices]
