"""Copy bundled C runtime files to a build directory.

Runtime Stripping
-----------------
The build system can strip unused runtime files to reduce binary size. It uses two
complementary approaches:

1. C code analysis: Extracts `prove_*` function calls from generated C using regex.
2. AST-level tracking: Scans ModuleDecl imports to identify stdlib modules used.

Files are matched against _RUNTIME_FUNCTIONS (C function → runtime lib mapping) to
determine which to copy. Core dependencies (arena, region, string, hash, intern,
list, option, result) are always included as they're required by other runtime
components and the base runtime.

Example:
    # Full copy (no stripping)
    copy_runtime(build_dir)

    # Strip based on C code analysis only
    copy_runtime(build_dir, c_sources=[c_code])

    # Strip with both C code analysis and stdlib tracking
    copy_runtime(build_dir, c_sources=[c_code], stdlib_libs={"prove_input_output"})
"""

from __future__ import annotations

import importlib.resources
import re
import shutil
from pathlib import Path


def _discover_runtime_files() -> list[str]:
    """Auto-discover prove_*.{c,h} files from the prove.runtime package."""
    pkg = importlib.resources.files("prove.runtime")
    files = []
    for item in pkg.iterdir():
        name = item.name
        if name.startswith("prove_") and name.endswith((".c", ".h")):
            files.append(name)
    return sorted(files)


_RUNTIME_FILES = _discover_runtime_files()

# Core runtime files that are always included (required by the runtime itself).
# Expanded to .h/.c pairs during stripping.
_CORE_FILES = {
    "prove_runtime",
    "prove_arena",
    "prove_region",
    "prove_string",
    "prove_hash",
    "prove_intern",
    "prove_list",
    "prove_option",
    "prove_result",
    "prove_text",
}

# Mapping of stdlib module names to the C runtime libraries they require.
# Used by RuntimeDeps (in optimizer.py) to track which runtime files to include.
# Keys are lowercase stdlib module names.
STDLIB_RUNTIME_LIBS: dict[str, set[str]] = {
    "io": {"prove_input_output"},
    "inputoutput": {"prove_input_output"},
    "character": {"prove_character"},
    "text": {"prove_text", "prove_string"},
    "table": {"prove_table", "prove_hash"},
    "parse": {"prove_parse"},
    "math": {"prove_math"},
    "types": {"prove_convert"},
    "convert": {"prove_convert"},
    "list": {"prove_list", "prove_list_ops"},
    "format": {"prove_format"},
    "path": {"prove_path"},
    "error": {"prove_error"},
    "pattern": {"prove_pattern"},
    "result": {"prove_result"},
    "option": {"prove_option"},
}

_RUNTIME_FUNCTIONS = {
    "prove_arena": [
        "prove_arena_alloc",
        "prove_arena_free",
        "prove_arena_gc",
        "prove_arena_new",
    ],
    "prove_region": [
        "prove_region_alloc",
        "prove_region_free",
        "prove_region_enter",
        "prove_region_exit",
    ],
    "prove_hash": [
        "prove_hash_create",
        "prove_hash_get",
        "prove_hash_set",
        "prove_hash_del",
        "prove_hash_iter",
    ],
    "prove_intern": [
        "prove_intern_get",
        "prove_intern_release",
        "prove_intern_table_new",
        "prove_intern_table_free",
    ],
    "prove_string": [
        "prove_string_from_cstr",
        "prove_string_concat",
        "prove_string_slice",
        "prove_string_eq",
        "prove_string_len",
    ],
    "prove_list": [
        "prove_list_create",
        "prove_list_push",
        "prove_list_pop",
        "prove_list_get",
        "prove_list_len",
    ],
    "prove_hof": ["prove_map", "prove_filter", "prove_reduce", "prove_any", "prove_all"],
    "prove_character": ["prove_character_from_int", "prove_character_to_int"],
    "prove_text": ["prove_text_from_string", "prove_text_to_string", "prove_text_len"],
    "prove_table": ["prove_table_create", "prove_table_get", "prove_table_set", "prove_table_del"],
    "prove_input_output": [
        "prove_print",
        "prove_println",
        "prove_readln",
        "prove_file_read",
        "prove_file_write",
    ],
    "prove_parse": ["prove_parse_toml", "prove_parse_json"],
    "prove_math": [
        "prove_math_abs",
        "prove_math_max",
        "prove_math_min",
        "prove_math_pow",
        "prove_math_sqrt",
    ],
    "prove_convert": [
        "prove_convert_integer_str",
        "prove_convert_integer_float",
        "prove_convert_float_str",
        "prove_convert_float_int",
        "prove_convert_string_int",
        "prove_convert_string_float",
        "prove_convert_string_bool",
        "prove_convert_code",
        "prove_convert_character",
    ],
    "prove_list_ops": [
        "prove_list_ops_length",
        "prove_list_ops_first_int",
        "prove_list_ops_first_str",
        "prove_list_ops_last_int",
        "prove_list_ops_last_str",
        "prove_list_ops_empty",
        "prove_list_ops_contains_int",
        "prove_list_ops_contains_str",
        "prove_list_ops_index_int",
        "prove_list_ops_index_str",
        "prove_list_ops_slice",
        "prove_list_ops_reverse",
        "prove_list_ops_sort_int",
        "prove_list_ops_sort_str",
        "prove_list_ops_range",
    ],
    "prove_format": ["prove_format_string", "prove_format_int", "prove_format_decimal"],
    "prove_path": [
        "prove_path_join",
        "prove_path_dirname",
        "prove_path_basename",
        "prove_path_exists",
    ],
    "prove_pattern": ["prove_pattern_match", "prove_pattern_replace", "prove_pattern_split"],
}


