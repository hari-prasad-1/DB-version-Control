"""Regenerates a branch's tracked .schema file from its current state.

Called after every authored migration so the model file is always
current-state truth, independent of whether anything ever reads it back
for diffing (that comes in Phase 2)."""

from pathlib import Path

from schemavcs.dag.store import DagStore
from schemavcs.dag.walk import replay
from schemavcs.dsl.render import render_snapshot
from schemavcs.storage.paths import schema_file, schemas_dir


def sync_model_file(repo_root: Path, store: DagStore, branch: str) -> None:
    schemas_dir(repo_root).mkdir(parents=True, exist_ok=True)
    snapshot = replay(store, store.head(branch), branch)
    schema_file(repo_root, branch).write_text(render_snapshot(snapshot))
