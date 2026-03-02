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


def _unwrap_refinement(ty: Type) -> Type:
    """Unwrap a RefinementType to its base type for compatibility checks.

    A refinement type (e.g. Price = Decimal where value > 0) is a subtype
    of its base and should be compatible wherever the base is expected.
    """
    while isinstance(ty, RefinementType) and ty.base is not None:
        ty = ty.base
    return ty


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
    expected = _unwrap_refinement(expected)
    actual = _unwrap_refinement(actual)
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


# ── Type variable resolution ───────────────────────────────


def resolve_type_vars(
    sig_params: list[Type], actual_args: list[Type],
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
