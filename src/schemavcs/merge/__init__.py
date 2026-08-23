from schemavcs.merge.classify import Classification, ClassifiedGroup, classify
from schemavcs.merge.cross_object import cross_object_pass
from schemavcs.merge.engine import MergeResult, merge
from schemavcs.merge.grouping import IdentityGroup, group_by_identity
from schemavcs.merge.name_collision import NameCollision, find_name_collisions
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
    "NameCollision",
    "ResolutionEngine",
    "TokenAlreadyUsedError",
    "classify",
    "confirm_from_cli",
    "cross_object_pass",
    "find_name_collisions",
    "group_by_identity",
    "merge",
]
