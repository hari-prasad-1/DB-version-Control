"""Generic JSON codec for the model's dataclass tree.

Every dataclass gets serialized as {"__type__": <class name>, **fields}, so a
new Operation variant or model type needs no serialization code of its own —
only a name -> class registry entry to decode it back.
"""

import dataclasses
from typing import Any
from uuid import UUID

from schemavcs.model import operations as op_module
from schemavcs.model import schema as schema_module
from schemavcs.model import snapshot as snapshot_module
from schemavcs.model import types as types_module
from schemavcs.model.migration import Migration

_REGISTRY: dict[str, type] = {}
for _module in (op_module, schema_module, snapshot_module, types_module):
    for _name in dir(_module):
        _obj = getattr(_module, _name)
        if dataclasses.is_dataclass(_obj) and isinstance(_obj, type):
            _REGISTRY[_obj.__name__] = _obj
_REGISTRY[Migration.__name__] = Migration


def to_jsonable(value: Any) -> Any:
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {
            "__type__": type(value).__name__,
            **{f.name: to_jsonable(getattr(value, f.name)) for f in dataclasses.fields(value)},
        }
    if isinstance(value, UUID):
        return {"__type__": "UUID", "hex": value.hex}
    if isinstance(value, list | tuple):
        return [to_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {k: to_jsonable(v) for k, v in value.items()}
    return value


def _is_tuple_field(cls: type, field_name: str) -> bool:
    for f in dataclasses.fields(cls):
        if f.name == field_name:
            return "tuple" in str(f.type)
    return False


def from_jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        type_name = value.get("__type__")
        if type_name == "UUID":
            return UUID(hex=value["hex"])
        if type_name is not None:
            cls = _REGISTRY[type_name]
            kwargs = {}
            for k, v in value.items():
                if k == "__type__":
                    continue
                decoded = from_jsonable(v)
                if isinstance(decoded, list) and _is_tuple_field(cls, k):
                    decoded = tuple(decoded)
                kwargs[k] = decoded
            return cls(**kwargs)
        return {k: from_jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [from_jsonable(v) for v in value]
    return value
