import logging
from pathlib import Path

from schemavcs.dag import DagStore
from schemavcs.dag.persistence import save
from schemavcs.dag.revision_id import make_revision_id
from schemavcs.model_sync.sync import sync_model_file
from schemavcs.storage.paths import init_storage, write_current_branch

ROOT_BRANCH = "main"

logger = logging.getLogger(__name__)


def run(repo_root: Path) -> None:
    init_storage(repo_root)
    store = DagStore()
    root_id = make_revision_id((), ())
    store.append(root_id, ROOT_BRANCH, ())
    save(store, repo_root)
    sync_model_file(repo_root, store, ROOT_BRANCH)
    write_current_branch(repo_root, ROOT_BRANCH)
    logger.info("initialized empty schemavcs repo at %s", repo_root / ".schemavcs")
