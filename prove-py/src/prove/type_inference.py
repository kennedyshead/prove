"""Shared type inference constants.

Constants shared between the C emitter, formatter, and testing modules
to avoid duplication of binary operator mappings and utility functions.
"""

from __future__ import annotations

from prove.types import ArrayType, GenericInstance, ListType, Type

# Binary operator → C operator identity mapping.
# Used by c_emitter._emit_binary and testing._expr_to_c_inner.
BINARY_OP_TO_C: dict[str, str] = {
    "+": "+",
    "-": "-",
    "*": "*",
    "/": "/",
    "%": "%",
    "==": "==",
    "!=": "!=",
    "<": "<",
    ">": ">",
    "<=": "<=",
    ">=": ">=",
    "&&": "&&",
    "||": "||",
}

# Built-in functions that map directly to runtime calls.
# Used by _emit_calls and _emit_exprs mixins.
BUILTIN_MAP: dict[str, str] = {
    "clamp": "prove_clamp",
}


def get_type_key(ty: Type | None) -> str | None:
    """Get a type key string for overload dispatch.

    For generic types (ListType, GenericInstance), produces richer keys
    like "List<Integer>" instead of just "List".
    """
    if ty is None:
        return None
    if isinstance(ty, ListType):
        inner = getattr(ty.element, "name", "T")
        return f"List<{inner}>"
    if isinstance(ty, ArrayType):
        inner = getattr(ty.element, "name", "T")
        key = f"Array<{inner}>"
        if ty.modifiers:
            return f"{key}:{','.join(v for _, v in ty.modifiers)}"
        return key
    if isinstance(ty, GenericInstance):
        args = ",".join(getattr(a, "name", "T") for a in ty.args)
        return f"{ty.base_name}<{args}>"
    return getattr(ty, "name", None)
