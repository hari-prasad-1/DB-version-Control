from pathlib import Path

from schemavcs.dag import DagStore
from schemavcs.dag.persistence import save
from schemavcs.dag.revision_id import make_revision_id
from schemavcs.model_sync.sync import sync_model_file
from schemavcs.storage.paths import init_storage, write_current_branch

ROOT_BRANCH = "main"


def run(repo_root: Path) -> None:
    init_storage(repo_root)
    store = DagStore()
    root_id = make_revision_id((), ())
    store.append(root_id, ROOT_BRANCH, ())
    save(store, repo_root)
    sync_model_file(repo_root, store, ROOT_BRANCH)
    write_current_branch(repo_root, ROOT_BRANCH)
    print(f"initialized empty schemavcs repo at {repo_root / '.schemavcs'}")
