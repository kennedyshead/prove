"""Shared cast/box helpers for the C emitter mixins."""

from __future__ import annotations

from typing import TYPE_CHECKING

from prove.c_types import CType

if TYPE_CHECKING:
    from prove.types import Type

# Shared type-name → prove_string_from_* dispatch table.
TYPE_TO_STRING_FUNC: dict[str, str] = {
    "Integer": "prove_string_from_int",
    "Float": "prove_string_from_double",
    "Decimal": "prove_string_from_double",
    "Boolean": "prove_string_from_bool",
    "Character": "prove_string_from_char",
    "Value": "prove_value_as_text",
    "Time": "prove_time_string_time",
    "Date": "prove_time_string_date",
    "DateTime": "prove_time_string_datetime",
    "Clock": "prove_time_string_clock",
    "Duration": "prove_time_string_duration",
}


def to_string_func(ty: Type) -> str:
    """Pick the right prove_string_from_* function for a Prove type."""
    from prove.types import PrimitiveType

    if isinstance(ty, PrimitiveType):
        if ty.name == "String":
            return ""  # identity
        result = TYPE_TO_STRING_FUNC.get(ty.name)
        if result:
            return result
    return "prove_string_from_int"  # fallback


def hof_box(expr: str, ct: CType) -> str:
    """Box a typed value into void* for HOF callbacks and list storage."""
    if ct.is_pointer:
        return f"(void*){expr}"
    if ct.decl in ("double", "float"):
        return f"_prove_f64_box({expr})"
    if ct.decl.startswith("Prove_"):
        return f"({{{ct.decl} *_bx = malloc(sizeof({ct.decl})); *_bx = {expr}; (void*)_bx;}})"
    return f"(void*)(intptr_t){expr}"


def hof_unbox(expr: str, ct: CType) -> str:
    """Unbox a void* into a typed value."""
    if ct.is_pointer:
        return f"({ct.decl}){expr}"
    if ct.decl in ("double", "float"):
        return f"_prove_f64_unbox({expr})"
    if ct.decl.startswith("Prove_"):
        return f"(*({ct.decl}*){expr})"
    return f"({ct.decl})(intptr_t){expr}"


def option_unwrap_value(value_expr: str, inner_ct: CType) -> str:
    """Cast an Option/Result .value field to its inner type.

    Unlike hof_unbox, this adds a (void*) intermediate cast for struct types
    since .value is Prove_Value*, not void*.
    """
    if inner_ct.is_pointer:
        return f"({inner_ct.decl}){value_expr}"
    if inner_ct.decl.startswith("Prove_"):
        return f"*({inner_ct.decl}*)(void*){value_expr}"
    return f"({inner_ct.decl})(intptr_t){value_expr}"
