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
class StructType:
    """Row-polymorphic structural type.

    A bare StructType() (no required_fields) means "any record".
    With required_fields populated (via `with` constraints), it means
    "any record that has at least these fields with these types".
    """

    required_fields: dict[str, Type] = field(default_factory=dict)


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
class ArrayType:
    element: Type = None  # type: ignore[assignment]
    modifiers: tuple[str, ...] = ()


@dataclass(frozen=True)
class ErrorType:
    """Poison type that suppresses cascading errors."""

    pass


@dataclass(frozen=True)
class BorrowType:
    """Type representing a borrowed reference (compiler-inferred read-only borrow)."""

    inner: Type


@dataclass(frozen=True)
class EffectType:
    """Type annotated with effects (IO, Fail, Async).

    Wraps a base type with a set of effect labels. For V1.0, effects
    are informational — violations produce warnings, not errors.
    """

    base: "Type"
    effects: frozenset[str]


Type = (
    PrimitiveType
    | UnitType
    | RecordType
    | StructType
    | AlgebraicType
    | RefinementType
    | GenericInstance
    | TypeVariable
    | FunctionType
    | ListType
    | ArrayType
    | ErrorType
    | VariantInfo
    | BorrowType
    | EffectType
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
ATTACHED = PrimitiveType("Attached")
STRUCT = StructType()
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
    "Struct": STRUCT,
}

# ── Built-in function names ────────────────────────────────────

BUILTIN_FUNCTIONS: frozenset[str] = frozenset(
    {
        "len",
        "map",
        "each",
        "filter",
        "reduce",
        "par_map",
        "par_filter",
        "par_reduce",
        "par_each",
        "to_string",
        "clamp",
    }
)

HOF_BUILTINS: frozenset[str] = frozenset(
    {"map", "filter", "reduce", "each", "par_map", "par_filter", "par_reduce", "par_each"}
)


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
    if isinstance(ty, StructType):
        if ty.required_fields:
            fields = ", ".join(
                f"{n}: {type_name(t)}" for n, t in ty.required_fields.items()
            )
            return f"Struct with {{{fields}}}"
        return "Struct"
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
    if isinstance(ty, ArrayType):
        name = f"Array<{type_name(ty.element)}>"
        if ty.modifiers:
            return f"{name}:[{', '.join(ty.modifiers)}]"
        return name
    if isinstance(ty, ErrorType):
        return "<error>"
    if isinstance(ty, VariantInfo):
        return ty.name
    if isinstance(ty, BorrowType):
        return f"&{type_name(ty.inner)}"
    if isinstance(ty, EffectType):
        effs = " & ".join(sorted(ty.effects))
        return f"{type_name(ty.base)} & {effs}"
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
    if isinstance(ty, StructType):
        return all(is_json_serializable(ft) for ft in ty.required_fields.values())
    if isinstance(ty, GenericInstance):
        if ty.base_name in ("List", "Option", "Table"):
            return all(is_json_serializable(a) for a in ty.args)
        return False
    if isinstance(ty, ListType):
        return is_json_serializable(ty.element)
    if isinstance(ty, ArrayType):
        return False
    if isinstance(ty, RefinementType):
        return ty.base is not None and is_json_serializable(ty.base)
    return False


# Store-backed lookup type names — populated by the checker at registration time.
# types_compatible uses this to treat these types as interchangeable with StoreTable.
STORE_BACKED_TYPES: set[str] = set()


def types_compatible(expected: Type, actual: Type) -> bool:
    """Check structural compatibility between two types.

    ErrorType and TypeVariable are compatible with anything to prevent
    cascading errors and allow generic params through without full inference.
    Refinement types are compatible with their base type.
    """
    if expected is actual:
        return True
    if isinstance(expected, ErrorType) or isinstance(actual, ErrorType):
        return True
    if isinstance(expected, TypeVariable) or isinstance(actual, TypeVariable):
        return True

    # Value is the heterogeneous base type for all serializable types
    if isinstance(expected, PrimitiveType) and expected.name == "Value":
        if is_json_serializable(actual):
            return True

    # Unwrap refinement types so Price (Decimal where ...) is
    # compatible with Decimal and with other Decimal refinements.
    # Allow Value → Option<Refinement(Value)>: when the Option's inner type is a
    # RefinementType whose base matches actual, the assignment is valid
    # (Option wraps the boundary-failure case).
    if isinstance(expected, GenericInstance) and expected.base_name == "Option" and expected.args:
        inner = expected.args[0]
        if isinstance(inner, RefinementType) and types_compatible(inner.base, actual):
            return True
    expected = _unwrap_refinement(expected)
    actual = _unwrap_refinement(actual)
    # EffectType is transparent for compatibility — unwrap to base
    if isinstance(expected, EffectType):
        return types_compatible(expected.base, actual)
    if isinstance(actual, EffectType):
        return types_compatible(expected, actual.base)
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
    # Store-backed lookup types are interchangeable with StoreTable
    if STORE_BACKED_TYPES:
        exp_name = getattr(expected, "name", "")
        act_name = getattr(actual, "name", "")
        if (exp_name == "StoreTable" and act_name in STORE_BACKED_TYPES) or (
            act_name == "StoreTable" and exp_name in STORE_BACKED_TYPES
        ):
            return True
    # Row polymorphism: StructType accepts any RecordType with matching fields
    if isinstance(expected, StructType):
        if isinstance(actual, RecordType):
            for fname, ftype in expected.required_fields.items():
                actual_ftype = actual.fields.get(fname)
                if actual_ftype is None or not types_compatible(ftype, actual_ftype):
                    return False
            return True
        if isinstance(actual, StructType):
            for fname, ftype in expected.required_fields.items():
                actual_ftype = actual.required_fields.get(fname)
                if actual_ftype is None or not types_compatible(ftype, actual_ftype):
                    return False
            return True
        return False
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
    if isinstance(expected, ArrayType) and isinstance(actual, ArrayType):
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
        if isinstance(sig, ArrayType) and isinstance(actual, ArrayType):
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
    if isinstance(ty, ArrayType):
        return ArrayType(substitute_type_vars(ty.element, bindings))
    if isinstance(ty, StructType) and ty.required_fields:
        new_fields = {
            n: substitute_type_vars(t, bindings)
            for n, t in ty.required_fields.items()
        }
        return StructType(new_fields)
    return ty


# ── Ownership helpers ─────────────────────────────────────────────


def has_own_modifier(ty: Type) -> bool:
    """Check if a type has the Own (linear) ownership modifier."""
    if isinstance(ty, PrimitiveType):
        return "Own" in ty.modifiers
    if isinstance(ty, ArrayType):
        return "Own" in ty.modifiers
    return False


def has_mutable_modifier(ty: Type) -> bool:
    """Check if a type has the Mutable modifier."""
    if isinstance(ty, PrimitiveType):
        return "Mutable" in ty.modifiers
    if isinstance(ty, ArrayType):
        return "Mutable" in ty.modifiers
    return False


def get_ownership_kind(ty: Type) -> str:
    """Return the ownership kind: 'owned', 'mutable', or 'shared'."""
    if isinstance(ty, PrimitiveType):
        if "Own" in ty.modifiers:
            return "owned"
        if "Mutable" in ty.modifiers:
            return "mutable"
    if isinstance(ty, ArrayType):
        if "Own" in ty.modifiers:
            return "owned"
        if "Mutable" in ty.modifiers:
            return "mutable"
    return "shared"
