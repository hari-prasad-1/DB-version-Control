"""Persists a DagStore to and loads it from the .schemavcs/dag/ JSON layout."""

import json
from pathlib import Path

from schemavcs.dag.store import DagStore
from schemavcs.model.serialize import from_jsonable, to_jsonable
from schemavcs.storage.paths import dag_heads_file, dag_nodes_dir


def save(store: DagStore, repo_root: Path) -> None:
    nodes_dir = dag_nodes_dir(repo_root)
    nodes_dir.mkdir(parents=True, exist_ok=True)
    for revision_id in store.all_revision_ids():
        node = store.get_node(revision_id)
        (nodes_dir / f"{revision_id}.json").write_text(json.dumps(to_jsonable(node), indent=2))
    dag_heads_file(repo_root).write_text(json.dumps(store.all_heads(), indent=2))


def load(repo_root: Path) -> DagStore:
    store = DagStore()
    nodes_dir = dag_nodes_dir(repo_root)
    if not nodes_dir.is_dir():
        return store

    raw_nodes = {}
    for path in nodes_dir.glob("*.json"):
        node = from_jsonable(json.loads(path.read_text()))
        raw_nodes[node.id] = node

    for node in _topologically_sorted(raw_nodes):
        store.append(node.id, node.branch, tuple(node.parents), tuple(node.operations))

    # append() above sets a head for every node's own `.branch` field as a
    # side effect of replaying it -- correct for a branch that's still
    # alive (its last node's branch IS its current head), but wrong for a
    # branch that was later deleted: its last node still claims that
    # branch name, so it would silently reappear as a live head unless
    # heads.json (the actual source of truth for "what branches currently
    # exist") is applied as a real overwrite, not just a set of additions.
    store.replace_all_heads({})
    heads_file = dag_heads_file(repo_root)
    if heads_file.exists():
        for branch, revision_id in json.loads(heads_file.read_text()).items():
            store.set_head(branch, revision_id)

    return store


def _topologically_sorted(raw_nodes: dict) -> list:
    """Order nodes so every parent is appended before its child — required
    since DagStore.append validates that referenced parents already exist."""
    visited: set = set()
    ordered: list = []

    def visit(revision_id: str) -> None:
        if revision_id in visited:
            return
        visited.add(revision_id)
        node = raw_nodes[revision_id]
        for parent in node.parents:
            visit(parent)
        ordered.append(node)

    for revision_id in raw_nodes:
        visit(revision_id)
    return ordered
