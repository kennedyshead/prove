"""Verify _RUNTIME_FUNCTIONS in c_runtime.py stays in sync with C headers."""

from __future__ import annotations

import importlib.resources
import re

from prove.c_runtime import _RUNTIME_FUNCTIONS


def _parse_header_functions(header_text: str, *, include_static_inline: bool = False) -> set[str]:
    """Extract prove_* function declarations from a C header.

    When include_static_inline is False (default), only matches public
    (non-static) declarations — used to check that public API functions
    are registered.

    When include_static_inline is True, also matches static inline wrappers
    — used to verify that registered functions actually exist in headers.
    """
    funcs: set[str] = set()
    decl_pat = re.compile(
        r"^[A-Za-z_][\w\s*]*?"  # return type
        r"\b(prove_\w+)\s*\(",  # function name + opening paren
    )
    static_inline_pat = re.compile(
        r"^static\s+inline\s+[A-Za-z_][\w\s*]*?"
        r"\b(prove_\w+)\s*\(",
    )
    for line in header_text.splitlines():
        stripped = line.strip()
        # Skip lines that are clearly not declarations
        if stripped.startswith(("//", "/*", "*", "#", "}", "if ", "return ")):
            continue
        # Check static inline first
        if stripped.startswith("static"):
            if include_static_inline and "inline" in stripped.split("(")[0]:
                m = static_inline_pat.match(stripped)
                if m:
                    funcs.add(m.group(1))
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
    for lib, reg_fns in _RUNTIME_FUNCTIONS.items():
        for fn in reg_fns:
            registered[fn] = lib

    all_header_funcs: dict[str, set[str]] = {}  # header_basename -> functions

    for item in sorted(pkg.iterdir(), key=lambda p: p.name):
        if not item.name.endswith(".h"):
            continue
        basename = item.name.removesuffix(".h")
        with importlib.resources.as_file(item) as path:
            text = path.read_text()
        hdr_fns = _parse_header_functions(text)
        if hdr_fns:
            all_header_funcs[basename] = hdr_fns

    missing: list[str] = []
    for header, hdr_fns in sorted(all_header_funcs.items()):
        for fn in sorted(hdr_fns):
            if fn not in registered:
                missing.append(f"  {header}: {fn}")

    if missing:
        msg = "Functions in headers but missing from _RUNTIME_FUNCTIONS:\n"
        msg += "\n".join(missing)
        raise AssertionError(msg)


def test_no_stale_entries() -> None:
    """Every function in _RUNTIME_FUNCTIONS must exist in the corresponding .h file."""
    pkg = importlib.resources.files("prove.runtime")

    # Parse all header functions (including static inline wrappers)
    all_funcs: set[str] = set()
    for item in pkg.iterdir():
        if not item.name.endswith(".h"):
            continue
        with importlib.resources.as_file(item) as path:
            text = path.read_text()
        all_funcs.update(_parse_header_functions(text, include_static_inline=True))

    stale: list[str] = []
    for lib, funcs in sorted(_RUNTIME_FUNCTIONS.items()):
        for fn in sorted(funcs):
            if fn not in all_funcs:
                stale.append(f"  {lib}: {fn}")

    if stale:
        msg = "Functions in _RUNTIME_FUNCTIONS but missing from headers:\n"
        msg += "\n".join(stale)
        raise AssertionError(msg)
