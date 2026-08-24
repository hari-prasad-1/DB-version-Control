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


def rollback(repo_root: Path, name: str, steps: int = 1) -> None:
    """Moves a branch's head back `steps` revisions -- like Rails'
    `db:rollback STEP=n` or `git reset --hard HEAD~n`. Each step is just a
    head-pointer move; no node is ever deleted, so a rolled-back-past node
    stays reachable (by revision id, or if another branch still points at
    or past it) exactly like an orphaned commit after a real git reset.
    Walking a merge node (two parents) always takes the first parent -- the
    side the merge was run "into" -- same ambiguity git itself resolves the
    same way with `HEAD^` vs `HEAD^2`."""
    if steps < 1:
        raise ValueError(f"steps must be >= 1, got {steps}")

    store = load(repo_root)
    revision_id = store.head(name)
    for _ in range(steps):
        node = store.get_node(revision_id)
        if not node.parents:
            raise ValueError(
                f"branch {name!r} has no earlier revision to roll back to "
                f"(reached the root after fewer than {steps} step(s))"
            )
        revision_id = node.parents[0]

    store.set_head(name, revision_id)
    save(store, repo_root)
    sync_model_file(repo_root, store, name)
    logger.info("rolled back %r by %d step(s), now at %s", name, steps, revision_id)
