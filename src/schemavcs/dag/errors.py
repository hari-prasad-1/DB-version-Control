class AmbiguousMergeBaseError(Exception):
    """Raised when two revisions have more than one maximal common ancestor
    (a criss-cross merge) — refuses to guess which one is correct."""

    def __init__(self, rev_a: str, rev_b: str, candidates: list[str]):
        self.rev_a = rev_a
        self.rev_b = rev_b
        self.candidates = candidates
        super().__init__(
            f"no single merge base for {rev_a!r} and {rev_b!r}: "
            f"multiple candidate ancestors {candidates!r}"
        )


class NothingToMergeError(Exception):
    """Raised when merging a revision with itself, or a branch whose head
    equals the revision it would be merged into."""

    def __init__(self, rev_a: str, rev_b: str):
        self.rev_a = rev_a
        self.rev_b = rev_b
        super().__init__(f"nothing to merge: {rev_a!r} and {rev_b!r} are the same revision")
