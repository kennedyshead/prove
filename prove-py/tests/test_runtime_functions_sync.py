"""Verify _RUNTIME_FUNCTIONS in c_runtime.py stays in sync with C headers."""

from __future__ import annotations

import importlib.resources
import re

from prove.c_runtime import _RUNTIME_FUNCTIONS


def _parse_header_functions(header_text: str) -> set[str]:
    """Extract non-static prove_* function declarations from a C header.

    Only matches lines that look like function declarations (return type
    followed by function name and opening paren), not function calls
    inside macro bodies or inline functions.
    """
    funcs: set[str] = set()
    # Match function declarations at the start of a line:
    # return_type prove_xxx(  — possibly with qualifiers like const, _Noreturn
    decl_pat = re.compile(
        r"^(?!static\b)"  # not static
        r"[A-Za-z_][\w\s*]*?"  # return type (e.g. "ProveString*", "int", "void")
        r"\b(prove_\w+)\s*\(",  # function name + opening paren
    )
    for line in header_text.splitlines():
        stripped = line.strip()
        # Skip lines that are clearly not declarations
        if stripped.startswith(("//", "/*", "*", "#", "}", "if ", "return ")):
            continue
        m = decl_pat.match(stripped)
        if m:
            funcs.add(m.group(1))
    return funcs


def test_runtime_functions_match_headers() -> None:
    """Every non-static prove_* function in a .h file must appear in _RUNTIME_FUNCTIONS."""
    pkg = importlib.resources.files("prove.runtime")

    # Build reverse map: function -> library
    registered: dict[str, str] = {}
    for lib, funcs in _RUNTIME_FUNCTIONS.items():
        for fn in funcs:
            registered[fn] = lib

    all_header_funcs: dict[str, set[str]] = {}  # header_basename -> functions

    for item in sorted(pkg.iterdir(), key=lambda p: p.name):
        if not item.name.endswith(".h"):
            continue
        basename = item.name.removesuffix(".h")
        with importlib.resources.as_file(item) as path:
            text = path.read_text()
        funcs = _parse_header_functions(text)
        if funcs:
            all_header_funcs[basename] = funcs

    missing: list[str] = []
    for header, funcs in sorted(all_header_funcs.items()):
        for fn in sorted(funcs):
            if fn not in registered:
                missing.append(f"  {header}: {fn}")

    if missing:
        msg = "Functions in headers but missing from _RUNTIME_FUNCTIONS:\n"
        msg += "\n".join(missing)
        raise AssertionError(msg)


def test_no_stale_entries() -> None:
    """Every function in _RUNTIME_FUNCTIONS must exist in the corresponding .h file."""
    pkg = importlib.resources.files("prove.runtime")

    # Parse all header functions
    all_funcs: set[str] = set()
    for item in pkg.iterdir():
        if not item.name.endswith(".h"):
            continue
        with importlib.resources.as_file(item) as path:
            text = path.read_text()
        all_funcs.update(_parse_header_functions(text))

    stale: list[str] = []
    for lib, funcs in sorted(_RUNTIME_FUNCTIONS.items()):
        for fn in sorted(funcs):
            if fn not in all_funcs:
                stale.append(f"  {lib}: {fn}")

    if stale:
        msg = "Functions in _RUNTIME_FUNCTIONS but missing from headers:\n"
        msg += "\n".join(stale)
        raise AssertionError(msg)
