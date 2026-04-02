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
    "prove_bitarray",
}

# Field declarations for binary (C-backed) stdlib types.
# Maps type name → {field_name: prove_type_name}.
# Used by the checker to validate field access on opaque binary types.
BINARY_TYPE_FIELDS: dict[str, dict[str, str]] = {
    "ProcessResult": {
        "exit_code": "Integer",
        "standard_output": "String",
        "standard_error": "String",
    },
    "DirEntry": {
        "name": "String",
        "path": "String",
    },
    "Match": {
        "start": "Integer",
        "end": "Integer",
        "text": "String",
    },
    "Url": {
        "scheme": "String",
        "host": "String",
        "port": "Integer",
        "path": "String",
        "query": "String",
        "fragment": "String",
    },
    "Token": {
        "text": "String",
        "start": "Integer",
        "end": "Integer",
        "kind": "Integer",
    },
    "Rule": {
        "pattern": "String",
        "kind": "Integer",
    },
    "Version": {
        "number": "Integer",
        "timestamp": "Integer",
        "hash": "String",
    },
}

# Mapping of stdlib module names to the C runtime libraries they require.
# Used by RuntimeDeps (in optimizer.py) to track which runtime files to include.
# Keys are lowercase stdlib module names.
STDLIB_RUNTIME_LIBS: dict[str, set[str]] = {
    "system": {"prove_input_output"},
    "io": {"prove_input_output"},
    "inputoutput": {"prove_input_output"},
    "character": {"prove_character"},
    "text": {"prove_text", "prove_string"},
    "table": {"prove_table", "prove_hash"},
    "parse": {
        "prove_parse",
        "prove_parse_url",
        "prove_parse_csv",
        "prove_table",
        "prove_hash",
        "prove_bytes",
        "prove_time",
        "prove_format",
    },
    "math": {"prove_math"},
    "types": {
        "prove_convert",
        "prove_parse",
        "prove_table",
        "prove_hash",
        "prove_error",
        "prove_bytes",
    },
    "convert": {"prove_convert"},
    "list": {"prove_list", "prove_list_ops"},
    "sequence": {"prove_list", "prove_list_ops"},
    "array": {"prove_array"},
    "format": {"prove_format", "prove_time"},
    "path": {"prove_path"},
    "pattern": {"prove_pattern"},
    "result": {"prove_result"},
    "option": {"prove_option"},
    "random": {"prove_random"},
    "bytes": {"prove_bytes"},
    "hash": {"prove_hash_crypto", "prove_bytes"},
    "time": {"prove_time"},
    "log": {"prove_terminal", "prove_ansi", "prove_event"},
    "store": {
        "prove_store",
        "prove_hash_crypto",
        "prove_bytes",
        "prove_input_output",
        "prove_path",
    },
    "network": {"prove_network", "prove_bytes"},
    "language": {"prove_language", "prove_parse"},
    "ui": set(),
    "terminal": {"prove_terminal", "prove_ansi", "prove_event"},
    "graphic": {"prove_gui"},
    "prove": {"prove_prove"},
}

