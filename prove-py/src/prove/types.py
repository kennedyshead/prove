"""Resolved type representations for the Prove type system.

These are distinct from AST TypeExpr nodes (which are syntactic).
Resolved types are produced during semantic analysis.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from prove.ast_nodes import Expr

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
    constraint: Optional["Expr"] = None


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


@dataclass(frozen=True)
class BorrowType:
    """Type representing a borrowed reference (compiler-inferred read-only borrow)."""

    inner: Type


Type = (
    PrimitiveType
    | UnitType
    | RecordType
    | AlgebraicType
    | RefinementType
    | GenericInstance
    | TypeVariable
    | FunctionType
    | ListType
    | ErrorType
    | VariantInfo
    | BorrowType
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

# Numeric widening hierarchy: Integer → Decimal → Float
_NUMERIC_RANK: dict[str, int] = {
    "Integer": 0,
    "Decimal": 1,
    "Float": 2,
}


def numeric_widen(a: Type, b: Type) -> Type | None:
    """Return the wider numeric type, or None if not both numeric.

    Unwraps refinement types so that e.g. Price (Decimal where ...)
    widens correctly against Integer.
    """
    ua = _unwrap_refinement(a)
    ub = _unwrap_refinement(b)
    if not (isinstance(ua, PrimitiveType) and isinstance(ub, PrimitiveType)):
        return None
    ra = _NUMERIC_RANK.get(ua.name)
    rb = _NUMERIC_RANK.get(ub.name)
    if ra is None or rb is None:
        return None
    return a if ra >= rb else b


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

# ── Built-in function names ────────────────────────────────────

BUILTIN_FUNCTIONS: frozenset[str] = frozenset(
    {
        "len",
        "map",
        "each",
        "filter",
        "reduce",
        "to_string",
        "clamp",
    }
)

HOF_BUILTINS: frozenset[str] = frozenset({"map", "filter", "reduce", "each"})


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
    if isinstance(ty, BorrowType):
        return f"&{type_name(ty.inner)}"
    return str(ty)


def _unwrap_refinement(ty: Type) -> Type:
    """Unwrap a RefinementType to its base type for compatibility checks.

    A refinement type (e.g. Price = Decimal where value > 0) is a subtype
    of its base and should be compatible wherever the base is expected.
    """
    while isinstance(ty, RefinementType) and ty.base is not None:
        ty = ty.base
    return ty


_JSON_SERIALIZABLE_PRIMITIVES = frozenset(
    {
        "String",
        "Integer",
        "Float",
        "Decimal",
        "Boolean",
        "Character",
        "Byte",
        "Value",
    }
)


def is_json_serializable(ty: Type) -> bool:
    """Return True if *ty* can be automatically converted to Value.

    Serializable types: primitives in _JSON_SERIALIZABLE_PRIMITIVES,
    records whose fields are all serializable, List/Option/Table of
    serializable inner types, and refinements of serializable bases.
    """
    if isinstance(ty, PrimitiveType):
        return ty.name in _JSON_SERIALIZABLE_PRIMITIVES
    if isinstance(ty, TypeVariable):
        return ty.name in _JSON_SERIALIZABLE_PRIMITIVES
    if isinstance(ty, RecordType):
        return all(is_json_serializable(ft) for ft in ty.fields.values())
    if isinstance(ty, GenericInstance):
        if ty.base_name in ("List", "Option", "Table"):
            return all(is_json_serializable(a) for a in ty.args)
        return False
    if isinstance(ty, ListType):
        return is_json_serializable(ty.element)
    if isinstance(ty, RefinementType):
        return ty.base is not None and is_json_serializable(ty.base)
    return False


def types_compatible(expected: Type, actual: Type) -> bool:
    """Check structural compatibility between two types.

    ErrorType and TypeVariable are compatible with anything to prevent
    cascading errors and allow generic params through without full inference.
    Refinement types are compatible with their base type.
    """
    if isinstance(expected, ErrorType) or isinstance(actual, ErrorType):
        return True
    if isinstance(expected, TypeVariable) or isinstance(actual, TypeVariable):
        return True
    # Unwrap refinement types so Price (Decimal where ...) is
    # compatible with Decimal and with other Decimal refinements.
    # Allow T → Option<Refinement(T)>: when the Option's inner type is a
    # RefinementType whose base matches actual, the assignment is valid
    # (Option wraps the boundary-failure case).
    if isinstance(expected, GenericInstance) and expected.base_name == "Option" and expected.args:
        inner = expected.args[0]
        if isinstance(inner, RefinementType) and types_compatible(inner.base, actual):
            return True
    expected = _unwrap_refinement(expected)
    actual = _unwrap_refinement(actual)
    # BorrowType is compatible with its inner type for read-only access
    if isinstance(expected, BorrowType):
        return types_compatible(expected.inner, actual)
    if isinstance(actual, BorrowType):
        return types_compatible(expected, actual.inner)
    if isinstance(expected, PrimitiveType) and expected.modifiers:
        if isinstance(actual, (RecordType, AlgebraicType)):
            return expected.name == actual.name
    if isinstance(actual, PrimitiveType) and actual.modifiers:
        if isinstance(expected, (RecordType, AlgebraicType)):
            return actual.name == expected.name
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
            types_compatible(e, a) for e, a in zip(expected.param_types, actual.param_types)
        ):
            return False
        return types_compatible(expected.return_type, actual.return_type)
    if isinstance(expected, ListType) and isinstance(actual, ListType):
        return types_compatible(expected.element, actual.element)
    return expected == actual


# ── Type variable resolution ───────────────────────────────


def resolve_type_vars(
    sig_params: list[Type],
    actual_args: list[Type],
) -> dict[str, Type]:
    """Unify signature params against actual arg types to bind type variables.

    Walks (sig_param, actual_arg) pairs.  When a TypeVariable is found in the
    signature tree, it is bound to the corresponding actual type.  For
    GenericInstance and ListType the function recurses into their arguments.
    """
    bindings: dict[str, Type] = {}

    def _unify(sig: Type, actual: Type) -> None:
        if isinstance(sig, TypeVariable):
            if sig.name not in bindings:
                bindings[sig.name] = actual
            return
        if isinstance(sig, GenericInstance) and isinstance(actual, GenericInstance):
            if sig.base_name == actual.base_name:
                for s, a in zip(sig.args, actual.args):
                    _unify(s, a)
            return
        if isinstance(sig, ListType) and isinstance(actual, ListType):
            _unify(sig.element, actual.element)
            return

    for sp, aa in zip(sig_params, actual_args):
        _unify(sp, aa)
    return bindings


def substitute_type_vars(ty: Type, bindings: dict[str, Type]) -> Type:
    """Replace TypeVariable nodes in *ty* using *bindings*."""
    if isinstance(ty, TypeVariable):
        return bindings.get(ty.name, ty)
    if isinstance(ty, GenericInstance):
        new_args = [substitute_type_vars(a, bindings) for a in ty.args]
        return GenericInstance(ty.base_name, new_args)
    if isinstance(ty, ListType):
        return ListType(substitute_type_vars(ty.element, bindings))
    return ty


# ── Ownership helpers ─────────────────────────────────────────────


def has_own_modifier(ty: Type) -> bool:
    """Check if a type has the Own (linear) ownership modifier."""
    if isinstance(ty, PrimitiveType):
        return "Own" in ty.modifiers
    return False


def has_mutable_modifier(ty: Type) -> bool:
    """Check if a type has the Mutable modifier."""
    if isinstance(ty, PrimitiveType):
        return "Mutable" in ty.modifiers
    return False


def get_ownership_kind(ty: Type) -> str:
    """Return the ownership kind: 'owned', 'mutable', or 'shared'."""
    if isinstance(ty, PrimitiveType):
        if "Own" in ty.modifiers:
            return "owned"
        if "Mutable" in ty.modifiers:
            return "mutable"
    return "shared"
