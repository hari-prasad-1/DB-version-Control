"""Type specification and default-value expression used on Column."""

from dataclasses import dataclass


@dataclass(frozen=True)
class TypeSpec:
    name: str
    params: tuple[int, ...] = ()

    def __str__(self) -> str:
        if not self.params:
            return self.name
        return f"{self.name}({', '.join(str(p) for p in self.params)})"


@dataclass(frozen=True)
class Expr:
    """A stored expression (column default, etc). Opaque — never parsed or evaluated
    by this tool, only carried through to DDL emission verbatim."""

    raw: str

    def __str__(self) -> str:
        return self.raw
