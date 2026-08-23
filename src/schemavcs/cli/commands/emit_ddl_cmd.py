"""CLI entry point for emitting DDL for a branch's full history from scratch."""

from pathlib import Path

from schemavcs.dag.persistence import load
from schemavcs.dag.walk import topological_order
from schemavcs.ddl.emitter import emit_ddl


def run(repo_root: Path, branch: str) -> None:
    store = load(repo_root)
    head = store.head(branch)
    ordered_revisions = topological_order(store, head)

    operations = tuple(
        op
        for revision_id in ordered_revisions
        for compound in store.get_node(revision_id).operations
        for op in compound.operations
    )
    print(emit_ddl(operations))
