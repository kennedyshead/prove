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
    StructType,
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


def _map_integer(modifiers: tuple[tuple[str | None, str], ...]) -> CType:
    unsigned = any(v == "Unsigned" for (_, v) in modifiers)
    size = 64  # default
    for _, v in modifiers:
        if v.isdigit():
            size = int(v)
    key = (unsigned, size)
    c_type = _INT_SIZE_MAP.get(key, "int64_t")
    return CType(c_type, is_pointer=False, header=None)


def _map_float(modifiers: tuple[tuple[str | None, str], ...]) -> CType:
    for _, v in modifiers:
        if v == "32":
            return CType("float", is_pointer=False, header=None)
        if v == "128":
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
    "DirEntry": CType("Prove_DirEntry*", is_pointer=True, header="prove_input_output.h"),
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
    "Token": CType("Prove_Language_Token*", is_pointer=True, header="prove_language.h"),
    "Tree": CType("Prove_Tree", is_pointer=True, header="prove_prove.h"),
    "Node": CType("Prove_Node", is_pointer=True, header="prove_prove.h"),
    "Verb": CType("void*", is_pointer=True, header=None),
    "Attached": CType("Prove_CoroFn", is_pointer=False, header="prove_coro.h"),
    "Listens": CType("Prove_CoroFn", is_pointer=False, header="prove_coro.h"),
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
        if ty.base_name == "Value":
            if ty.args and isinstance(ty.args[0], PrimitiveType):
                phantom = ty.args[0].name
                if phantom == "Tree":
                    return CType("Prove_Tree", is_pointer=True, header=None)
                if phantom == "Csv":
                    return CType("Prove_List*", is_pointer=True, header="prove_list.h")
            return CType("Prove_Value*", is_pointer=True, header="prove_parse.h")
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

    if isinstance(ty, StructType):
        # StructType is erased by monomorphisation — should not reach here
        # in correct code.  Fallback to void* for safety.
        return CType("void*", is_pointer=True, header=None)

    if isinstance(ty, VariantInfo):
        return CType("int64_t", is_pointer=False, header=None)

    if isinstance(ty, ErrorType):
        return CType("int64_t", is_pointer=False, header=None)

    return CType("int64_t", is_pointer=False, header=None)


# C/C23 reserved words that cannot be used as identifiers in generated code.
_C_KEYWORDS = frozenset(
    {
        "auto",
        "break",
        "case",
        "char",
        "const",
        "continue",
        "default",
        "do",
        "double",
        "else",
        "enum",
        "extern",
        "float",
        "for",
        "goto",
        "if",
        "inline",
        "int",
        "long",
        "register",
        "restrict",
        "return",
        "short",
        "signed",
        "sizeof",
        "static",
        "struct",
        "switch",
        "typedef",
        "union",
        "unsigned",
        "void",
        "volatile",
        "while",
        "_Bool",
        "_Complex",
        "_Imaginary",
        "_Alignas",
        "_Alignof",
        "_Atomic",
        "_Generic",
        "_Noreturn",
        "_Static_assert",
        "_Thread_local",
    }
)


def safe_c_name(name: str) -> str:
    """Escape a Prove identifier that collides with a C keyword."""
    if name in _C_KEYWORDS:
        return f"_{name}"
    return name


def mangle_name(
    verb: str | None,
    name: str,
    param_types: list[Type] | None = None,
    *,
    module: str | None = None,
) -> str:
    """Mangle a function name for C with ``prv_`` prefix.

    e.g. ("transforms", "add", [Integer, Integer]) -> "prv_transforms_add_Integer_Integer"

    When *module* is given the module name is included after ``prv_`` to
    disambiguate functions with the same verb/name/params in different
    modules (e.g. ``prv_compiler_matches_unwrap_Option``).

    The prefix prevents collisions with C standard library and system
    functions (e.g. ``file``, ``read``, ``close``).
    """
    parts: list[str] = ["prv"]
    if module:
        parts.append(module)
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
    if isinstance(ty, StructType):
        return "Struct"
    return "unknown"
