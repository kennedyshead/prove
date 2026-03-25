"""Load stdlib module signatures from bundled .prv files."""

from __future__ import annotations

import importlib.resources
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from prove.ast_nodes import LookupTypeDef, Module, TypeDef, TypeExpr

from prove.errors import CompileError
from prove.parse import parse
from prove.source import Span
from prove.symbols import FunctionSignature
from prove.types import (
    BOOLEAN,
    CHARACTER,
    ERROR_TY,
    INTEGER,
    STRING,
    STRUCT,
    UNIT,
    AlgebraicType,
    ArrayType,
    FunctionType,
    GenericInstance,
    ListType,
    PrimitiveType,
    RecordType,
    Type,
    TypeVariable,
    VariantInfo,
)

_DUMMY = Span("<stdlib>", 0, 0, 0, 0)

# ── Per-module registration ──────────────────────────────────────

# Populated by _register_module() calls below
_BINARY_C_MAP: dict[tuple[str, str | None, str], str] = {}
_BINARY_C_OVERLOADS: dict[tuple[str, str | None, str, str], str] = {}
_STDLIB_MODULES: dict[str, str] = {}
_STDLIB_LINK_FLAGS: dict[str, list[str]] = {}
_STDLIB_C_FLAGS: dict[str, list[str]] = {}
_MODULE_DISPLAY_NAMES: dict[str, str] = {}


