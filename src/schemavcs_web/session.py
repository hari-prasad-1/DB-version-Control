"""One demo repo per browser session, plus one WebConfirmBridge-backed
session per in-flight merge or rename-detection run. Everything here is an
in-process dict -- no persistence beyond this process's lifetime, which
matches the project's explicit scope for this web layer: a demo tool for
walking through the engine, not a multi-user production service. There is
no cross-session concurrency handling because there is no cross-session
resource sharing -- each browser session gets its own temp directory, and
`storage/paths.py`'s lack of file-locking (documented in decisions.md) is
therefore never actually exercised by more than one writer at a time here.
"""

import tempfile
import threading
from dataclasses import dataclass, field
from pathlib import Path
from uuid import uuid4

from schemavcs.cli.commands import init_cmd
from schemavcs.dag.persistence import load
from schemavcs.dag.store import DagStore
from schemavcs.merge.classify import ClassifiedGroup
from schemavcs.merge.resolve import HumanConfirmationToken
from schemavcs.rename_detect.detector import RenameProposal
from schemavcs_web.bridge import WebConfirmBridge


@dataclass
class RepoSession:
    session_id: str
    repo_root: Path


@dataclass
class MergeSession:
    session_id: str
    repo_root: Path
    store: DagStore
    target_branch: str
    source_branch: str
    bridge: WebConfirmBridge[ClassifiedGroup, HumanConfirmationToken] = field(
        default_factory=WebConfirmBridge
    )


@dataclass
class RenameSession:
    session_id: str
    branch: str
    bridge: WebConfirmBridge[RenameProposal, bool] = field(default_factory=WebConfirmBridge)


class SessionStore:
    """Process-global registry. Guarded by a lock for dict mutation only --
    a session's own worker thread is the only writer to its own bridge, so
    the lock never needs to protect anything beyond registering/looking up
    entries in these three dicts."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._repos: dict[str, RepoSession] = {}
        self._merges: dict[str, MergeSession] = {}
        self._renames: dict[str, RenameSession] = {}

    def create_repo_session(self) -> RepoSession:
        session_id = uuid4().hex
        repo_root = Path(tempfile.mkdtemp(prefix="schemavcs_web_"))
        init_cmd.run(repo_root)
        session = RepoSession(session_id=session_id, repo_root=repo_root)
        with self._lock:
            self._repos[session_id] = session
        return session

    def get_repo_session(self, session_id: str) -> RepoSession | None:
        with self._lock:
            return self._repos.get(session_id)

    def load_store(self, repo_session: RepoSession) -> DagStore:
        return load(repo_session.repo_root)

    def register_merge_session(self, session: MergeSession) -> None:
        with self._lock:
            self._merges[session.session_id] = session

    def get_merge_session(self, session_id: str) -> MergeSession | None:
        with self._lock:
            return self._merges.get(session_id)

    def register_rename_session(self, session: RenameSession) -> None:
        with self._lock:
            self._renames[session.session_id] = session

    def get_rename_session(self, session_id: str) -> RenameSession | None:
        with self._lock:
            return self._renames.get(session_id)
