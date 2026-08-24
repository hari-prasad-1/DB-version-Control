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


def dag_retired_branches_file(repo_root: Path) -> Path:
    """Names of branches that were once created, then deleted. Kept
    forever, separate from `heads.json`, so a deleted name can never be
    reused for a new branch -- old migration history stays valid and
    readable even after its branch name is gone, but nothing should ever
    look like it belongs to an unrelated new branch of the same name."""
    return storage_dir(repo_root) / "dag" / "retired_branches.json"


def current_branch_file(repo_root: Path) -> Path:
    """The repo's current branch pointer — analogous to Git's HEAD, but
    always a plain branch name (no detached-HEAD state in this design)."""
    return storage_dir(repo_root) / "HEAD"


def read_current_branch(repo_root: Path) -> str:
    return current_branch_file(repo_root).read_text().strip()


def write_current_branch(repo_root: Path, branch: str) -> None:
    current_branch_file(repo_root).write_text(f"{branch}\n")


def schemas_dir(repo_root: Path) -> Path:
    """Visible (not under .schemavcs/) directory holding each branch's
    current model as a plain .schema file — human-inspectable, Rails
    schema.rb-style, kept in sync after every authored migration."""
    return repo_root / "schemas"


def schema_file(repo_root: Path, branch: str) -> Path:
    return schemas_dir(repo_root) / f"{branch}.schema"


def init_storage(repo_root: Path) -> None:
    snapshots_dir(repo_root).mkdir(parents=True, exist_ok=True)
    dag_nodes_dir(repo_root).mkdir(parents=True, exist_ok=True)
    schemas_dir(repo_root).mkdir(parents=True, exist_ok=True)
    if not dag_heads_file(repo_root).exists():
        dag_heads_file(repo_root).write_text("{}\n")
