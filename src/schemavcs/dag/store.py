"""In-memory DAG store: migration nodes plus per-branch head pointers."""

from schemavcs.model import CompoundOperation, Migration, RevisionId


class UnknownRevisionError(Exception):
    pass


class UnknownBranchError(Exception):
    pass


class DagStore:
    def __init__(self) -> None:
        self._nodes: dict[RevisionId, Migration] = {}
        self._heads: dict[str, RevisionId] = {}
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

    def all_revision_ids(self) -> list[RevisionId]:
        return list(self._nodes.keys())

    def all_heads(self) -> dict[str, RevisionId]:
        return dict(self._heads)
