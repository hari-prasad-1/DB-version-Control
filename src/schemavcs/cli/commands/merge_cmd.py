"""CLI entry point for merging one branch into another."""

import logging
from pathlib import Path

from schemavcs.dag.persistence import load, save
from schemavcs.merge.engine import merge
from schemavcs.merge.resolve import confirm_from_cli
from schemavcs.model_sync.sync import sync_model_file

logger = logging.getLogger(__name__)


def run(repo_root: Path, target_branch: str, source_branch: str) -> None:
    store = load(repo_root)
    result = merge(store, target_branch, source_branch, confirm=confirm_from_cli)
    save(store, repo_root)
    sync_model_file(repo_root, store, target_branch)

    if result.fast_forward:
        logger.info(
            "fast-forwarded %r to %s (%r)", target_branch, result.migration.id, source_branch
        )
    else:
        logger.info(
            "merged %r into %r at %s (%d conflict(s) resolved)",
            source_branch,
            target_branch,
            result.migration.id,
            result.conflicts_resolved,
        )
    for note in result.notes:
        logger.info("note: %s", note)
