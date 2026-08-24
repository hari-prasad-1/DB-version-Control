import logging
from pathlib import Path

from schemavcs.dag.persistence import load, save
from schemavcs.dag.store import BranchNameRetiredError
from schemavcs.model_sync.sync import sync_model_file
from schemavcs.storage.paths import read_current_branch, write_current_branch

logger = logging.getLogger(__name__)


def create(repo_root: Path, name: str, from_branch: str | None = None) -> None:
    store = load(repo_root)
    if store.has_branch(name):
        raise ValueError(f"branch {name!r} already exists")
    if store.is_retired(name):
        raise BranchNameRetiredError(
            f"branch name {name!r} was deleted earlier and can never be reused"
        )

    source = from_branch or read_current_branch(repo_root)
    parent_head = store.head(source)
    store.set_head(name, parent_head)
    save(store, repo_root)
    sync_model_file(repo_root, store, name)
    write_current_branch(repo_root, name)
    logger.info("created branch %r from %r at %s, switched to %r", name, source, parent_head, name)


def delete(repo_root: Path, name: str) -> None:
    store = load(repo_root)
    current = read_current_branch(repo_root)
    if name == current:
        raise ValueError(
            f"cannot delete {name!r}: it's the current branch -- checkout another branch first"
        )
    store.retire_branch(name)
    save(store, repo_root)
    logger.info("deleted branch %r (name is retired, can never be reused)", name)
