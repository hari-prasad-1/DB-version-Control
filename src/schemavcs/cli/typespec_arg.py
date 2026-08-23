"""Parses a CLI-typed type expression like "string(255)" or "uuid" into a TypeSpec."""

import re

from schemavcs.model import TypeSpec

_PATTERN = re.compile(r"^(?P<name>[a-zA-Z_][a-zA-Z0-9_]*)(\((?P<params>[0-9, ]+)\))?$")


def parse_type_spec(text: str) -> TypeSpec:
    match = _PATTERN.match(text.strip())
    if not match:
        raise ValueError(f"invalid type expression: {text!r}")
    name = match.group("name")
    params_text = match.group("params")
    params = tuple(int(p.strip()) for p in params_text.split(",")) if params_text else ()
    return TypeSpec(name, params)
