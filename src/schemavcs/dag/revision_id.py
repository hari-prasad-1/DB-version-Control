"""Generates a Migration's RevisionId: a content hash, never sequential or
timestamp-based, so ids never collide across independently-numbered branches
and carry no false causal ordering.

A random nonce is mixed in so that authoring the same edit twice (even by
mistake, on the same parent) still gets a distinct id rather than silently
colliding with the first one."""

import hashlib
import json
from uuid import uuid4

from schemavcs.model import CompoundOperation, RevisionId
from schemavcs.model.serialize import to_jsonable


def make_revision_id(
    parents: tuple[RevisionId, ...], operations: tuple[CompoundOperation, ...]
) -> RevisionId:
    payload = json.dumps(
        {
            "parents": list(parents),
            "operations": to_jsonable(operations),
            "nonce": uuid4().hex,
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:12]
