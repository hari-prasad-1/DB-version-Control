"""Parses .schema DSL text into plain RawTable values -- the read half of
the round-trip dsl/render.py writes. No ids, no Snapshot, no diffing here;
this module's only job is turning text into structured data.
"""

from pathlib import Path

from lark import Lark, Token, Transformer

from schemavcs.dsl.raw import RawCheck, RawColumn, RawForeignKey, RawIndex, RawTable, RawUnique
from schemavcs.model import TypeSpec

_GRAMMAR_PATH = Path(__file__).parent / "grammar.lark"
_parser = Lark(_GRAMMAR_PATH.read_text(), parser="lalr")


class _ToRaw(Transformer):
    def start(self, tables):
        return list(tables)

    def table_def(self, children):
        name = str(children[0])
        members = children[1:]
        columns = tuple(
            RawColumn(name=c.name, type=c.type, nullable=c.nullable, default=c.default, position=i)
            for i, c in enumerate(m for m in members if isinstance(m, RawColumn))
        )
        indexes = tuple(m for m in members if isinstance(m, RawIndex))
        foreign_keys = tuple(m for m in members if isinstance(m, RawForeignKey))
        uniques = tuple(m for m in members if isinstance(m, RawUnique))
        checks = tuple(m for m in members if isinstance(m, RawCheck))
        return RawTable(
            name=name,
            columns=columns,
            indexes=indexes,
            foreign_keys=foreign_keys,
            uniques=uniques,
            checks=checks,
        )

    def member(self, children):
        return children[0]

    def column_def(self, children):
        name = str(children[0])
        type_spec = children[1]
        modifiers = children[2:]
        nullable = True
        default = None
        for kind, value in modifiers:
            if kind == "not_null":
                nullable = False
            elif kind == "default":
                default = value
        return RawColumn(name=name, type=type_spec, nullable=nullable, default=default)

    def not_null(self, _children):
        return ("not_null", None)

    def default(self, children):
        return ("default", children[0])

    def default_value(self, children):
        token: Token = children[0]
        text = str(token)
        if text.startswith('"') and text.endswith('"'):
            return text[1:-1]
        return text

    def type_spec(self, children):
        name = str(children[0])
        params = tuple(int(p) for p in children[1:])
        return TypeSpec(name, params)

    def index_def(self, children):
        name = str(children[0])
        rest = children[1:]
        is_unique = bool(rest) and isinstance(rest[-1], Token) and rest[-1].type == "UNIQUE_KW"
        columns = rest[:-1] if is_unique else rest
        return RawIndex(name=name, columns=tuple(str(c) for c in columns), unique=is_unique)

    def fk_def(self, children):
        *columns, references_table = children
        return RawForeignKey(
            columns=tuple(str(c) for c in columns), references_table=str(references_table)
        )

    def unique_def(self, children):
        return RawUnique(columns=tuple(str(c) for c in children))

    def check_def(self, children):
        return RawCheck(raw_expr=str(children[0]).strip())


def parse(text: str) -> list[RawTable]:
    tree = _parser.parse(text)
    return _ToRaw().transform(tree)
