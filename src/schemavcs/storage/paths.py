"""Resolves the .schemavcs/ repo-local storage layout."""

from pathlib import Path

STORAGE_DIRNAME = ".schemavcs"


class RepoNotInitializedError(Exception):
    pass


def find_repo_root(start: Path | None = None) -> Path:
    """Walk upward from `start` (default: cwd) for a `.schemavcs/` directory."""
    current = (start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if (candidate / STORAGE_DIRNAME).is_dir():
            return candidate
    raise RepoNotInitializedError(f"no {STORAGE_DIRNAME}/ found above {current}")


def storage_dir(repo_root: Path) -> Path:
    return repo_root / STORAGE_DIRNAME


def snapshots_dir(repo_root: Path) -> Path:
    return storage_dir(repo_root) / "snapshots"


def dag_nodes_dir(repo_root: Path) -> Path:
    return storage_dir(repo_root) / "dag" / "nodes"


def dag_heads_file(repo_root: Path) -> Path:
    return storage_dir(repo_root) / "dag" / "heads.json"


def init_storage(repo_root: Path) -> None:
    snapshots_dir(repo_root).mkdir(parents=True, exist_ok=True)
    dag_nodes_dir(repo_root).mkdir(parents=True, exist_ok=True)
    if not dag_heads_file(repo_root).exists():
        dag_heads_file(repo_root).write_text("{}\n")
