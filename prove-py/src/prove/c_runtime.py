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

_RUNTIME_FILES = [
    "prove_runtime.h",
    "prove_runtime.c",
    "prove_arena.h",
    "prove_arena.c",
    "prove_region.h",
    "prove_region.c",
    "prove_hash.h",
    "prove_hash.c",
    "prove_intern.h",
    "prove_intern.c",
    "prove_string.h",
    "prove_string.c",
    "prove_list.h",
    "prove_list.c",
    "prove_hof.h",
    "prove_hof.c",
    "prove_option.h",
    "prove_result.h",
    "prove_character.h",
    "prove_character.c",
    "prove_text.h",
    "prove_text.c",
    "prove_table.h",
    "prove_table.c",
    "prove_input_output.h",
    "prove_input_output.c",
    "prove_parse.h",
    "prove_parse_toml.c",
    "prove_parse_json.c",
    "prove_math.h",
    "prove_math.c",
    "prove_convert.h",
    "prove_convert.c",
    "prove_list_ops.h",
    "prove_list_ops.c",
    "prove_format.h",
    "prove_format.c",
    "prove_path.h",
    "prove_path.c",
    "prove_error.h",
    "prove_pattern.h",
    "prove_pattern.c",
]

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

    needed_files = set()
    for lib_name in needed_libs:
        for name in _RUNTIME_FILES:
            if lib_name in name:
                needed_files.add(name)

    needed_files.add("prove_runtime.h")
    needed_files.add("prove_runtime.c")
    needed_files.add("prove_arena.h")
    needed_files.add("prove_arena.c")
    needed_files.add("prove_region.h")
    needed_files.add("prove_region.c")
    needed_files.add("prove_string.h")
    needed_files.add("prove_string.c")
    needed_files.add("prove_hash.h")
    needed_files.add("prove_hash.c")
    needed_files.add("prove_intern.h")
    needed_files.add("prove_intern.c")
    needed_files.add("prove_list.h")
    needed_files.add("prove_list.c")
    needed_files.add("prove_option.h")
    needed_files.add("prove_result.h")
    needed_files.add("prove_text.h")
    needed_files.add("prove_text.c")

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
