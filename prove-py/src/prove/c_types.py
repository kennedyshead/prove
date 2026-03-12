"""Prove Type -> C type mapping and name mangling."""

from __future__ import annotations

from dataclasses import dataclass

from prove.types import (
    AlgebraicType,
    ArrayType,
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
        if m == "128":
            return CType("long double", is_pointer=False, header=None)
    return CType("double", is_pointer=False, header=None)


# ── Primitive name → CType lookup ──────────────────────────────────

_PRIMITIVE_MAP: dict[str, CType] = {
    "Boolean": CType("bool", is_pointer=False, header=None),
    "Character": CType("char", is_pointer=False, header=None),
    "Byte": CType("uint8_t", is_pointer=False, header=None),
    "String": CType("Prove_String*", is_pointer=True, header="prove_string.h"),
    "Error": CType("Prove_String*", is_pointer=True, header="prove_string.h"),
    "StringBuilder": CType("Prove_Builder*", is_pointer=True, header="prove_text.h"),
    "ProcessResult": CType("Prove_ProcessResult", is_pointer=False, header="prove_input_output.h"),
    "DirEntry": CType("Prove_DirEntry", is_pointer=False, header="prove_input_output.h"),
    "ExitCode": CType("int64_t", is_pointer=False, header=None),
    "Value": CType("Prove_Value*", is_pointer=True, header="prove_parse.h"),
    "Match": CType("Prove_Match*", is_pointer=True, header="prove_pattern.h"),
    "Time": CType("Prove_Time*", is_pointer=True, header="prove_time.h"),
    "Duration": CType("Prove_Duration*", is_pointer=True, header="prove_time.h"),
    "Date": CType("Prove_Date*", is_pointer=True, header="prove_time.h"),
    "Clock": CType("Prove_Clock*", is_pointer=True, header="prove_time.h"),
    "DateTime": CType("Prove_DateTime*", is_pointer=True, header="prove_time.h"),
    "Weekday": CType("int64_t", is_pointer=False, header="prove_time.h"),
    "ByteArray": CType("Prove_ByteArray*", is_pointer=True, header="prove_bytes.h"),
    "Url": CType("Prove_Url*", is_pointer=True, header="prove_parse.h"),
    "Socket": CType("Prove_Socket*", is_pointer=True, header="prove_network.h"),
    "File": CType("Prove_File*", is_pointer=True, header="prove_input_output.h"),
    "Store": CType("Prove_Store*", is_pointer=True, header="prove_store.h"),
    "StoreTable": CType("Prove_StoreTable*", is_pointer=True, header="prove_store.h"),
    "TableDiff": CType("Prove_TableDiff*", is_pointer=True, header="prove_store.h"),
    "Version": CType("Prove_Version*", is_pointer=True, header="prove_store.h"),
    "Conflict": CType("Prove_Conflict*", is_pointer=True, header="prove_store.h"),
    "Resolution": CType("Prove_Resolution*", is_pointer=True, header="prove_store.h"),
    "MergeResult": CType("Prove_MergeResult*", is_pointer=True, header="prove_store.h"),
    "Verb": CType("void*", is_pointer=True, header=None),
}

# ── Public API ─────────────────────────────────────────────────────


def map_type(ty: Type) -> CType:
    """Map a Prove resolved Type to its C representation."""
    # Unwrap borrowed types - they're passed as regular pointers in C
    from prove.types import BorrowType

    if isinstance(ty, BorrowType):
        ty = ty.inner

    if isinstance(ty, PrimitiveType):
        name = ty.name
        if name == "Integer":
            return _map_integer(ty.modifiers)
        if name in ("Decimal", "Float"):
            return _map_float(ty.modifiers)
        mapped = _PRIMITIVE_MAP.get(name)
        if mapped is not None:
            return mapped
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

    if isinstance(ty, ArrayType):
        return CType("Prove_Array*", is_pointer=True, header="prove_array.h")

    if isinstance(ty, GenericInstance):
        if ty.base_name == "Result":
            return CType("Prove_Result", is_pointer=False, header="prove_result.h")
        if ty.base_name == "Table":
            return CType("Prove_Table*", is_pointer=True, header="prove_table.h")
        if ty.base_name == "Option":
            return CType("Prove_Option", is_pointer=False, header="prove_option.h")
        return CType(mangle_type_name(ty.base_name), is_pointer=False, header=None)

    if isinstance(ty, FunctionType):
        ret_ct = map_type(ty.return_type) if ty.return_type else CType("void", False, None)
        param_cts = [map_type(pt) for pt in ty.param_types]
        param_str = ", ".join(ct.decl for ct in param_cts) if param_cts else "void"
        headers = {ct.header for ct in [ret_ct] + param_cts if ct.header}
        header = next(iter(headers)) if len(headers) == 1 else None
        return CType(f"{ret_ct.decl} (*)({param_str})", is_pointer=True, header=header)

    if isinstance(ty, TypeVariable):
        if ty.name == "Value":
            return CType("Prove_Value*", is_pointer=True, header="prove_parse.h")
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
    if isinstance(ty, ArrayType):
        return "Array"
    if isinstance(ty, GenericInstance):
        return ty.base_name
    if isinstance(ty, UnitType):
        return "Unit"
    if isinstance(ty, TypeVariable):
        return ty.name
    return "unknown"
