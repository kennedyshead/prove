"""Prove Type -> C type mapping and name mangling."""

from __future__ import annotations

from dataclasses import dataclass

from prove.types import (
    AlgebraicType,
    ErrorType,
    FunctionType,
    GenericInstance,
    ListType,
    PrimitiveType,
    RecordType,
    RefinementType,
    Type,
    TypeVariable,
    UnitType,
    VariantInfo,
)


@dataclass(frozen=True)
class CType:
    """A C type representation."""

    decl: str  # C type string, e.g. "int64_t", "Prove_String*"
    is_pointer: bool  # needs retain/release
    header: str | None  # runtime header needed, e.g. "prove_string.h"


# ── Integer modifier mapping ──────────────────────────────────────

_INT_SIZE_MAP: dict[tuple[bool, int], str] = {
    (False, 8): "int8_t",
    (False, 16): "int16_t",
    (False, 32): "int32_t",
    (False, 64): "int64_t",
    (True, 8): "uint8_t",
    (True, 16): "uint16_t",
    (True, 32): "uint32_t",
    (True, 64): "uint64_t",
}


def _map_integer(modifiers: tuple[str, ...]) -> CType:
    unsigned = "Unsigned" in modifiers
    size = 64  # default
    for m in modifiers:
        if m.isdigit():
            size = int(m)
    key = (unsigned, size)
    c_type = _INT_SIZE_MAP.get(key, "int64_t")
    return CType(c_type, is_pointer=False, header=None)


def _map_float(modifiers: tuple[str, ...]) -> CType:
    for m in modifiers:
        if m == "32":
            return CType("float", is_pointer=False, header=None)
    return CType("double", is_pointer=False, header=None)


# ── Public API ─────────────────────────────────────────────────────


def map_type(ty: Type) -> CType:
    """Map a Prove resolved Type to its C representation."""
    if isinstance(ty, PrimitiveType):
        name = ty.name
        if name == "Integer":
            return _map_integer(ty.modifiers)
        if name in ("Decimal", "Float"):
            return _map_float(ty.modifiers)
        if name == "Boolean":
            return CType("bool", is_pointer=False, header=None)
        if name == "Character":
            return CType("char", is_pointer=False, header=None)
        if name == "Byte":
            return CType("uint8_t", is_pointer=False, header=None)
        if name == "String":
            return CType("Prove_String*", is_pointer=True, header="prove_string.h")
        if name == "Error":
            return CType("Prove_String*", is_pointer=True, header="prove_string.h")
        if name == "Builder":
            return CType("Prove_Builder*", is_pointer=True, header="prove_text.h")
        if name == "ProcessResult":
            return CType(
                "Prove_ProcessResult", is_pointer=False,
                header="prove_input_output.h",
            )
        if name == "DirEntry":
            return CType(
                "Prove_DirEntry", is_pointer=False,
                header="prove_input_output.h",
            )
        if name == "ExitCode":
            return CType("int64_t", is_pointer=False, header=None)
        if name == "Value":
            return CType("Prove_Value*", is_pointer=True, header="prove_parse.h")
        # Fallback for unknown primitives
        return CType("int64_t", is_pointer=False, header=None)

    if isinstance(ty, UnitType):
        return CType("void", is_pointer=False, header=None)

    if isinstance(ty, RecordType):
        return CType(mangle_type_name(ty.name), is_pointer=False, header=None)

    if isinstance(ty, AlgebraicType):
        return CType(mangle_type_name(ty.name), is_pointer=False, header=None)

    if isinstance(ty, RefinementType):
        return map_type(ty.base) if ty.base else CType("int64_t", is_pointer=False, header=None)

    if isinstance(ty, ListType):
        return CType("Prove_List*", is_pointer=True, header="prove_list.h")

    if isinstance(ty, GenericInstance):
        if ty.base_name == "Result":
            return CType("Prove_Result", is_pointer=False, header="prove_result.h")
        if ty.base_name == "Table":
            return CType("Prove_Table*", is_pointer=True, header="prove_table.h")
        if ty.base_name == "Option":
            # Monomorphize: Option<Integer> -> Prove_Option_int64_t
            if ty.args:
                inner = map_type(ty.args[0])
                safe = inner.decl.replace("*", "ptr").replace(" ", "_")
                return CType(f"Prove_Option_{safe}", is_pointer=False, header="prove_option.h")
            return CType("Prove_Option_int64_t", is_pointer=False, header="prove_option.h")
        return CType(mangle_type_name(ty.base_name), is_pointer=False, header=None)

    if isinstance(ty, FunctionType):
        # Function pointers are not directly emitted as types in POC
        return CType("void*", is_pointer=True, header=None)

    if isinstance(ty, TypeVariable):
        # Generic — fallback to void* in POC
        return CType("void*", is_pointer=True, header=None)

    if isinstance(ty, VariantInfo):
        return CType("int64_t", is_pointer=False, header=None)

    if isinstance(ty, ErrorType):
        return CType("int64_t", is_pointer=False, header=None)

    return CType("int64_t", is_pointer=False, header=None)


def mangle_name(verb: str | None, name: str, param_types: list[Type] | None = None) -> str:
    """Mangle a function name for C with ``prv_`` prefix.

    e.g. ("transforms", "add", [Integer, Integer]) -> "prv_transforms_add_Integer_Integer"

    The prefix prevents collisions with C standard library and system
    functions (e.g. ``file``, ``read``, ``close``).
    """
    parts: list[str] = ["prv"]
    if verb:
        parts.append(verb)
    parts.append(name)
    if param_types:
        for pt in param_types:
            parts.append(_type_tag(pt))
    return "_".join(parts)


def mangle_type_name(name: str) -> str:
    """Mangle a type name for C. e.g. "Point" -> "Prove_Point"."""
    return f"Prove_{name}"


def _type_tag(ty: Type) -> str:
    """Short tag for a type, used in name mangling."""
    if isinstance(ty, PrimitiveType):
        return ty.name
    if isinstance(ty, RecordType):
        return ty.name
    if isinstance(ty, AlgebraicType):
        return ty.name
    if isinstance(ty, ListType):
        return "List"
    if isinstance(ty, GenericInstance):
        return ty.base_name
    if isinstance(ty, UnitType):
        return "Unit"
    if isinstance(ty, TypeVariable):
        return ty.name
    return "unknown"