def _register_module(
    name: str,
    *,
    display: str,
    prv_file: str,
    c_map: dict[tuple[str, str], str] | None = None,
    overloads: dict[tuple[str, str, str], str] | None = None,
    link_flags: list[str] | None = None,
    c_flags: list[str] | None = None,
    pkg_config: str | None = None,
    aliases: list[str] | None = None,
) -> None:
    """Register a stdlib module with all its metadata in one block."""
    key = name.lower()
    _STDLIB_MODULES[key] = prv_file
    _MODULE_DISPLAY_NAMES[key] = display

    if c_map:
        for (verb, func), c_name in c_map.items():
            _BINARY_C_MAP[(key, verb, func)] = c_name

    if overloads:
        for (verb, func, type_name), c_name in overloads.items():
            _BINARY_C_OVERLOADS[(key, verb, func, type_name)] = c_name

    # Resolve flags via pkg-config if specified
    if pkg_config:
        import subprocess

        try:
            result = subprocess.run(
                ["pkg-config", "--cflags", "--libs", pkg_config],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                flags = result.stdout.strip().split()
                pc_c = [f for f in flags if f.startswith(("-I", "-D"))]
                pc_l = [f for f in flags if not f.startswith(("-I", "-D"))]
                c_flags = (c_flags or []) + pc_c
                link_flags = (link_flags or []) + pc_l
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

    if link_flags:
        _STDLIB_LINK_FLAGS[key] = link_flags

    if c_flags:
        _STDLIB_C_FLAGS[key] = c_flags

    # Register aliases (e.g. "io" for "inputoutput")
    if aliases:
        for alias in aliases:
            alias_key = alias.lower()
            _STDLIB_MODULES[alias_key] = prv_file
            _MODULE_DISPLAY_NAMES[alias_key] = display
            if c_map:
                for (verb, func), c_name in c_map.items():
                    _BINARY_C_MAP[(alias_key, verb, func)] = c_name
            if overloads:
                for (verb, func, type_name), c_name in overloads.items():
                    _BINARY_C_OVERLOADS[(alias_key, verb, func, type_name)] = c_name
            if link_flags:
                _STDLIB_LINK_FLAGS[alias_key] = link_flags


# ── Module registrations ─────────────────────────────────────────

_register_module(
    "system",
    display="System",
    prv_file="system.prv",
    aliases=["io", "inputoutput"],
    c_map={
        ("outputs", "console"): "prove_println",
        ("inputs", "console"): "prove_readln",
        ("validates", "console"): "prove_io_console_validates",
        ("inputs", "file"): "prove_file_read",
        ("outputs", "file"): "prove_file_write",
        ("validates", "file"): "prove_io_file_validates",
        ("inputs", "system"): "prove_io_system_inputs",
        ("outputs", "system"): "prove_io_system_outputs",
        ("validates", "system"): "prove_io_system_validates",
        ("inputs", "dir"): "prove_io_dir_inputs",
        ("outputs", "dir"): "prove_io_dir_outputs",
        ("validates", "dir"): "prove_io_dir_validates",
        ("inputs", "process"): "prove_io_process_inputs",
        ("validates", "process"): "prove_io_process_validates",
        ("inputs", "reader"): "prove_file_open_read",
        ("inputs", "line"): "prove_file_readline_handle",
        ("outputs", "close"): "prove_file_close_handle",
        ("inputs", "writer"): "prove_file_open_append",
        ("outputs", "line"): "prove_file_writeln_handle",
        ("inputs", "cwd"): "prove_io_process_cwd",
    },
    overloads={
        ("inputs", "console", "Integer"): "prove_readexactly",
    },
)

_register_module(
    "character",
    display="Character",
    prv_file="character.prv",
    c_map={
        ("validates", "alphabetic"): "prove_character_alpha",
        ("validates", "digit"): "prove_character_digit",
        ("validates", "alphanumeric"): "prove_character_alnum",
        ("validates", "uppercase"): "prove_character_upper",
        ("validates", "lowercase"): "prove_character_lower",
        ("validates", "whitespace"): "prove_character_space",
        ("creates", "at"): "prove_character_at",
    },
)

_register_module(
    "text",
    display="Text",
    prv_file="text.prv",
    c_map={
        ("creates", "length"): "prove_text_length",
        ("reads", "slice"): "prove_text_slice",
        ("validates", "starts"): "prove_text_starts_with",
        ("validates", "ends"): "prove_text_ends_with",
        ("validates", "contains"): "prove_text_contains",
        ("creates", "index"): "prove_text_index_of",
        ("creates", "split"): "prove_text_split",
        ("creates", "join"): "prove_text_join",
        ("reads", "trim"): "prove_text_trim",
        ("reads", "lower"): "prove_text_to_lower",
        ("reads", "upper"): "prove_text_to_upper",
        ("reads", "replace"): "prove_text_replace",
        ("reads", "repeat"): "prove_text_repeat",
        ("creates", "builder"): "prove_text_builder",
        ("reads", "string"): "prove_text_write",
        ("reads", "char"): "prove_text_write_char",
        ("creates", "build"): "prove_text_build",
    },
    overloads={
        ("creates", "length", "StringBuilder"): "prove_text_builder_length",
    },
)

_register_module(
    "table",
    display="Table",
    prv_file="table.prv",
    c_map={
        ("creates", "new"): "prove_table_new",
        ("validates", "has"): "prove_table_has",
        ("reads", "add"): "prove_table_add",
        ("reads", "get"): "prove_table_get",
        ("reads", "remove"): "prove_table_remove",
        ("creates", "keys"): "prove_table_keys",
        ("reads", "values"): "prove_table_values",
        ("creates", "length"): "prove_table_length",
        ("creates", "table"): "prove_value_as_object",
    },
)

_register_module(
    "pattern",
    display="Pattern",
    prv_file="pattern.prv",
    c_map={
        ("validates", "test"): "prove_pattern_match",
        ("creates", "search"): "prove_pattern_search",
        ("creates", "find_all"): "prove_pattern_find_all",
        ("reads", "replace"): "prove_pattern_replace",
        ("creates", "split"): "prove_pattern_split",
        ("creates", "string"): "prove_pattern_text",
        ("creates", "start"): "prove_pattern_start",
        ("creates", "end"): "prove_pattern_end",
    },
)

_register_module(
    "path",
    display="Path",
    prv_file="path.prv",
    c_map={
        ("reads", "join"): "prove_path_join",
        ("reads", "parent"): "prove_path_parent",
        ("reads", "name"): "prove_path_name",
        ("reads", "stem"): "prove_path_stem",
        ("reads", "extension"): "prove_path_extension",
        ("validates", "absolute"): "prove_path_absolute",
        ("reads", "normalize"): "prove_path_normalize",
    },
)

_register_module(
    "format",
    display="Format",
    prv_file="format.prv",
    c_map={
        ("reads", "pad_left"): "prove_format_pad_left",
        ("reads", "pad_right"): "prove_format_pad_right",
        ("reads", "center"): "prove_format_center",
        ("creates", "octal"): "prove_format_octal",
        ("creates", "hexadecimal"): "prove_format_hex",
        ("creates", "bin"): "prove_format_binary",
        ("creates", "decimal"): "prove_format_decimal",
    },
    overloads={
        ("creates", "decimal", "Float"): "prove_format_decimal",
        ("creates", "time", "Time"): "prove_time_format_time",
        ("creates", "date", "Date"): "prove_time_format_date",
        ("creates", "datetime", "DateTime"): "prove_time_format_datetime",
        ("creates", "duration", "Duration"): "prove_time_format_duration",
    },
)

_register_module(
    "sequence",
    display="Sequence",
    prv_file="sequence.prv",
    c_map={
        ("creates", "length"): "prove_list_ops_length",
        ("reads", "value"): "prove_list_ops_value",
        ("validates", "empty"): "prove_list_ops_empty",
        ("reads", "slice"): "prove_list_ops_slice",
        ("reads", "reverse"): "prove_list_ops_reverse",
        ("reads", "set"): "prove_list_ops_set",
        ("reads", "remove"): "prove_list_ops_remove",
        ("creates", "range"): "prove_list_ops_range",
    },
    overloads={
        ("reads", "first", "List<Integer>"): "prove_list_ops_first_int",
        ("reads", "first", "List<String>"): "prove_list_ops_first_str",
        ("reads", "first", "List<Float>"): "prove_list_ops_first_float",
        ("reads", "first", "List<Decimal>"): "prove_list_ops_first_float",
        ("reads", "last", "List<Integer>"): "prove_list_ops_last_int",
        ("reads", "last", "List<String>"): "prove_list_ops_last_str",
        ("reads", "last", "List<Float>"): "prove_list_ops_last_float",
        ("reads", "last", "List<Decimal>"): "prove_list_ops_last_float",
        ("validates", "contains", "List<Integer>"): "prove_list_ops_contains_int",
        ("validates", "contains", "List<String>"): "prove_list_ops_contains_str",
        ("validates", "contains", "List<Float>"): "prove_list_ops_contains_float",
        ("validates", "contains", "List<Decimal>"): "prove_list_ops_contains_float",
        ("creates", "index", "List<Integer>"): "prove_list_ops_index_int",
        ("creates", "index", "List<String>"): "prove_list_ops_index_str",
        ("creates", "index", "List<Float>"): "prove_list_ops_index_float",
        ("creates", "index", "List<Decimal>"): "prove_list_ops_index_float",
        ("reads", "sort", "List<Integer>"): "prove_list_ops_sort_int",
        ("reads", "sort", "List<String>"): "prove_list_ops_sort_str",
        ("reads", "sort", "List<Float>"): "prove_list_ops_sort_float",
        ("reads", "sort", "List<Decimal>"): "prove_list_ops_sort_float",
        ("creates", "list", "Value<Csv>"): "prove_csv_as_list",
        ("creates", "list", "Value"): "prove_value_as_array",
        ("creates", "range", "Integer_Integer_Integer"): "prove_list_ops_range_step",
        # Array functions
        ("creates", "array", "Integer_Boolean"): "prove_array_new_bool",
        ("creates", "array", "Integer_Integer"): "prove_array_new_int",
        ("creates", "array", "Integer_Boolean:Mutable"): "prove_array_new_bool",
        ("creates", "array", "Integer_Integer:Mutable"): "prove_array_new_int",
        ("creates", "array", "Integer_Float"): "prove_array_new_float",
        ("creates", "array", "Integer_Float:Mutable"): "prove_array_new_float",
        ("creates", "array", "Integer_Decimal"): "prove_array_new_float",
        ("creates", "array", "Integer_Decimal:Mutable"): "prove_array_new_float",
        ("reads", "get", "Array<Boolean>"): "prove_array_get_bool",
        ("reads", "get", "Array<Integer>"): "prove_array_get_int",
        ("reads", "get", "Array<Boolean>:Mutable"): "prove_array_get_bool",
        ("reads", "get", "Array<Integer>:Mutable"): "prove_array_get_int",
        ("reads", "get", "Array<Float>"): "prove_array_get_float",
        ("reads", "get", "Array<Float>:Mutable"): "prove_array_get_float",
        ("reads", "get", "Array<Decimal>"): "prove_array_get_float",
        ("reads", "get", "Array<Decimal>:Mutable"): "prove_array_get_float",
        ("reads", "set", "Array<Boolean>"): "prove_array_set_bool",
        ("reads", "set", "Array<Integer>"): "prove_array_set_int",
        ("reads", "set", "Array<Float>"): "prove_array_set_float",
        ("reads", "set", "Array<Decimal>"): "prove_array_set_float",
        ("reads", "set", "Array<Boolean>:Mutable"): "prove_array_set_mut_bool",
        ("reads", "set", "Array<Integer>:Mutable"): "prove_array_set_mut_int",
        ("reads", "set", "Array<Float>:Mutable"): "prove_array_set_mut_float",
        ("reads", "set", "Array<Decimal>:Mutable"): "prove_array_set_mut_float",
        ("creates", "length", "Array<Boolean>"): "prove_array_length",
        ("creates", "length", "Array<Integer>"): "prove_array_length",
        ("creates", "length", "Array<Boolean>:Mutable"): "prove_array_length",
        ("creates", "length", "Array<Integer>:Mutable"): "prove_array_length",
        ("creates", "length", "Array<Float>"): "prove_array_length",
        ("creates", "length", "Array<Float>:Mutable"): "prove_array_length",
        ("creates", "length", "Array<Decimal>"): "prove_array_length",
        ("creates", "length", "Array<Decimal>:Mutable"): "prove_array_length",
        ("creates", "list", "Array<Boolean>"): "prove_array_to_list",
        ("creates", "list", "Array<Integer>"): "prove_array_to_list",
        ("creates", "list", "Array<Float>"): "prove_array_to_list",
        ("creates", "list", "Array<Decimal>"): "prove_array_to_list",
        # Array safe access
        ("reads", "get_safe", "Array<Boolean>"): "prove_array_get_safe_bool",
        ("reads", "get_safe", "Array<Integer>"): "prove_array_get_safe_int",
        ("reads", "get_safe", "Array<Boolean>:Mutable"): "prove_array_get_safe_bool",
        ("reads", "get_safe", "Array<Integer>:Mutable"): "prove_array_get_safe_int",
        ("reads", "get_safe", "Array<Float>"): "prove_array_get_safe_float",
        ("reads", "get_safe", "Array<Float>:Mutable"): "prove_array_get_safe_float",
        ("reads", "get_safe", "Array<Decimal>"): "prove_array_get_safe_float",
        ("reads", "get_safe", "Array<Decimal>:Mutable"): "prove_array_get_safe_float",
        ("creates", "set_safe", "Array<Boolean>"): "prove_array_set_safe_bool",
        ("creates", "set_safe", "Array<Integer>"): "prove_array_set_safe_int",
        ("creates", "set_safe", "Array<Float>"): "prove_array_set_safe_float",
        ("creates", "set_safe", "Array<Decimal>"): "prove_array_set_safe_float",
        ("creates", "set_safe", "Array<Boolean>:Mutable"): "prove_array_set_safe_bool",
        ("creates", "set_safe", "Array<Integer>:Mutable"): "prove_array_set_safe_int",
        ("creates", "set_safe", "Array<Float>:Mutable"): "prove_array_set_safe_float",
        ("creates", "set_safe", "Array<Decimal>:Mutable"): "prove_array_set_safe_float",
        # List get (unchecked indexed access)
        ("reads", "get", "List<Integer>"): "prove_list_ops_get_int",
        ("reads", "get", "List<String>"): "prove_list_ops_get_str",
        ("reads", "get", "List<Float>"): "prove_list_ops_get_float",
        ("reads", "get", "List<Decimal>"): "prove_list_ops_get_float",
        ("reads", "get", "List<Value>"): "prove_list_ops_get_value",
        # List get_safe (bounds-checked access)
        ("reads", "get_safe", "List<Integer>"): "prove_list_ops_get_safe_int",
        ("reads", "get_safe", "List<String>"): "prove_list_ops_get_safe_str",
        ("reads", "get_safe", "List<Float>"): "prove_list_ops_get_safe_float",
        ("reads", "get_safe", "List<Decimal>"): "prove_list_ops_get_safe_float",
        ("reads", "get_safe", "List<Value>"): "prove_list_ops_get_safe_value",
        # Array first / last
        ("reads", "first", "Array<Integer>"): "prove_array_first_int",
        ("reads", "first", "Array<Integer>:Mutable"): "prove_array_first_int",
        ("reads", "first", "Array<Boolean>"): "prove_array_first_bool",
        ("reads", "first", "Array<Boolean>:Mutable"): "prove_array_first_bool",
        ("reads", "first", "Array<Decimal>"): "prove_array_first_float",
        ("reads", "first", "Array<Decimal>:Mutable"): "prove_array_first_float",
        ("reads", "first", "Array<Float>"): "prove_array_first_float",
        ("reads", "first", "Array<Float>:Mutable"): "prove_array_first_float",
        ("reads", "last", "Array<Integer>"): "prove_array_last_int",
        ("reads", "last", "Array<Integer>:Mutable"): "prove_array_last_int",
        ("reads", "last", "Array<Boolean>"): "prove_array_last_bool",
        ("reads", "last", "Array<Boolean>:Mutable"): "prove_array_last_bool",
        ("reads", "last", "Array<Decimal>"): "prove_array_last_float",
        ("reads", "last", "Array<Decimal>:Mutable"): "prove_array_last_float",
        ("reads", "last", "Array<Float>"): "prove_array_last_float",
        ("reads", "last", "Array<Float>:Mutable"): "prove_array_last_float",
        # Array empty
        ("validates", "empty", "Array<Integer>"): "prove_array_empty",
        ("validates", "empty", "Array<Integer>:Mutable"): "prove_array_empty",
        ("validates", "empty", "Array<Boolean>"): "prove_array_empty",
        ("validates", "empty", "Array<Boolean>:Mutable"): "prove_array_empty",
        ("validates", "empty", "Array<Decimal>"): "prove_array_empty",
        ("validates", "empty", "Array<Decimal>:Mutable"): "prove_array_empty",
        ("validates", "empty", "Array<Float>"): "prove_array_empty",
        ("validates", "empty", "Array<Float>:Mutable"): "prove_array_empty",
        # Array contains
        ("validates", "contains", "Array<Integer>"): "prove_array_contains_int",
        ("validates", "contains", "Array<Integer>:Mutable"): "prove_array_contains_int",
        ("validates", "contains", "Array<Boolean>"): "prove_array_contains_bool",
        ("validates", "contains", "Array<Boolean>:Mutable"): "prove_array_contains_bool",
        ("validates", "contains", "Array<Float>"): "prove_array_contains_float",
        ("validates", "contains", "Array<Float>:Mutable"): "prove_array_contains_float",
        ("validates", "contains", "Array<Decimal>"): "prove_array_contains_float",
        ("validates", "contains", "Array<Decimal>:Mutable"): "prove_array_contains_float",
        # Array index
        ("creates", "index", "Array<Integer>"): "prove_array_index_int",
        ("creates", "index", "Array<Integer>:Mutable"): "prove_array_index_int",
        ("creates", "index", "Array<Boolean>"): "prove_array_index_bool",
        ("creates", "index", "Array<Boolean>:Mutable"): "prove_array_index_bool",
        ("creates", "index", "Array<Float>"): "prove_array_index_float",
        ("creates", "index", "Array<Float>:Mutable"): "prove_array_index_float",
        ("creates", "index", "Array<Decimal>"): "prove_array_index_float",
        ("creates", "index", "Array<Decimal>:Mutable"): "prove_array_index_float",
        # Array slice
        ("reads", "slice", "Array<Integer>"): "prove_array_slice_int",
        ("reads", "slice", "Array<Integer>:Mutable"): "prove_array_slice_int",
        ("reads", "slice", "Array<Boolean>"): "prove_array_slice_bool",
        ("reads", "slice", "Array<Boolean>:Mutable"): "prove_array_slice_bool",
        ("reads", "slice", "Array<Decimal>"): "prove_array_slice_float",
        ("reads", "slice", "Array<Decimal>:Mutable"): "prove_array_slice_float",
        ("reads", "slice", "Array<Float>"): "prove_array_slice_float",
        ("reads", "slice", "Array<Float>:Mutable"): "prove_array_slice_float",
        # Array reverse
        ("reads", "reverse", "Array<Integer>"): "prove_array_reverse_int",
        ("reads", "reverse", "Array<Integer>:Mutable"): "prove_array_reverse_int",
        ("reads", "reverse", "Array<Boolean>"): "prove_array_reverse_bool",
        ("reads", "reverse", "Array<Boolean>:Mutable"): "prove_array_reverse_bool",
        ("reads", "reverse", "Array<Decimal>"): "prove_array_reverse_float",
        ("reads", "reverse", "Array<Decimal>:Mutable"): "prove_array_reverse_float",
        ("reads", "reverse", "Array<Float>"): "prove_array_reverse_float",
        ("reads", "reverse", "Array<Float>:Mutable"): "prove_array_reverse_float",
        # Array sort
        ("reads", "sort", "Array<Integer>"): "prove_array_sort_int",
        ("reads", "sort", "Array<Integer>:Mutable"): "prove_array_sort_int",
        ("reads", "sort", "Array<Decimal>"): "prove_array_sort_float",
        ("reads", "sort", "Array<Decimal>:Mutable"): "prove_array_sort_float",
        ("reads", "sort", "Array<Float>"): "prove_array_sort_float",
        ("reads", "sort", "Array<Float>:Mutable"): "prove_array_sort_float",
    },
    aliases=["list", "array"],
)

_register_module(
    "types",
    display="Types",
    prv_file="types.prv",
    c_map={
        ("creates", "code"): "prove_convert_code",
        ("creates", "string"): "prove_value_as_text",
        ("validates", "text"): "prove_value_is_text",
        ("validates", "number"): "prove_value_is_number",
        ("validates", "decimal"): "prove_value_is_decimal",
        ("validates", "boolean"): "prove_value_is_boolean",
        ("validates", "array"): "prove_value_is_array",
        ("validates", "object"): "prove_value_is_object",
        ("validates", "unit"): "prove_value_is_unit",
        ("validates", "value"): "prove_validates_value",
        ("validates", "ok"): "prove_error_ok",
        ("validates", "error"): "prove_error_err",
    },
    overloads={
        ("creates", "integer", "String"): "prove_convert_integer_str",
        ("creates", "integer", "Float"): "prove_convert_integer_float",
        ("creates", "integer", "Decimal"): "prove_convert_integer_decimal",
        ("creates", "float", "String"): "prove_convert_float_str",
        ("creates", "float", "Integer"): "prove_convert_float_int",
        ("creates", "float", "Decimal"): "prove_convert_float_decimal",
        ("creates", "decimal", "String"): "prove_convert_decimal_str",
        ("creates", "decimal", "Integer"): "prove_convert_decimal_int",
        ("creates", "string", "Integer"): "prove_convert_string_int",
        ("creates", "string", "Float"): "prove_convert_string_float",
        ("creates", "string", "Decimal"): "prove_convert_string_float",
        ("creates", "string", "Boolean"): "prove_convert_string_bool",
        ("creates", "string", "Byte"): "prove_convert_string_byte",
        ("creates", "string", "Character"): "prove_string_from_char",
        ("creates", "string", "Time"): "prove_time_string_time",
        ("creates", "string", "Date"): "prove_time_string_date",
        ("creates", "string", "DateTime"): "prove_time_string_datetime",
        ("creates", "string", "Clock"): "prove_time_string_clock",
        ("creates", "string", "Duration"): "prove_time_string_duration",
        ("creates", "string", "Value"): "prove_value_as_text",
        ("creates", "string", "ByteArray"): "prove_bytes_to_string",
        ("creates", "string", "Value<Json>"): "prove_emit_json",
        ("creates", "string", "Value<Toml>"): "prove_emit_toml",
        ("creates", "string", "Value<Csv>"): "prove_emit_csv",
        ("creates", "string", "Value<Tree>"): "prove_parse_string_tree",
        ("creates", "string", "Url"): "prove_parse_url_host_reads",
        ("creates", "string", "Token"): "prove_parse_token_text",
        ("creates", "string", "Position"): "prove_convert_string_position",
        ("creates", "integer", "Boolean"): "prove_convert_integer_bool",
        ("creates", "integer", "Value"): "prove_value_as_number",
        ("creates", "float", "Value"): "prove_value_as_decimal",
        ("creates", "decimal", "Value"): "prove_value_as_decimal",
        ("creates", "boolean", "Value"): "prove_value_as_bool",
        ("creates", "boolean", "Integer"): "prove_convert_boolean_int",
        ("creates", "boolean", "String"): "prove_convert_boolean_str",
        ("creates", "character", "Integer"): "prove_convert_character",
        ("validates", "value", "Option<Integer>"): "prove_error_some_int",
        ("validates", "value", "Option<String>"): "prove_error_some_str",
        ("validates", "value", "Option<Float>"): "prove_error_some_float",
        ("validates", "value", "Option<Decimal>"): "prove_error_some_decimal",
        ("validates", "value", "Option<Boolean>"): "prove_error_some_bool",
        ("validates", "unit", "Option<Integer>"): "prove_error_none_int",
        ("validates", "unit", "Option<String>"): "prove_error_none_str",
        ("validates", "unit", "Option<Float>"): "prove_error_none_float",
        ("validates", "unit", "Option<Decimal>"): "prove_error_none_decimal",
        ("validates", "unit", "Option<Boolean>"): "prove_error_none_bool",
        ("reads", "unwrap", "Option<Integer>"): "prove_error_unwrap_or_int",
        ("reads", "unwrap", "Option<String>"): "prove_error_unwrap_or_str",
        ("reads", "unwrap", "Option<Float>"): "prove_error_unwrap_or_float",
        ("reads", "unwrap", "Option<Decimal>"): "prove_error_unwrap_or_float",
        ("reads", "unwrap", "Option<Boolean>"): "prove_error_unwrap_or_bool",
        ("reads", "unwrap", "Option<Value>"): "prove_error_unwrap_or",
    },
)

_register_module(
    "math",
    display="Math",
    prv_file="math.prv",
    link_flags=["-lm"],
    c_map={
        ("reads", "sqrt"): "prove_math_sqrt",
        ("reads", "pow"): "prove_math_pow",
        ("reads", "power"): "prove_math_pow",
        ("creates", "floor"): "prove_math_floor",
        ("creates", "ceil"): "prove_math_ceil",
        ("creates", "round"): "prove_math_round",
        ("reads", "log"): "prove_math_log",
        ("reads", "log10"): "prove_math_log10",
        ("reads", "sin"): "prove_math_sin",
        ("reads", "cos"): "prove_math_cos",
        ("reads", "tan"): "prove_math_tan",
        ("reads", "asin"): "prove_math_asin",
        ("reads", "acos"): "prove_math_acos",
        ("reads", "atan"): "prove_math_atan",
        ("reads", "atan2"): "prove_math_atan2",
        ("reads", "exp"): "prove_math_exp",
        ("reads", "log2"): "prove_math_log2",
        ("reads", "pi"): "prove_math_pi",
        ("reads", "e"): "prove_math_e",
    },
    overloads={
        ("reads", "abs", "Integer"): "prove_math_abs_int",
        ("reads", "abs", "Float"): "prove_math_abs_float",
        ("reads", "abs", "Decimal"): "prove_math_abs_float",
        ("reads", "min", "Integer"): "prove_math_min_int",
        ("reads", "min", "Float"): "prove_math_min_float",
        ("reads", "min", "Decimal"): "prove_math_min_float",
        ("reads", "max", "Integer"): "prove_math_max_int",
        ("reads", "max", "Float"): "prove_math_max_float",
        ("reads", "max", "Decimal"): "prove_math_max_float",
        ("reads", "clamp", "Integer"): "prove_math_clamp_int",
        ("reads", "clamp", "Float"): "prove_math_clamp_float",
        ("reads", "clamp", "Decimal"): "prove_math_clamp_float",
    },
)

_register_module(
    "time",
    display="Time",
    prv_file="time.prv",
    c_map={
        ("inputs", "time"): "prove_time_now",
        ("creates", "duration"): "prove_time_creates_duration",
        ("creates", "date"): "prove_time_creates_date",
        ("creates", "datetime"): "prove_time_creates_datetime",
        ("creates", "clock"): "prove_time_creates_clock",
        ("reads", "days"): "prove_time_reads_days",
        ("validates", "days"): "prove_time_validates_days",
    },
    overloads={
        ("validates", "time", "Time"): "prove_time_validates",
        ("reads", "duration", "Duration"): "prove_time_reads_duration",
        ("validates", "duration", "Duration"): "prove_time_validates_duration",
        ("creates", "duration", "Time"): "prove_time_transforms_duration",
        ("creates", "date", "Time"): "prove_time_reads_date",
        ("validates", "date", "Integer"): "prove_time_validates_date",
        ("reads", "date", "Date"): "prove_time_transforms_date",
        ("creates", "datetime", "Time"): "prove_time_reads_datetime",
        ("validates", "datetime", "DateTime"): "prove_time_validates_datetime",
        ("creates", "datetime", "DateTime"): "prove_time_transforms_datetime",
        ("creates", "weekday", "Date"): "prove_time_reads_weekday",
        ("validates", "weekday", "Date"): "prove_time_validates_weekday",
        ("creates", "clock", "Time"): "prove_time_reads_clock",
        ("validates", "clock", "Integer"): "prove_time_validates_clock",
    },
)

_register_module(
    "random",
    display="Random",
    prv_file="random.prv",
    c_map={
        ("inputs", "integer"): "prove_random_integer",
        ("validates", "integer"): "prove_random_validates_integer",
        ("inputs", "decimal"): "prove_random_decimal",
        ("inputs", "boolean"): "prove_random_boolean",
    },
    overloads={
        ("inputs", "integer", "Integer"): "prove_random_integer_range",
        ("inputs", "decimal", "Float"): "prove_random_decimal_range",
        ("inputs", "choice", "List<Integer>"): "prove_random_choice_int",
        ("inputs", "choice", "List<String>"): "prove_random_choice_str",
        ("inputs", "shuffle", "List<Integer>"): "prove_random_shuffle_int",
        ("inputs", "shuffle", "List<String>"): "prove_random_shuffle_str",
    },
)

_register_module(
    "hash",
    display="Hash",
    prv_file="hash.prv",
    c_map={
        ("validates", "sha256"): "prove_crypto_sha256_validates",
        ("validates", "sha512"): "prove_crypto_sha512_validates",
        ("validates", "blake3"): "prove_crypto_blake3_validates",
        ("creates", "hmac"): "prove_crypto_hmac_create",
        ("validates", "hmac"): "prove_crypto_hmac_validates",
    },
    overloads={
        ("creates", "sha256", "ByteArray"): "prove_crypto_sha256_bytes",
        ("creates", "sha256", "String"): "prove_crypto_sha256_string",
        ("creates", "sha512", "ByteArray"): "prove_crypto_sha512_bytes",
        ("creates", "sha512", "String"): "prove_crypto_sha512_string",
        ("creates", "blake3", "ByteArray"): "prove_crypto_blake3_bytes",
        ("creates", "blake3", "String"): "prove_crypto_blake3_string",
    },
)

_register_module(
    "bytes",
    display="Bytes",
    prv_file="bytes.prv",
    c_map={
        ("creates", "bytearray"): "prove_bytes_create",
        ("validates", "bytearray"): "prove_bytes_validates",
        ("validates", "exist"): "prove_bytes_at_validates",
    },
    overloads={
        ("reads", "bytearray", "ByteArray_Integer"): "prove_bytes_slice",
        ("reads", "bytearray", "ByteArray_ByteArray"): "prove_bytes_concat",
        ("creates", "at", "ByteArray"): "prove_bytes_at",
    },
)

_register_module(
    "parse",
    display="Parse",
    prv_file="parse.prv",
    c_map={
        ("creates", "toml"): "prove_parse_toml",
        ("creates", "json"): "prove_parse_json",
        ("creates", "tag"): "prove_value_tag",
        ("validates", "json"): "prove_validates_json",
        ("validates", "toml"): "prove_validates_toml",
        ("creates", "value"): "prove_creates_value",
        ("creates", "url"): "prove_parse_url",
        ("validates", "url"): "prove_parse_url_validates",
        ("transforms", "url"): "prove_parse_url_transform",
        ("creates", "hexadecimal"): "prove_bytes_hex_decode",
        ("validates", "hexadecimal"): "prove_bytes_hex_validates",
        ("creates", "base64"): "prove_parse_base64_decode",
        ("validates", "base64"): "prove_parse_base64_validates",
        ("creates", "arguments"): "prove_parse_arguments",
        ("creates", "csv"): "prove_parse_csv",
        ("validates", "csv"): "prove_validates_csv",
        ("creates", "port"): "prove_parse_url_port_reads",
        ("creates", "time"): "prove_time_parse_time",
        ("validates", "time"): "prove_time_validates_time",
        ("creates", "date"): "prove_time_parse_date",
        ("validates", "date"): "prove_time_validates_date_str",
        ("creates", "datetime"): "prove_time_parse_datetime",
        ("validates", "datetime"): "prove_time_validates_datetime_str",
        ("creates", "duration"): "prove_time_parse_duration",
        ("creates", "rule"): "prove_parse_rule",
        ("creates", "tokens"): "prove_parse_tokens",
        ("creates", "tree"): "prove_parse_tree",
    },
    overloads={
        ("creates", "json", "String"): "prove_parse_json",
        ("creates", "json", "Value"): "prove_tag_json",
        ("creates", "toml", "String"): "prove_parse_toml",
        ("creates", "toml", "Value"): "prove_tag_toml",
        ("creates", "url", "String_String"): "prove_parse_url_create",
        ("creates", "hexadecimal", "ByteArray"): "prove_bytes_hex_encode",
        ("creates", "base64", "ByteArray"): "prove_parse_base64_encode",
    },
)

_register_module(
    "log",
    display="Log",
    prv_file="pure/log.prv",
)

_register_module(
    "store",
    display="Store",
    prv_file="store.prv",
    c_map={
        ("outputs", "store"): "prove_store_create",
        ("validates", "store"): "prove_store_validates",
        ("inputs", "table"): "prove_store_table_inputs",
        ("outputs", "table"): "prove_store_table_outputs",
        ("validates", "table"): "prove_store_table_validates",
        ("creates", "diff"): "prove_store_diff",
        ("reads", "patch"): "prove_store_patch",
        ("creates", "merge"): "prove_store_merge",
        ("validates", "merged"): "prove_store_merged_validates",
        ("creates", "merged"): "prove_store_merged",
        ("creates", "conflicts"): "prove_store_conflicts",
        ("creates", "variant"): "prove_store_conflict_variant",
        ("creates", "column"): "prove_store_conflict_column",
        ("creates", "local_value"): "prove_store_conflict_local_value",
        ("creates", "remote_value"): "prove_store_conflict_remote_value",
        ("outputs", "lookup"): "prove_store_lookup_outputs",
        ("inputs", "lookup"): "prove_store_lookup_inputs",
        ("creates", "integrity"): "prove_store_integrity",
        ("outputs", "rollback"): "prove_store_rollback",
        ("inputs", "version"): "prove_store_version_inputs",
        ("outputs", "add"): "prove_store_table_add",
    },
)

_register_module(
    "network",
    display="Network",
    prv_file="network.prv",
    c_map={
        ("inputs", "socket"): "prove_network_socket_inputs",
        ("outputs", "socket"): "prove_network_socket_outputs",
        ("validates", "socket"): "prove_network_socket_validates",
        ("inputs", "server"): "prove_network_server_inputs",
        ("inputs", "accept"): "prove_network_accept_inputs",
        ("inputs", "message"): "prove_network_message_inputs",
        ("outputs", "message"): "prove_network_message_outputs",
    },
)

_register_module(
    "language",
    display="Language",
    prv_file="language.prv",
    c_map={
        ("creates", "words"): "prove_language_words",
        ("creates", "sentences"): "prove_language_sentences",
        ("reads", "stem"): "prove_language_stem",
        ("reads", "root"): "prove_language_root",
        ("creates", "distance"): "prove_language_distance",
        ("creates", "similarity"): "prove_language_similarity",
        ("reads", "soundex"): "prove_language_soundex",
        ("reads", "metaphone"): "prove_language_metaphone",
        ("creates", "ngrams"): "prove_language_ngrams",
        ("creates", "bigrams"): "prove_language_bigrams",
        ("reads", "normalize"): "prove_language_normalize",
        ("reads", "transliterate"): "prove_language_transliterate",
        ("reads", "stopwords"): "prove_language_stopwords",
        ("creates", "without_stopwords"): "prove_language_without_stopwords",
        ("creates", "frequency"): "prove_language_frequency",
        ("creates", "keywords"): "prove_language_keywords",
        ("creates", "start"): "prove_parse_token_start",
        ("creates", "end"): "prove_parse_token_end",
        ("creates", "kind"): "prove_parse_token_kind",
    },
    overloads={
        ("creates", "start", "Token"): "prove_parse_token_start",
        ("creates", "end", "Token"): "prove_parse_token_end",
        ("creates", "kind", "Token"): "prove_parse_token_kind",
    },
)

_register_module(
    "ui",
    display="UI",
    prv_file="ui.prv",
)

_register_module(
    "terminal",
    display="Terminal",
    prv_file="terminal.prv",
    c_map={
        ("validates", "terminal"): "prove_terminal_validates",
        ("outputs", "raw"): "prove_terminal_raw",
        ("outputs", "cooked"): "prove_terminal_cooked",
        ("outputs", "terminal"): "prove_terminal_write",
        ("outputs", "clear"): "prove_terminal_clear",
        ("outputs", "cursor"): "prove_terminal_cursor",
        ("reads", "size"): "prove_terminal_size",
        ("reads", "ansi"): "prove_terminal_color_ansi",
    },
    overloads={
        ("outputs", "terminal", "Integer_Integer_String"): "prove_terminal_write_at",
    },
)

_register_module(
    "graphic",
    display="Graphic",
    prv_file="graphic.prv",
    c_map={
        ("outputs", "window"): "prove_gui_window",
        ("outputs", "button"): "prove_gui_button",
        ("outputs", "label"): "prove_gui_label",
        ("outputs", "text_input"): "prove_gui_text_input",
        ("outputs", "checkbox"): "prove_gui_checkbox",
        ("outputs", "slider"): "prove_gui_slider",
        ("outputs", "progress"): "prove_gui_progress",
        ("outputs", "quit"): "prove_gui_quit",
    },
    pkg_config="sdl2",
    link_flags=["-framework", "OpenGL"],
)

_register_module(
    "prove",
    display="Prove",
    prv_file="prove.prv",
    c_map={
        ("reads", "root"): "prove_prove_root",
        ("creates", "kind"): "prove_prove_kind",
        ("creates", "string"): "prove_prove_string",
        ("creates", "children"): "prove_prove_children",
        ("creates", "child"): "prove_prove_child",
        ("creates", "line"): "prove_prove_line",
        ("creates", "column"): "prove_prove_column",
        ("validates", "error"): "prove_prove_error",
        ("creates", "count"): "prove_prove_count",
        ("creates", "named_children"): "prove_prove_named_children",
    },
    pkg_config="tree-sitter",
)


def binary_c_name(
    module: str,
    verb: str | None,
    name: str,
    first_param_type: str | None = None,
) -> str | None:
    """Look up the C runtime function for a binary stdlib function."""
    key = module.lower()
    if first_param_type is not None:
        overload = _BINARY_C_OVERLOADS.get((key, verb, name, first_param_type))
        if overload is not None:
            return overload
    return _BINARY_C_MAP.get((key, verb, name))


def binary_c_name_overload_only(
    module: str,
    verb: str | None,
    name: str,
    first_param_type: str,
) -> str | None:
    """Look up overload-only (no generic fallback) for a binary stdlib function."""
    key = module.lower()
    return _BINARY_C_OVERLOADS.get((key, verb, name, first_param_type))


# Cache loaded signatures
_cache: dict[str, list[FunctionSignature]] = {}


# ── Stdlib constants ──────────────────────────────────────────────


@dataclass(frozen=True)
class StdlibConstant:
    """A constant exported from a pure-Prove stdlib module."""

    name: str
    type_name: str
    raw_value: str


_const_cache: dict[str, list[StdlibConstant]] = {}


def load_stdlib_constants(module_name: str) -> list[StdlibConstant]:
    """Load constant definitions from a stdlib module.

    Returns an empty list if the module has no constants.
    """
    normalized = module_name.lower()

    if normalized in _const_cache:
        return _const_cache[normalized]

    module = _parse_stdlib_module(normalized)
    if module is None:
        _const_cache[normalized] = []
        return []

    from prove.ast_nodes import ModuleDecl, StringLit

    constants: list[StdlibConstant] = []
    for decl in module.declarations:
        if isinstance(decl, ModuleDecl):
            for const in decl.constants:
                type_name = "String"
                if const.type_expr is not None and hasattr(const.type_expr, "name"):
                    type_name = const.type_expr.name
                raw_value = ""
                if isinstance(const.value, StringLit):
                    raw_value = const.value.value
                constants.append(StdlibConstant(const.name, type_name, raw_value))

    _const_cache[normalized] = constants
    return constants


_KNOWN_TYPES = {
    "Integer": INTEGER,
    "String": STRING,
    "Boolean": BOOLEAN,
    "Character": CHARACTER,
    "Unit": UNIT,
    "Float": PrimitiveType("Float"),
    "Match": PrimitiveType("Match"),
    "Time": PrimitiveType("Time"),
    "Duration": PrimitiveType("Duration"),
    "Date": PrimitiveType("Date"),
    "Clock": PrimitiveType("Clock"),
    "DateTime": PrimitiveType("DateTime"),
    "Weekday": PrimitiveType("Weekday"),
    "ByteArray": PrimitiveType("ByteArray"),
    "Algorithm": PrimitiveType("Algorithm"),
    "Url": PrimitiveType("Url"),
    "Store": PrimitiveType("Store"),
    "StoreTable": PrimitiveType("StoreTable"),
    "TableDiff": PrimitiveType("TableDiff"),
    "Version": PrimitiveType("Version"),
    "Conflict": PrimitiveType("Conflict"),
    "Resolution": PrimitiveType("Resolution"),
    "MergeResult": PrimitiveType("MergeResult"),
    "Socket": PrimitiveType("Socket"),
    "File": PrimitiveType("File"),
    "Token": PrimitiveType("Token"),
    "Json": PrimitiveType("Json"),
    "Toml": PrimitiveType("Toml"),
    "Csv": PrimitiveType("Csv"),
    "Tree": PrimitiveType("Tree"),
    "Struct": STRUCT,
}


_STDLIB_TYPE_VARS: frozenset[str] = frozenset({"Value", "Output", "Source"})


def _resolve_type_name(name: str) -> PrimitiveType | ListType | GenericInstance | TypeVariable:
    """Resolve a simple type name to a Type.

    Names in _STDLIB_TYPE_VARS are treated as type variables for generic
    signatures (e.g. Value, Output, Source).
    """
    if name in _KNOWN_TYPES:
        return _KNOWN_TYPES[name]  # type: ignore[return-value]
    if name in _STDLIB_TYPE_VARS:
        return TypeVariable(name)
    return PrimitiveType(name)


def _resolve_type_expr(
    type_expr: TypeExpr,
) -> PrimitiveType | ListType | GenericInstance | TypeVariable:
    """Resolve an AST TypeExpr to a semantic Type, handling generics and modifiers."""
    from prove.ast_nodes import GenericType, ModifiedType, SimpleType

    if isinstance(type_expr, GenericType):
        args = []
        for a in type_expr.args:
            if isinstance(a, SimpleType):
                args.append(_resolve_type_name(a.name))
            elif isinstance(a, ModifiedType):
                base = _resolve_type_name(a.name)
                mods = tuple((m.name, m.value) for m in a.modifiers)
                if isinstance(base, PrimitiveType):
                    args.append(PrimitiveType(base.name, modifiers=mods))
                else:
                    args.append(base)
            elif isinstance(a, GenericType):
                args.append(_resolve_type_expr(a))
            else:
                args.append(TypeVariable("Value"))
        if type_expr.name == "List" and len(args) == 1:
            return ListType(args[0])
        if type_expr.name == "Array" and len(args) == 1:
            mods = tuple((m.name, m.value) for m in type_expr.modifiers)
            if mods:
                return ArrayType(args[0], modifiers=mods)  # type: ignore[return-value]
            return ArrayType(args[0])  # type: ignore[return-value]
        if type_expr.name == "Verb" and len(args) >= 1:
            return FunctionType(list(args[:-1]), args[-1])  # type: ignore[return-value]
        return GenericInstance(type_expr.name, args)

    if isinstance(type_expr, ModifiedType):
        base = _resolve_type_name(type_expr.name)
        mods = tuple((m.name, m.value) for m in type_expr.modifiers)
        if isinstance(base, PrimitiveType):
            return PrimitiveType(base.name, modifiers=mods)
        return base

    if hasattr(type_expr, "name"):
        return _resolve_type_name(type_expr.name)

    return ERROR_TY  # type: ignore[return-value]


def load_stdlib(module_name: str) -> list[FunctionSignature]:
    """Load function signatures from a stdlib module.

    Returns an empty list if the module is not found.
    """
    # Normalize: "System" -> "system", "InputOutput" -> "inputoutput"
    normalized = module_name.lower()

    if normalized in _cache:
        return _cache[normalized]

    filename = _STDLIB_MODULES.get(normalized)
    if filename is None:
        return []

    pkg = importlib.resources.files("prove.stdlib")
    resource = pkg.joinpath(filename)

    try:
        source = resource.read_text(encoding="utf-8")
    except Exception:
        return []

    # Parse the stdlib file to extract function declarations
    try:
        module = parse(source, f"<stdlib:{module_name}>")
    except (CompileError, ValueError, IndexError):
        return []

    from prove.ast_nodes import FunctionDef, ModuleDecl

    sigs: list[FunctionSignature] = []
    all_decls = list(module.declarations)
    for decl in module.declarations:
        if isinstance(decl, ModuleDecl):
            all_decls.extend(decl.body)
    for decl in all_decls:
        if not isinstance(decl, FunctionDef):
            continue

        param_types = []
        param_names = []
        for p in decl.params:
            param_names.append(p.name)
            pt = _resolve_type_expr(p.type_expr)
            param_types.append(pt)

        # Resolve return type
        ret_type = BOOLEAN if decl.verb == "validates" else UNIT
        if decl.return_type is not None:
            ret_type = _resolve_type_expr(decl.return_type)  # type: ignore[assignment]

        sig = FunctionSignature(
            verb=decl.verb,
            name=decl.name,
            param_names=param_names,
            param_types=param_types,
            return_type=ret_type,
            can_fail=decl.can_fail,
            span=decl.span,
            module=normalized,
            requires=getattr(decl, "requires", []),
        )
        sigs.append(sig)

    _cache[normalized] = sigs
    return sigs


_type_cache: dict[str, dict[str, Type]] = {}


def load_stdlib_types(module_name: str) -> dict[str, Type]:
    """Load type definitions from a stdlib module.

    Returns a dict mapping type name -> resolved Type (AlgebraicType, RecordType, etc.).
    """
    normalized = module_name.lower()
    if normalized in _type_cache:
        return _type_cache[normalized]

    module = _parse_stdlib_module(normalized)
    if module is None:
        _type_cache[normalized] = {}
        return {}

    from prove.ast_nodes import (
        AlgebraicTypeDef,
        LookupTypeDef,
        ModuleDecl,
        RecordTypeDef,
    )

    # Pre-load dependency module types (UI is the base for event types)
    dep_types: dict[str, Type] = {}
    for dep_module in ("ui",):
        if dep_module != normalized:
            dep_types.update(load_stdlib_types(dep_module))

    types: dict[str, Type] = {}
    all_type_defs = []
    for decl in module.declarations:
        if isinstance(decl, ModuleDecl):
            all_type_defs.extend(decl.types)

    for td in all_type_defs:
        body = td.body
        if isinstance(body, AlgebraicTypeDef):
            variants: list[VariantInfo] = []
            for v in body.variants:
                # Check if variant name is a base type (inheritance)
                base = types.get(v.name) or dep_types.get(v.name)
                if base is not None and isinstance(base, AlgebraicType) and not v.fields:
                    variants.extend(base.variants)
                    continue
                vfields: dict[str, Type] = {}
                for f in v.fields:
                    vfields[f.name] = _resolve_type_expr(f.type_expr)
                variants.append(VariantInfo(v.name, vfields))
            types[td.name] = AlgebraicType(td.name, variants, [])
        elif isinstance(body, RecordTypeDef):
            fields: dict[str, Type] = {}
            for f in body.fields:
                fields[f.name] = _resolve_type_expr(f.type_expr)
            types[td.name] = RecordType(td.name, fields, [])
        elif isinstance(body, LookupTypeDef):
            # Lookup types are algebraic types with variant constructors
            variant_names = []
            seen: dict[str, None] = {}
            for entry in body.entries:
                if entry.variant not in seen:
                    seen[entry.variant] = None
                    variant_names.append(entry.variant)
            variants = [VariantInfo(name, {}) for name in variant_names]
            types[td.name] = AlgebraicType(td.name, variants, [])
        else:
            types[td.name] = PrimitiveType(td.name)

    _type_cache[normalized] = types
    return types


_lookup_cache: dict[str, dict[str, "LookupTypeDef"]] = {}


def load_stdlib_lookup_defs(module_name: str) -> dict[str, "LookupTypeDef"]:
    """Load LookupTypeDef AST nodes from a stdlib module.

    Returns a dict mapping type name -> LookupTypeDef for all lookup types.
    """
    from prove.ast_nodes import LookupTypeDef, ModuleDecl

    normalized = module_name.lower()
    if normalized in _lookup_cache:
        return _lookup_cache[normalized]

    module = _parse_stdlib_module(normalized)
    if module is None:
        _lookup_cache[normalized] = {}
        return {}

    result: dict[str, LookupTypeDef] = {}
    for decl in module.declarations:
        if isinstance(decl, ModuleDecl):
            for td in decl.types:
                if isinstance(td.body, LookupTypeDef):
                    result[td.name] = td.body

    _lookup_cache[normalized] = result
    return result


def stdlib_link_flags(module_name: str) -> list[str]:
    """Return linker flags required by a stdlib module."""
    return _STDLIB_LINK_FLAGS.get(module_name.lower(), [])


def stdlib_c_flags(module_name: str) -> list[str]:
    """Return compiler flags (include paths, defines) required by a stdlib module."""
    return _STDLIB_C_FLAGS.get(module_name.lower(), [])


def stdlib_prv_path(module_name: str) -> Path | None:
    """Return the .prv Path for any stdlib module (pure or binary).

    Returns None if the module is unknown.
    """
    key = module_name.lower()
    prv_rel = _STDLIB_MODULES.get(key)
    if prv_rel is None:
        return None
    stdlib_dir = Path(__file__).parent / "stdlib"
    return stdlib_dir / prv_rel


def load_stdlib_prv_source(module_name: str) -> str | None:
    """Return the .prv source text for a pure (non-binary) stdlib module.

    Uses importlib.resources so it works whether prove is installed on disk
    or loaded from a zip bundle embedded in a compiled binary.
    Returns None if the module is binary, unknown, or unreadable.
    """
    key = module_name.lower()
    prv_rel = _STDLIB_MODULES.get(key)
    if prv_rel is None:
        return None
    for mod, _verb, _func in _BINARY_C_MAP:
        if mod == key:
            return None
    pkg = importlib.resources.files("prove.stdlib")
    try:
        return pkg.joinpath(prv_rel).read_text(encoding="utf-8")
    except Exception:
        return None


def is_stdlib_module(module_name: str) -> bool:
    """Return True if module_name is a known stdlib module."""
    return module_name.lower() in _STDLIB_MODULES


# ── Auto-import support ──────────────────────────────────────────


@dataclass(frozen=True)
class ImportSuggestion:
    """A suggestion for auto-importing a stdlib function."""

    module: str  # display-cased: "System", "Text", etc.
    verb: str | None  # "outputs", "transforms", etc.
    name: str  # "println", "decode", etc.
    signature: str = ""  # "(path: String) String!" display string
    docstring: str = ""  # doc comment from function definition
    type_def: str = ""  # for types: multiline type definition


# Alias keys that should be skipped when building the index
_ALIAS_KEYS = {"io", "inputoutput", "list"}

_import_index: dict[str, list[ImportSuggestion]] | None = None


def _type_expr_display(te: object) -> str:
    """Convert an AST TypeExpr to a display string."""
    from prove.ast_nodes import GenericType, ModifiedType, SimpleType

    if isinstance(te, SimpleType):
        return te.name
    if isinstance(te, GenericType):
        args = ", ".join(_type_expr_display(a) for a in te.args)
        return f"{te.name}<{args}>"
    if isinstance(te, ModifiedType):
        return te.name
    return str(te)


def _function_signature_display(decl: object) -> str:
    """Build a display signature string like '(path: String) String!' from a FunctionDef."""
    from prove.ast_nodes import FunctionDef

    if not isinstance(decl, FunctionDef):
        return ""
    params = ", ".join(f"{p.name}: {_type_expr_display(p.type_expr)}" for p in decl.params)
    ret = _type_expr_display(decl.return_type) if decl.return_type else "Unit"
    fail = "!" if decl.can_fail else ""
    return f"({params}) {ret}{fail}"


def _parse_stdlib_module(module_name: str) -> Module | None:
    """Parse a stdlib .prv file and return the Module AST, or None."""
    normalized = module_name.lower()
    filename = _STDLIB_MODULES.get(normalized)
    if filename is None:
        return None

    pkg = importlib.resources.files("prove.stdlib")
    resource = pkg.joinpath(filename)

    try:
        source = resource.read_text(encoding="utf-8")
    except Exception:
        return None

    try:
        return parse(source, f"<stdlib:{module_name}>")
    except (CompileError, ValueError, IndexError):
        return None


def _format_type_def(td: TypeDef) -> str:
    """Format a type definition as a multiline string."""
    from prove import ast_nodes

    RecordTypeDef = getattr(ast_nodes, "RecordTypeDef", None)
    AlgebraicTypeDef = getattr(ast_nodes, "AlgebraicTypeDef", None)
    LookupTypeDef = getattr(ast_nodes, "LookupTypeDef", None)

    lines = [f"types {td.name}"]
    if td.type_params:
        lines[0] += f"<{', '.join(td.type_params)}>"

    # Handle RecordTypeDef (type X is field Type ...)
    if RecordTypeDef and isinstance(td.body, RecordTypeDef):
        lines[0] += " is"
        for field in td.body.fields:
            field_type = _type_expr_to_str(field.type_expr)
            lines.append(f"  {field.name} {field_type}")
    # Handle AlgebraicTypeDef (type X is A | B | C)
    elif AlgebraicTypeDef and isinstance(td.body, AlgebraicTypeDef):
        lines[0] += " is"
        for variant in td.body.variants:
            if hasattr(variant, "fields") and variant.fields:
                field_str = ", ".join(
                    f"{f.name} {_type_expr_to_str(f.type_expr)}" for f in variant.fields
                )
                lines.append(f"  {variant.name}({field_str})")
            else:
                lines.append(f"  {variant.name}")
    # Handle LookupTypeDef (type X is Y at Z)
    elif LookupTypeDef and isinstance(td.body, LookupTypeDef):
        lines[0] += (
            f" is {td.body.value_type.name} at {td.body.key_type.name if hasattr(td.body, 'key_type') else '??'}"  # noqa: E501
        )
        for entry in getattr(td.body, "entries", []):
            lines.append(f"  {entry.variant}")
    # Handle BinaryDef (simple alias type)
    elif hasattr(td.body, "span"):
        # BinaryDef or RefinementTypeDef - just show the type name
        pass
    else:
        # Unknown body type - just show name
        pass

    return "\n".join(lines)


def _type_expr_to_str(te: TypeExpr) -> str:
    """Convert a TypeExpr to string representation."""
    from prove import ast_nodes

    PrimitiveType = getattr(ast_nodes, "PrimitiveType", None)
    TypeParam = getattr(ast_nodes, "TypeParam", None)
    TypeApply = getattr(ast_nodes, "TypeApply", None)

    if PrimitiveType and isinstance(te, PrimitiveType):
        name: object = te.name
        return str(name)
    elif TypeParam and isinstance(te, TypeParam):
        name: object = te.name
        return str(name)
    elif TypeApply and isinstance(te, TypeApply):
        name: object = te.name
        return str(name)
    elif hasattr(te, "inner") and hasattr(te, "ok"):
        # Result type
        return f"Result<{_type_expr_to_str(te.ok)}, {_type_expr_to_str(te.err)}>"
    elif hasattr(te, "inner"):
        # Option, List, or Mutable
        inner = _type_expr_to_str(te.inner)
        if hasattr(te, "mutable"):
            return f"{inner}:Mutable"
        return f"Option<{inner}>" if not hasattr(te, "entries") else f"List<{inner}>"
    return str(te)


def build_import_index() -> dict[str, list[ImportSuggestion]]:
    """Return a reverse index: name → list of ImportSuggestion.

    Indexes both functions (with their verb) and types/variant constructors
    (with verb=None). Built once and cached at module level.
    """
    global _import_index
    if _import_index is not None:
        return _import_index

    from prove.ast_nodes import AlgebraicTypeDef, ConstantDef, FunctionDef, ModuleDecl

    index: dict[str, list[ImportSuggestion]] = {}
    for key, _filename in _STDLIB_MODULES.items():
        if key in _ALIAS_KEYS:
            continue
        display = _MODULE_DISPLAY_NAMES.get(key, key)
        module = _parse_stdlib_module(key)
        if module is None:
            continue

        # Collect all declarations, including those inside ModuleDecl
        all_decls: list[object] = []
        all_types: list[TypeDef] = []
        all_constants: list[ConstantDef] = []
        for decl in module.declarations:
            if isinstance(decl, ModuleDecl):
                all_decls.extend(decl.body)
                all_types.extend(decl.types)
                all_constants.extend(decl.constants)
            else:
                all_decls.append(decl)

        for decl in all_decls:  # type: ignore[assignment]
            if isinstance(decl, FunctionDef):
                suggestion = ImportSuggestion(
                    module=display,
                    verb=decl.verb,
                    name=decl.name,
                    signature=_function_signature_display(decl),
                    docstring=decl.doc_comment or "",
                )
                index.setdefault(decl.name, []).append(suggestion)

        for td in all_types:
            # Index the type name itself with the type definition
            type_def = _format_type_def(td)
            index.setdefault(td.name, []).append(
                ImportSuggestion(
                    module=display,
                    verb="types",
                    name=td.name,
                    type_def=type_def,
                ),
            )
            # Index variant constructors for algebraic types
            if AlgebraicTypeDef and isinstance(td.body, AlgebraicTypeDef):  # type: ignore[truthy-function]
                for variant in td.body.variants:
                    index.setdefault(variant.name, []).append(
                        ImportSuggestion(
                            module=display,
                            verb="types",
                            name=variant.name,
                        ),
                    )

        for cd in all_constants:
            index.setdefault(cd.name, []).append(
                ImportSuggestion(
                    module=display,
                    verb="constants",
                    name=cd.name,
                ),
            )

    _import_index = index
    return _import_index
