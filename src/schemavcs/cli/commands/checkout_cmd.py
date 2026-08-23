from pathlib import Path

from schemavcs.dag.persistence import load
from schemavcs.storage.paths import write_current_branch


def run(repo_root: Path, branch: str) -> None:
    store = load(repo_root)
    if not store.has_branch(branch):
        raise ValueError(f"branch {branch!r} does not exist")
    write_current_branch(repo_root, branch)
    print(f"switched to branch {branch!r}")
