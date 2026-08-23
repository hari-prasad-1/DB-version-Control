"""generate-migration: the second, additive authoring path. A human edits
the branch's .schema file directly; this command diffs that edit against
the tracked Snapshot, runs rename detection (confirmed interactively), and
commits the result as one migration -- through the exact same
DagStore.append + sync_model_file path migrate_cmd's CLI verbs use.
"""

import logging
from pathlib import Path

from schemavcs.dag.persistence import load, save
from schemavcs.dag.revision_id import make_revision_id
from schemavcs.dag.walk import replay
from schemavcs.dsl.parser import parse
from schemavcs.model_sync.sync import sync_model_file
from schemavcs.rename_detect.detector import RenameProposal
from schemavcs.snapshot.diff import diff_snapshot
from schemavcs.snapshot.to_operations import generate_operations
from schemavcs.storage.paths import schema_file

logger = logging.getLogger(__name__)


def confirm_rename_from_cli(proposal: RenameProposal) -> bool:
    """Blocks on real terminal input -- the only place a rename proposal
    actually gets accepted or rejected."""
    # similarity is -1.0 specifically for the one-drop-one-add structural
    # fallback (detector.py), where there's no real score to show since
    # nothing else was scored against -- print that plainly instead of a
    # nonsensical negative percentage.
    similarity_text = (
        "no ambiguity, only one candidate on each side"
        if proposal.similarity < 0
        else f"similarity {proposal.similarity:.2f}"
    )
    print(
        f"Detected a possible rename: {proposal.old_column.name!r} -> "
        f"{proposal.new_column.name!r} ({similarity_text})"
    )
    answer = input("Confirm rename? [y/n] ").strip().lower()
    return answer == "y"


def run(repo_root: Path, branch: str) -> None:
    store = load(repo_root)
    head = store.head(branch)
    old_snapshot = replay(store, head, branch)

    text = schema_file(repo_root, branch).read_text()
    new_raw_tables = parse(text)

    diff = diff_snapshot(old_snapshot, new_raw_tables)
    generated = generate_operations(diff, confirm=confirm_rename_from_cli)

    if not generated.operations:
        logger.info("no changes detected in %s", schema_file(repo_root, branch))
        return

    revision_id = make_revision_id((head,), generated.operations)
    store.append(revision_id, branch, (head,), generated.operations)
    save(store, repo_root)
    sync_model_file(repo_root, store, branch)
    logger.info("generated migration %s from %s", revision_id, schema_file(repo_root, branch))
