import logging
from pathlib import Path

from schemavcs.dag.persistence import load, save
from schemavcs.model_sync.sync import sync_model_file
from schemavcs.storage.paths import read_current_branch, write_current_branch

logger = logging.getLogger(__name__)


def create(repo_root: Path, name: str, from_branch: str | None = None) -> None:
    store = load(repo_root)
    if store.has_branch(name):
        raise ValueError(f"branch {name!r} already exists")

    source = from_branch or read_current_branch(repo_root)
    parent_head = store.head(source)
    store.set_head(name, parent_head)
    save(store, repo_root)
    sync_model_file(repo_root, store, name)
    write_current_branch(repo_root, name)
    logger.info("created branch %r from %r at %s, switched to %r", name, source, parent_head, name)