_RUNTIME_FUNCTIONS = {
    "prove_runtime": [
        "prove_runtime_init",
        "prove_runtime_cleanup",
        "prove_global_region",
    ],
    "prove_coro": [
        "prove_coro_new",
        "prove_coro_start",
        "prove_coro_resume",
        "prove_coro_yield",
        "prove_coro_cancel",
        "prove_coro_done",
        "prove_coro_cancelled",
        "prove_coro_free",
    ],
    "prove_event": [
        "prove_event_queue_new",
        "prove_event_queue_send",
        "prove_event_queue_recv",
        "prove_event_queue_close",
        "prove_event_queue_free",
    ],
    "prove_arena": [
        "prove_arena_new",
        "prove_arena_alloc",
        "prove_arena_reset",
        "prove_arena_free",
    ],
    "prove_region": [
        "prove_region_new",
        "prove_region_alloc",
        "prove_region_enter",
        "prove_region_exit",
        "prove_region_free",
    ],
    "prove_hash": [
        "prove_hash",
    ],
    "prove_intern": [
        "prove_intern_table_new",
        "prove_intern",
        "prove_intern_table_free",
    ],
    "prove_string": [
        "prove_string_new",
        "prove_string_new_region",
        "prove_string_from_cstr",
        "prove_string_from_cstr_region",
        "prove_string_concat",
        "prove_string_eq",
        "prove_string_len",
        "prove_string_from_int",
        "prove_string_from_double",
        "prove_string_from_bool",
        "prove_string_from_char",
        "prove_println",
        "prove_print",
        "prove_readln",
    ],
    "prove_list": [
        "prove_list_new",
        "prove_list_new_region",
        "prove_list_push",
        "prove_list_get",
        "prove_list_len",
        "prove_list_free",
    ],
    "prove_hof": [
        "prove_list_map",
        "prove_list_filter",
        "prove_list_all",
        "prove_list_any",
        "prove_list_each",
        "prove_list_reduce",
    ],
    "prove_character": [
        "prove_character_alpha",
        "prove_character_digit",
        "prove_character_alnum",
        "prove_character_upper",
        "prove_character_lower",
        "prove_character_space",
        "prove_character_at",
    ],
    "prove_text": [
        "prove_text_length",
        "prove_text_slice",
        "prove_text_starts_with",
        "prove_text_ends_with",
        "prove_text_contains",
        "prove_text_index_of",
        "prove_text_split",
        "prove_text_join",
        "prove_text_trim",
        "prove_text_to_lower",
        "prove_text_to_upper",
        "prove_text_replace",
        "prove_text_repeat",
        "prove_text_builder",
        "prove_text_write",
        "prove_text_write_char",
        "prove_text_write_cstr",
        "prove_text_write_bytes",
        "prove_text_build",
        "prove_text_builder_length",
    ],
    "prove_table": [
        "prove_table_new",
        "prove_table_has",
        "prove_table_add",
        "prove_table_get",
        "prove_table_remove",
        "prove_table_keys",
        "prove_table_values",
        "prove_table_length",
    ],
    "prove_input_output": [
        "prove_file_read",
        "prove_file_write",
        "prove_io_console_validates",
        "prove_readexactly",
        "prove_io_file_validates",
        "prove_io_system_inputs",
        "prove_io_system_outputs",
        "prove_io_system_validates",
        "prove_io_dir_inputs",
        "prove_io_dir_outputs",
        "prove_io_dir_validates",
        "prove_io_init_args",
        "prove_io_process_inputs",
        "prove_io_process_validates",
        "prove_file_open_read",
        "prove_file_readline_handle",
        "prove_file_close_handle",
        "prove_file_open_append",
        "prove_file_writeln_handle",
        "prove_io_process_cwd",
    ],
    "prove_parse": [
        "prove_value_null",
        "prove_value_text",
        "prove_value_number",
        "prove_value_decimal",
        "prove_value_bool",
        "prove_value_array",
        "prove_value_object",
        "prove_value_tag",
        "prove_value_as_text",
        "prove_value_as_number",
        "prove_value_as_decimal",
        "prove_value_as_bool",
        "prove_value_as_array",
        "prove_value_as_object",
        "prove_value_is_text",
        "prove_value_is_number",
        "prove_value_is_decimal",
        "prove_value_is_boolean",
        "prove_value_is_array",
        "prove_value_is_object",
        "prove_value_is_unit",
        "prove_parse_toml",
        "prove_emit_toml",
        "prove_parse_json",
        "prove_emit_json",
        "prove_validates_json",
        "prove_validates_toml",
        "prove_tag_json",
        "prove_tag_toml",
        "prove_creates_value",
        "prove_validates_value",
        "prove_parse_arguments",
        "prove_parse_rule",
        "prove_parse_tokens",
        "prove_parse_token_text",
        "prove_parse_token_start",
        "prove_parse_token_end",
        "prove_parse_token_kind",
    ],
    "prove_parse_csv": [
        "prove_parse_csv",
        "prove_emit_csv",
        "prove_csv_as_list",
        "prove_validates_csv",
    ],
    "prove_parse_url": [
        "prove_parse_url",
        "prove_parse_url_create",
        "prove_parse_url_validates",
        "prove_parse_url_transform",
        "prove_parse_url_host_reads",
        "prove_parse_url_port_reads",
        "prove_parse_base64_decode",
        "prove_parse_base64_encode",
        "prove_parse_base64_validates",
    ],
    "prove_math": [
        "prove_math_abs_int",
        "prove_math_abs_float",
        "prove_math_min_int",
        "prove_math_min_float",
        "prove_math_max_int",
        "prove_math_max_float",
        "prove_math_clamp_int",
        "prove_math_clamp_float",
        "prove_math_sqrt",
        "prove_math_pow",
        "prove_math_floor",
        "prove_math_ceil",
        "prove_math_round",
        "prove_math_log",
        "prove_math_log10",
        "prove_math_sin",
        "prove_math_cos",
        "prove_math_tan",
        "prove_math_asin",
        "prove_math_acos",
        "prove_math_atan",
        "prove_math_atan2",
        "prove_math_exp",
        "prove_math_log2",
        "prove_math_pi",
        "prove_math_e",
    ],
    "prove_convert": [
        "prove_convert_integer_str",
        "prove_convert_integer_float",
        "prove_convert_integer_decimal",
        "prove_convert_float_str",
        "prove_convert_float_int",
        "prove_convert_float_decimal",
        "prove_convert_decimal_str",
        "prove_convert_decimal_int",
        "prove_convert_string_int",
        "prove_convert_string_float",
        "prove_convert_string_bool",
        "prove_convert_string_byte",
        "prove_convert_integer_bool",
        "prove_convert_boolean_int",
        "prove_convert_boolean_str",
        "prove_convert_code",
        "prove_convert_character",
        "prove_convert_string_position",
    ],
    "prove_list_ops": [
        "prove_list_ops_length",
        "prove_list_ops_first",
        "prove_list_ops_first_int",
        "prove_list_ops_first_str",
        "prove_list_ops_first_float",
        "prove_list_ops_last",
        "prove_list_ops_last_int",
        "prove_list_ops_last_str",
        "prove_list_ops_last_float",
        "prove_list_ops_value",
        "prove_list_ops_empty",
        "prove_list_ops_contains_int",
        "prove_list_ops_contains_str",
        "prove_list_ops_contains_float",
        "prove_list_ops_index_int",
        "prove_list_ops_index_str",
        "prove_list_ops_index_float",
        "prove_list_ops_slice",
        "prove_list_ops_reverse",
        "prove_list_ops_sort_int",
        "prove_list_ops_sort_str",
        "prove_list_ops_sort_float",
        "prove_list_ops_range",
        "prove_list_ops_range_step",
        "prove_list_ops_get_int",
        "prove_list_ops_get_str",
        "prove_list_ops_get_float",
        "prove_list_ops_get_value",
        "prove_list_ops_get_safe_int",
        "prove_list_ops_get_safe_str",
        "prove_list_ops_get_safe_float",
        "prove_list_ops_get_safe_value",
        "prove_list_ops_set",
        "prove_list_ops_remove",
    ],
    "prove_format": [
        "prove_format_pad_left",
        "prove_format_pad_right",
        "prove_format_center",
        "prove_format_hex",
        "prove_format_binary",
        "prove_format_octal",
        "prove_format_decimal",
    ],
    "prove_path": [
        "prove_path_join",
        "prove_path_parent",
        "prove_path_name",
        "prove_path_stem",
        "prove_path_extension",
        "prove_path_absolute",
        "prove_path_normalize",
    ],
    "prove_time": [
        "prove_time_now",
        "prove_time_validates",
        "prove_time_creates_duration",
        "prove_time_reads_duration",
        "prove_time_validates_duration",
        "prove_time_transforms_duration",
        "prove_time_reads_date",
        "prove_time_creates_date",
        "prove_time_validates_date",
        "prove_time_transforms_date",
        "prove_time_reads_datetime",
        "prove_time_creates_datetime",
        "prove_time_validates_datetime",
        "prove_time_transforms_datetime",
        "prove_time_reads_days",
        "prove_time_validates_days",
        "prove_time_reads_weekday",
        "prove_time_validates_weekday",
        "prove_time_reads_clock",
        "prove_time_creates_clock",
        "prove_time_validates_clock",
        "prove_time_string_time",
        "prove_time_string_date",
        "prove_time_string_datetime",
        "prove_time_string_clock",
        "prove_time_string_duration",
        "prove_time_format_time",
        "prove_time_parse_time",
        "prove_time_validates_time",
        "prove_time_format_date",
        "prove_time_parse_date",
        "prove_time_validates_date_str",
        "prove_time_format_datetime",
        "prove_time_parse_datetime",
        "prove_time_validates_datetime_str",
        "prove_time_format_duration",
        "prove_time_parse_duration",
    ],
    "prove_bytes": [
        "prove_bytes_from_string",
        "prove_bytes_to_string",
        "prove_bytes_create",
        "prove_bytes_validates",
        "prove_bytes_slice",
        "prove_bytes_concat",
        "prove_bytes_hex_encode",
        "prove_bytes_hex_decode",
        "prove_bytes_hex_validates",
        "prove_bytes_at",
        "prove_bytes_at_validates",
    ],
    "prove_hash_crypto": [
        "prove_crypto_sha256_bytes",
        "prove_crypto_sha256_string",
        "prove_crypto_sha256_validates",
        "prove_crypto_sha512_bytes",
        "prove_crypto_sha512_string",
        "prove_crypto_sha512_validates",
        "prove_crypto_blake3_bytes",
        "prove_crypto_blake3_string",
        "prove_crypto_blake3_validates",
        "prove_crypto_hmac_create",
        "prove_crypto_hmac_validates",
    ],
    "prove_random": [
        "prove_random_integer",
        "prove_random_integer_range",
        "prove_random_validates_integer",
        "prove_random_decimal",
        "prove_random_decimal_range",
        "prove_random_boolean",
        "prove_random_choice_raw",
        "prove_random_choice_int",
        "prove_random_choice_str",
        "prove_random_shuffle_raw",
        "prove_random_shuffle_int",
        "prove_random_shuffle_str",
    ],
    "prove_lookup": [
        "prove_lookup_find",
        "prove_lookup_find_int",
        "prove_lookup_find_sorted",
        "prove_lookup_find_int_sorted",
    ],
    "prove_pattern": [
        "prove_pattern_match",
        "prove_pattern_search",
        "prove_pattern_find_all",
        "prove_pattern_replace",
        "prove_pattern_split",
        "prove_pattern_text",
        "prove_pattern_start",
        "prove_pattern_end",
    ],
    "prove_par_map": [
        "prove_par_map",
        "prove_par_filter",
        "prove_par_reduce",
        "prove_par_each",
    ],
    "prove_store": [
        "prove_store_create",
        "prove_store_validates",
        "prove_store_table_inputs",
        "prove_store_table_outputs",
        "prove_store_table_validates",
        "prove_store_diff",
        "prove_store_patch",
        "prove_store_merge",
        "prove_store_merged_validates",
        "prove_store_merged",
        "prove_store_conflicts",
        "prove_store_conflict_variant",
        "prove_store_conflict_column",
        "prove_store_conflict_local_value",
        "prove_store_conflict_remote_value",
        "prove_store_lookup_outputs",
        "prove_store_lookup_inputs",
        "prove_store_integrity",
        "prove_store_rollback",
        "prove_store_version_inputs",
        "prove_store_table_new",
        "prove_store_table_add_variant",
        "prove_store_table_find",
        "prove_store_table_find_int",
        "prove_store_table_add",
    ],
    "prove_array": [
        "prove_array_new",
        "prove_array_new_bool",
        "prove_array_new_int",
        "prove_array_new_float",
        "prove_array_get",
        "prove_array_get_bool",
        "prove_array_get_int",
        "prove_array_get_float",
        "prove_array_set",
        "prove_array_set_bool",
        "prove_array_set_int",
        "prove_array_set_float",
        "prove_array_set_mut",
        "prove_array_set_mut_bool",
        "prove_array_set_mut_int",
        "prove_array_set_mut_float",
        "prove_array_length",
        "prove_array_get_safe_bool",
        "prove_array_get_safe_int",
        "prove_array_get_safe_float",
        "prove_array_set_safe_bool",
        "prove_array_set_safe_int",
        "prove_array_set_safe_float",
        "prove_array_map",
        "prove_array_reduce",
        "prove_array_each",
        "prove_array_filter",
        "prove_array_to_list",
        "prove_array_from_list",
        "prove_array_first_bool",
        "prove_array_first_int",
        "prove_array_first_float",
        "prove_array_last_bool",
        "prove_array_last_int",
        "prove_array_last_float",
        "prove_array_empty",
        "prove_array_contains_bool",
        "prove_array_contains_int",
        "prove_array_contains_float",
        "prove_array_index_int",
        "prove_array_index_bool",
        "prove_array_index_float",
        "prove_array_slice_bool",
        "prove_array_slice_int",
        "prove_array_slice_float",
        "prove_array_reverse_bool",
        "prove_array_reverse_int",
        "prove_array_reverse_float",
        "prove_array_sort_int",
        "prove_array_sort_float",
        "prove_array_free",
    ],
    "prove_network": [
        "prove_network_socket_inputs",
        "prove_network_socket_outputs",
        "prove_network_socket_validates",
        "prove_network_server_inputs",
        "prove_network_accept_inputs",
        "prove_network_message_inputs",
        "prove_network_message_outputs",
    ],
    "prove_language": [
        "prove_language_words",
        "prove_language_sentences",
        "prove_language_stem",
        "prove_language_root",
        "prove_language_distance",
        "prove_language_similarity",
        "prove_language_soundex",
        "prove_language_metaphone",
        "prove_language_ngrams",
        "prove_language_bigrams",
        "prove_language_normalize",
        "prove_language_transliterate",
        "prove_language_stopwords",
        "prove_language_without_stopwords",
        "prove_language_frequency",
        "prove_language_keywords",
    ],
    "prove_ansi": [
        "prove_ansi_escape",
    ],
    "prove_terminal": [
        "prove_terminal_validates",
        "prove_terminal_raw",
        "prove_terminal_cooked",
        "prove_terminal_write",
        "prove_terminal_write_at",
        "prove_terminal_clear",
        "prove_terminal_cursor",
        "prove_terminal_size",
        "prove_terminal_color_ansi",
        "prove_terminal_read_key",
        "prove_terminal_init",
        "prove_terminal_cleanup",
        "prove_terminal_check_resize",
    ],
    "prove_gui": [
        "prove_gui_window",
        "prove_gui_button",
        "prove_gui_label",
        "prove_gui_text_input",
        "prove_gui_checkbox",
        "prove_gui_slider",
        "prove_gui_progress",
        "prove_gui_quit",
        "prove_gui_init",
        "prove_gui_cleanup",
        "prove_gui_frame_begin",
        "prove_gui_frame_end",
        "prove_gui_window_end",
    ],
    "prove_prove": [
        "prove_parse_tree",
        "prove_parse_string_tree",
        "prove_prove_root",
        "prove_prove_kind",
        "prove_prove_parent",
        "prove_prove_string",
        "prove_prove_children",
        "prove_prove_child",
        "prove_prove_line",
        "prove_prove_column",
        "prove_prove_error",
        "prove_prove_count",
        "prove_prove_named_children",
    ],
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


_VENDOR_LIB_ALIASES: dict[str, str] = {
    "sdl2": "prove_gui",
    "tree-sitter": "prove_prove",
}


def copy_runtime(
    build_dir: Path,
    c_sources: list[str] | None = None,
    stdlib_libs: set[str] | None = None,
    *,
    strip_unused: bool = True,
    force_libs: list[str] | None = None,
) -> list[Path]:
    """Copy bundled runtime files to *build_dir*/runtime/.

    If *c_sources* is provided and *strip_unused* is True, only copies runtime
    files that contain functions used in the C sources.  This is the primary
    mechanism for usage-based linking.

    If *stdlib_libs* is provided, includes runtime files for those stdlib modules
    as a fallback (handles indirect dependencies from imports).

    If *force_libs* is provided (from prove.toml ``vendor_libs``), those libs are
    always included.  Accepts friendly names (``"sdl2"``, ``"tree-sitter"``) or
    raw prove lib names (``"prove_gui"``, ``"prove_prove"``).

    Returns the list of .c files (needed for compilation).
    """
    dest = build_dir / "runtime"
    dest.mkdir(parents=True, exist_ok=True)

    if not strip_unused or not c_sources:
        return _copy_all_runtime_files(dest, stdlib_libs=stdlib_libs)

    all_calls = set()
    all_includes: set[str] = set()
    include_pattern = re.compile(r'#include\s+"(prove_[a-zA-Z0-9_]+)\.h"')
    for src in c_sources:
        all_calls.update(_extract_function_calls(src))
        for m in include_pattern.finditer(src):
            all_includes.add(m.group(1))

    needed_libs = set()
    for lib_name, funcs in _RUNTIME_FUNCTIONS.items():
        for func in funcs:
            if func in all_calls:
                needed_libs.add(lib_name)
                break
        else:
            # Also include libs whose header is explicitly included
            if lib_name in all_includes:
                needed_libs.add(lib_name)

    if stdlib_libs:
        needed_libs.update(stdlib_libs)

    if force_libs:
        for lib in force_libs:
            lib_name = _VENDOR_LIB_ALIASES.get(lib, lib)
            needed_libs.add(lib_name)

    # Resolve transitive header dependencies: if a library's header
    # includes another library's header, that library must also be copied.
    _HEADER_DEPS: dict[str, set[str]] = {
        "prove_parse": {"prove_table", "prove_hash"},
        "prove_input_output": {"prove_bytes"},
        "prove_language": {"prove_parse"},
        "prove_event": {"prove_coro"},
        "prove_terminal": {"prove_ansi"},
    }
    for lib in list(needed_libs):
        needed_libs.update(_HEADER_DEPS.get(lib, set()))

    needed_files: set[str] = set()
    lib_keys = set(_RUNTIME_FUNCTIONS.keys())
    for lib_name in needed_libs:
        for name in _RUNTIME_FILES:
            stem = name.rsplit(".", 1)[0]  # e.g. "prove_parse_json"
            if stem == lib_name:
                # Exact match: prove_hash.c for prove_hash
                needed_files.add(name)
            elif stem.startswith(lib_name + "_") and stem not in lib_keys:
                # Sub-file: prove_parse_json.c for prove_parse
                # but NOT prove_hash_crypto.c for prove_hash (it's its own lib)
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
        src_path = pkg.joinpath(name)
        dst = dest / name
        with importlib.resources.as_file(src_path) as resolved:
            shutil.copy2(resolved, dst)
        if name.endswith(".c"):
            c_files.append(dst)

    # Copy vendor dependencies for needed libs
    if "prove_gui" in needed_libs:
        vendor_dest = dest / "vendor"
        vendor_dest.mkdir(parents=True, exist_ok=True)
        vendor_pkg = pkg.joinpath("vendor")
        for vfile in ("nuklear.h",):
            src_path = vendor_pkg.joinpath(vfile)
            with importlib.resources.as_file(src_path) as resolved:
                shutil.copy2(resolved, vendor_dest / vfile)

    if "prove_prove" in needed_libs:
        vendor_pkg = pkg.joinpath("vendor")
        # tree-sitter-prove parser + scanner (tree-sitter core is linked via pkg-config)
        tsp_dest = dest / "vendor" / "tree_sitter_prove"
        tsp_ts = tsp_dest / "tree_sitter"
        tsp_dest.mkdir(parents=True, exist_ok=True)
        tsp_ts.mkdir(parents=True, exist_ok=True)
        tsp_pkg = vendor_pkg.joinpath("tree_sitter_prove")
        for vfile in ("parser.c", "scanner.c"):
            with importlib.resources.as_file(tsp_pkg.joinpath(vfile)) as resolved:
                shutil.copy2(resolved, tsp_dest / vfile)
                c_files.append(tsp_dest / vfile)
        with importlib.resources.as_file(tsp_pkg.joinpath("tree_sitter", "parser.h")) as resolved:
            shutil.copy2(resolved, tsp_ts / "parser.h")

    return c_files


# Runtime libs that require external dependencies — excluded from default copy.
# Only included when explicitly requested via stdlib_libs.
_EXTERNAL_DEP_LIBS = frozenset({"prove_gui", "prove_prove"})


def _copy_all_runtime_files(dest: Path, *, stdlib_libs: set[str] | None = None) -> list[Path]:
    """Copy all runtime files, excluding external-dep libs unless requested."""
    c_files: list[Path] = []
    pkg = importlib.resources.files("prove.runtime")
    for name in _RUNTIME_FILES:
        stem = name.rsplit(".", 1)[0]
        if stem in _EXTERNAL_DEP_LIBS and (not stdlib_libs or stem not in stdlib_libs):
            continue
        src = pkg.joinpath(name)
        dst = dest / name
        with importlib.resources.as_file(src) as src_path:
            shutil.copy2(src_path, dst)
        if name.endswith(".c"):
            c_files.append(dst)
    return c_files
