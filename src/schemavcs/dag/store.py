"""In-memory DAG store: migration nodes plus per-branch head pointers."""

from schemavcs.model import CompoundOperation, Migration, RevisionId


class UnknownRevisionError(Exception):
    pass


class UnknownBranchError(Exception):
    pass


class BranchNameRetiredError(Exception):
    """Raised when creating/reusing a branch name that was deleted before.
    Old migration history stays valid and readable after its branch name is
    deleted; the one thing worth guarding against is a NEW branch later
    reusing that exact name, which would make old history look like it
    belongs to an unrelated branch of the same name."""


class DagStore:
    def __init__(self) -> None:
        self._nodes: dict[RevisionId, Migration] = {}
        self._heads: dict[str, RevisionId] = {}
        self._retired_branches: set[str] = set()
        # Ancestor sets never change once computed — nodes are immutable
        # after append, so a revision's parents (and thus its ancestors)
        # never change either.
        self._ancestor_cache: dict[RevisionId, set[RevisionId]] = {}

    def cached_ancestors(self, revision_id: RevisionId) -> set[RevisionId] | None:
        return self._ancestor_cache.get(revision_id)

    def cache_ancestors(self, revision_id: RevisionId, result: set[RevisionId]) -> None:
        self._ancestor_cache[revision_id] = result

    def get_node(self, revision_id: RevisionId) -> Migration:
        try:
            return self._nodes[revision_id]
        except KeyError:
            raise UnknownRevisionError(revision_id) from None

    def has_node(self, revision_id: RevisionId) -> bool:
        return revision_id in self._nodes

    def append(
        self,
        revision_id: RevisionId,
        branch: str,
        parents: tuple[RevisionId, ...],
        operations: tuple[CompoundOperation, ...] = (),
    ) -> Migration:
        for parent in parents:
            if not self.has_node(parent):
                raise UnknownRevisionError(parent)
        node = Migration(id=revision_id, parents=parents, branch=branch, operations=operations)
        self._nodes[revision_id] = node
        self._heads[branch] = revision_id
        return node

    def head(self, branch: str) -> RevisionId:
        try:
            return self._heads[branch]
        except KeyError:
            raise UnknownBranchError(branch) from None

    def set_head(self, branch: str, revision_id: RevisionId) -> None:
        if not self.has_node(revision_id):
            raise UnknownRevisionError(revision_id)
        self._heads[branch] = revision_id

    def has_branch(self, branch: str) -> bool:
        return branch in self._heads

    def replace_all_heads(self, heads: dict[str, RevisionId]) -> None:
        """Loader-only escape hatch: `append()` sets a head for every node's
        own `.branch` field as a side effect of replaying history, which is
        wrong for a branch that was later deleted -- its last node still
        claims that branch name. `persistence.load()` uses this to reset
        `_heads` to exactly what `heads.json` (the real source of truth for
        "what branches currently exist") says, discarding whatever replay
        happened to leave behind."""
        self._heads = dict(heads)

    def retire_branch(self, branch: str) -> None:
        """Deletes a branch: its head pointer is removed, but the migration
        nodes it pointed at are untouched and stay reachable through any
        other branch that shares ancestry with them (e.g. a branch merged
        from it earlier). The name itself is retired permanently -- see
        BranchNameRetiredError."""
        if not self.has_branch(branch):
            raise UnknownBranchError(branch)
        del self._heads[branch]
        self._retired_branches.add(branch)

    def retire_branch_from_load(self, branch: str) -> None:
        """Restores retired-branch state from disk. Unlike `retire_branch`,
        doesn't require the branch to currently have a head -- by the time
        this runs during load(), the head was already omitted from the
        persisted heads.json, exactly as retire_branch left it."""
        self._retired_branches.add(branch)

    def is_retired(self, branch: str) -> bool:
        return branch in self._retired_branches

    def all_retired(self) -> set[str]:
        return set(self._retired_branches)

    def all_revision_ids(self) -> list[RevisionId]:
        return list(self._nodes.keys())

    def all_heads(self) -> dict[str, RevisionId]:
        return dict(self._heads)