def _extract_function_calls(c_code: str) -> set[str]:
    """Extract all function calls from C code."""
    calls = set()
    func_call_pattern = r"\b([a-zA-Z_][a-zA-Z0-9_]*)\s*\("
    for match in re.finditer(func_call_pattern, c_code):
        func_name = match.group(1)
        if func_name.startswith("prove_") or func_name.startswith("_prove_"):
            calls.add(func_name)
    return calls


def copy_runtime(
    build_dir: Path,
    c_sources: list[str] | None = None,
    stdlib_libs: set[str] | None = None,
    *,
    strip_unused: bool = True,
) -> list[Path]:
    """Copy bundled runtime files to *build_dir*/runtime/.

    If *c_sources* is provided and *strip_unused* is True, only copies runtime
    files that contain functions used in the C sources.

    If *stdlib_libs* is provided, includes runtime files for those stdlib modules
    regardless of whether they're detected in C code (handles indirect dependencies).

    Returns the list of .c files (needed for compilation).
    """
    dest = build_dir / "runtime"
    dest.mkdir(parents=True, exist_ok=True)

    if not strip_unused or not c_sources:
        return _copy_all_runtime_files(dest)

    all_calls = set()
    for src in c_sources:
        all_calls.update(_extract_function_calls(src))

    needed_libs = set()
    for lib_name, funcs in _RUNTIME_FUNCTIONS.items():
        for func in funcs:
            if func in all_calls:
                needed_libs.add(lib_name)
                break

    if stdlib_libs:
        needed_libs.update(stdlib_libs)

    needed_files: set[str] = set()
    for lib_name in needed_libs:
        for name in _RUNTIME_FILES:
            if lib_name in name:
                needed_files.add(name)

    # Always include core runtime files.
    for base in _CORE_FILES:
        needed_files.add(f"{base}.h")
        needed_files.add(f"{base}.c")

    c_files: list[Path] = []
    pkg = importlib.resources.files("prove.runtime")
    for name in _RUNTIME_FILES:
        if name not in needed_files:
            continue
        src = pkg.joinpath(name)
        dst = dest / name
        with importlib.resources.as_file(src) as src_path:
            shutil.copy2(src_path, dst)
        if name.endswith(".c"):
            c_files.append(dst)

    return c_files


def _copy_all_runtime_files(dest: Path) -> list[Path]:
    """Copy all runtime files."""
    c_files: list[Path] = []
    pkg = importlib.resources.files("prove.runtime")
    for name in _RUNTIME_FILES:
        src = pkg.joinpath(name)
        dst = dest / name
        with importlib.resources.as_file(src) as src_path:
            shutil.copy2(src_path, dst)
        if name.endswith(".c"):
            c_files.append(dst)
    return c_files
