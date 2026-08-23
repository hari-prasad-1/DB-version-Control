from schemavcs.merge.classify import Classification, ClassifiedGroup, classify
from schemavcs.merge.cross_object import cross_object_pass
from schemavcs.merge.engine import MergeResult, merge
from schemavcs.merge.grouping import IdentityGroup, group_by_identity
from schemavcs.merge.resolve import (
    HumanConfirmationToken,
    ResolutionEngine,
    TokenAlreadyUsedError,
    confirm_from_cli,
)

__all__ = [
    "Classification",
    "ClassifiedGroup",
    "HumanConfirmationToken",
    "IdentityGroup",
    "MergeResult",
    "ResolutionEngine",
    "TokenAlreadyUsedError",
    "classify",
    "confirm_from_cli",
    "cross_object_pass",
    "group_by_identity",
    "merge",
]
