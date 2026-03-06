"""Shared type inference constants.

Constants shared between the C emitter, formatter, and testing modules
to avoid duplication of binary operator mappings.
"""

from __future__ import annotations

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
