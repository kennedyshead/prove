"""Resolved type representations for the Prove type system.

These are distinct from AST TypeExpr nodes (which are syntactic).
Resolved types are produced during semantic analysis.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# ── Resolved types ──────────────────────────────────────────────


@dataclass(frozen=True)
class PrimitiveType:
    name: str
    modifiers: tuple[str, ...] = ()


@dataclass(frozen=True)
class UnitType:
    pass


@dataclass(frozen=True)
class VariantInfo:
    name: str
    fields: dict[str, Type] = field(default_factory=dict)


@dataclass(frozen=True)
class RecordType:
    name: str
    fields: dict[str, Type] = field(default_factory=dict)
    type_params: tuple[str, ...] = ()


@dataclass(frozen=True)
class AlgebraicType:
    name: str
    variants: list[VariantInfo] = field(default_factory=list)
    type_params: tuple[str, ...] = ()


@dataclass(frozen=True)
class RefinementType:
    name: str
    base: Type = None  # type: ignore[assignment]


@dataclass(frozen=True)
class GenericInstance:
    base_name: str
    args: list[Type] = field(default_factory=list)


@dataclass(frozen=True)
class TypeVariable:
    name: str


@dataclass(frozen=True)
class FunctionType:
    param_types: list[Type] = field(default_factory=list)
    return_type: Type = None  # type: ignore[assignment]


@dataclass(frozen=True)
class ListType:
    element: Type = None  # type: ignore[assignment]


@dataclass(frozen=True)
class ErrorType:
    """Poison type that suppresses cascading errors."""
    pass


Type = (
    PrimitiveType | UnitType | RecordType | AlgebraicType
    | RefinementType | GenericInstance | TypeVariable
    | FunctionType | ListType | ErrorType | VariantInfo
)


# ── Built-in type constants ─────────────────────────────────────

INTEGER = PrimitiveType("Integer")
DECIMAL = PrimitiveType("Decimal")
FLOAT = PrimitiveType("Float")
BOOLEAN = PrimitiveType("Boolean")
STRING = PrimitiveType("String")
CHARACTER = PrimitiveType("Character")
BYTE = PrimitiveType("Byte")
UNIT = UnitType()
ERROR_TY = ErrorType()

BUILTINS: dict[str, Type] = {
    "Integer": INTEGER,
    "Decimal": DECIMAL,
    "Float": FLOAT,
    "Boolean": BOOLEAN,
    "String": STRING,
    "Character": CHARACTER,
    "Byte": BYTE,
    "Unit": UNIT,
}


# ── Type utilities ──────────────────────────────────────────────


def type_name(ty: Type) -> str:
    """Human-readable name for diagnostics."""
    if isinstance(ty, PrimitiveType):
        if ty.modifiers:
            mods = " ".join(ty.modifiers)
            return f"{ty.name}:[{mods}]"
        return ty.name
    if isinstance(ty, UnitType):
        return "Unit"
    if isinstance(ty, RecordType):
        return ty.name
    if isinstance(ty, AlgebraicType):
        return ty.name
    if isinstance(ty, RefinementType):
        return ty.name
    if isinstance(ty, GenericInstance):
        args = ", ".join(type_name(a) for a in ty.args)
        return f"{ty.base_name}<{args}>"
    if isinstance(ty, TypeVariable):
        return ty.name
    if isinstance(ty, FunctionType):
        params = ", ".join(type_name(p) for p in ty.param_types)
        ret = type_name(ty.return_type)
        return f"({params}) -> {ret}"
    if isinstance(ty, ListType):
        return f"List<{type_name(ty.element)}>"
    if isinstance(ty, ErrorType):
        return "<error>"
    if isinstance(ty, VariantInfo):
        return ty.name
    return str(ty)


def types_compatible(expected: Type, actual: Type) -> bool:
    """Check structural compatibility between two types.

    ErrorType and TypeVariable are compatible with anything to prevent
    cascading errors and allow generic params through without full inference.
    """
    if isinstance(expected, ErrorType) or isinstance(actual, ErrorType):
        return True
    if isinstance(expected, TypeVariable) or isinstance(actual, TypeVariable):
        return True
    if type(expected) is not type(actual):
        return False
    if isinstance(expected, PrimitiveType) and isinstance(actual, PrimitiveType):
        return expected.name == actual.name
    if isinstance(expected, UnitType):
        return True
    if isinstance(expected, RecordType) and isinstance(actual, RecordType):
        return expected.name == actual.name
    if isinstance(expected, AlgebraicType) and isinstance(actual, AlgebraicType):
        return expected.name == actual.name
    if isinstance(expected, RefinementType) and isinstance(actual, RefinementType):
        return expected.name == actual.name
    if isinstance(expected, GenericInstance) and isinstance(actual, GenericInstance):
        if expected.base_name != actual.base_name:
            return False
        if len(expected.args) != len(actual.args):
            return False
        return all(types_compatible(e, a) for e, a in zip(expected.args, actual.args))
    if isinstance(expected, FunctionType) and isinstance(actual, FunctionType):
        if len(expected.param_types) != len(actual.param_types):
            return False
        if not all(
            types_compatible(e, a)
            for e, a in zip(expected.param_types, actual.param_types)
        ):
            return False
        return types_compatible(expected.return_type, actual.return_type)
    if isinstance(expected, ListType) and isinstance(actual, ListType):
        return types_compatible(expected.element, actual.element)
    return expected == actual
