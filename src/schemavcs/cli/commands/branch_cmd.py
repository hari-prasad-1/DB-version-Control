from pathlib import Path

from schemavcs.dag.persistence import load, save
from schemavcs.storage.paths import read_current_branch, write_current_branch


def create(repo_root: Path, name: str, from_branch: str | None = None) -> None:
    store = load(repo_root)
    if store.has_branch(name):
        raise ValueError(f"branch {name!r} already exists")

    source = from_branch or read_current_branch(repo_root)
    parent_head = store.head(source)
    store.set_head(name, parent_head)
    save(store, repo_root)
    write_current_branch(repo_root, name)
    print(f"created branch {name!r} from {source!r} at {parent_head}, switched to {name!r}")
