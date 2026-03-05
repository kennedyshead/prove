"""Load stdlib module signatures from bundled .prv files."""

from __future__ import annotations

import importlib.resources
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from prove.ast_nodes import Module

from prove.lexer import Lexer
from prove.parser import Parser
from prove.source import Span
from prove.symbols import FunctionSignature
from prove.types import (
    BOOLEAN,
    CHARACTER,
    ERROR_TY,
    INTEGER,
    STRING,
    UNIT,
    GenericInstance,
    ListType,
    PrimitiveType,
    TypeVariable,
)

_DUMMY = Span("<stdlib>", 0, 0, 0, 0)

# Binary function → C runtime function mapping
# Key: (module_key, verb, function_name) → C function name
_BINARY_C_MAP: dict[tuple[str, str | None, str], str] = {
    # InputOutput
    ("io", "outputs", "console"): "prove_println",
    ("io", "inputs", "console"): "prove_readln",
    ("io", "validates", "console"): "prove_io_console_validates",
    ("io", "inputs", "file"): "prove_file_read",
    ("io", "outputs", "file"): "prove_file_write",
    ("io", "validates", "file"): "prove_io_file_validates",
    ("io", "inputs", "system"): "prove_io_system_inputs",
    ("io", "outputs", "system"): "prove_io_system_outputs",
    ("io", "validates", "system"): "prove_io_system_validates",
    ("io", "inputs", "dir"): "prove_io_dir_inputs",
    ("io", "outputs", "dir"): "prove_io_dir_outputs",
    ("io", "validates", "dir"): "prove_io_dir_validates",
    ("io", "inputs", "process"): "prove_io_process_inputs",
    ("io", "validates", "process"): "prove_io_process_validates",
    ("inputoutput", "outputs", "console"): "prove_println",
    ("inputoutput", "inputs", "console"): "prove_readln",
    ("inputoutput", "validates", "console"): "prove_io_console_validates",
    ("inputoutput", "inputs", "file"): "prove_file_read",
    ("inputoutput", "outputs", "file"): "prove_file_write",
    ("inputoutput", "validates", "file"): "prove_io_file_validates",
    ("inputoutput", "inputs", "system"): "prove_io_system_inputs",
    ("inputoutput", "outputs", "system"): "prove_io_system_outputs",
    ("inputoutput", "validates", "system"): "prove_io_system_validates",
    ("inputoutput", "inputs", "dir"): "prove_io_dir_inputs",
    ("inputoutput", "outputs", "dir"): "prove_io_dir_outputs",
    ("inputoutput", "validates", "dir"): "prove_io_dir_validates",
    ("inputoutput", "inputs", "process"): "prove_io_process_inputs",
    ("inputoutput", "validates", "process"): "prove_io_process_validates",
    # Character
    ("character", "validates", "alpha"): "prove_character_alpha",
    ("character", "validates", "digit"): "prove_character_digit",
    ("character", "validates", "alnum"): "prove_character_alnum",
    ("character", "validates", "upper"): "prove_character_upper",
    ("character", "validates", "lower"): "prove_character_lower",
    ("character", "validates", "space"): "prove_character_space",
    ("character", "reads", "at"): "prove_character_at",
    # Text
    ("text", "reads", "length"): "prove_text_length",
    ("text", "transforms", "slice"): "prove_text_slice",
    ("text", "validates", "starts"): "prove_text_starts_with",
    ("text", "validates", "ends"): "prove_text_ends_with",
    ("text", "validates", "contains"): "prove_text_contains",
    ("text", "reads", "index"): "prove_text_index_of",
    ("text", "transforms", "split"): "prove_text_split",
    ("text", "transforms", "join"): "prove_text_join",
    ("text", "transforms", "trim"): "prove_text_trim",
    ("text", "transforms", "lower"): "prove_text_to_lower",
    ("text", "transforms", "upper"): "prove_text_to_upper",
    ("text", "transforms", "replace"): "prove_text_replace",
    ("text", "transforms", "repeat"): "prove_text_repeat",
    ("text", "creates", "builder"): "prove_text_builder",
    ("text", "transforms", "string"): "prove_text_write",
    ("text", "transforms", "char"): "prove_text_write_char",
    ("text", "reads", "build"): "prove_text_build",
    # Table
    ("table", "creates", "new"): "prove_table_new",
    ("table", "validates", "has"): "prove_table_has",
    ("table", "transforms", "add"): "prove_table_add",
    ("table", "reads", "get"): "prove_table_get",
    ("table", "transforms", "remove"): "prove_table_remove",
    ("table", "reads", "keys"): "prove_table_keys",
    ("table", "reads", "values"): "prove_table_values",
    ("table", "reads", "length"): "prove_table_length",
    # Pattern
    ("pattern", "validates", "test"): "prove_pattern_match",
    ("pattern", "reads", "search"): "prove_pattern_search",
    ("pattern", "reads", "find_all"): "prove_pattern_find_all",
    ("pattern", "transforms", "replace"): "prove_pattern_replace",
    ("pattern", "transforms", "split"): "prove_pattern_split",
    ("pattern", "reads", "text"): "prove_pattern_text",
    ("pattern", "reads", "start"): "prove_pattern_start",
    ("pattern", "reads", "end"): "prove_pattern_end",
    # Error
    ("error", "validates", "ok"): "prove_error_ok",
    ("error", "validates", "err"): "prove_error_err",
    # Path
    ("path", "transforms", "join"): "prove_path_join",
    ("path", "reads", "parent"): "prove_path_parent",
    ("path", "reads", "name"): "prove_path_name",
    ("path", "reads", "stem"): "prove_path_stem",
    ("path", "reads", "extension"): "prove_path_extension",
    ("path", "validates", "absolute"): "prove_path_absolute",
    ("path", "transforms", "normalize"): "prove_path_normalize",
    # Format
    ("format", "transforms", "pad_left"): "prove_format_pad_left",
    ("format", "transforms", "pad_right"): "prove_format_pad_right",
    ("format", "transforms", "center"): "prove_format_center",
    ("format", "transforms", "hex"): "prove_format_hex",
    ("format", "transforms", "bin"): "prove_format_binary",
    ("format", "transforms", "octal"): "prove_format_octal",
    ("format", "transforms", "decimal"): "prove_format_decimal",
    # List (non-overloaded, generic operations)
    ("list", "reads", "length"): "prove_list_ops_length",
    ("list", "validates", "empty"): "prove_list_ops_empty",
    ("list", "transforms", "slice"): "prove_list_ops_slice",
    ("list", "transforms", "reverse"): "prove_list_ops_reverse",
    ("list", "creates", "range"): "prove_list_ops_range",
    # Convert (non-overloaded)
    ("convert", "reads", "code"): "prove_convert_code",
    # Math (non-overloaded, Float-only functions)
    ("math", "reads", "sqrt"): "prove_math_sqrt",
    ("math", "reads", "pow"): "prove_math_pow",
    ("math", "reads", "floor"): "prove_math_floor",
    ("math", "reads", "ceil"): "prove_math_ceil",
    ("math", "reads", "round"): "prove_math_round",
    ("math", "reads", "log"): "prove_math_log",
    # Parse
    ("parse", "creates", "toml"): "prove_parse_toml",
    ("parse", "reads", "toml"): "prove_emit_toml",
    ("parse", "creates", "json"): "prove_parse_json",
    ("parse", "reads", "json"): "prove_emit_json",
    ("parse", "reads", "tag"): "prove_value_tag",
    ("parse", "reads", "text"): "prove_value_as_text",
    ("parse", "reads", "number"): "prove_value_as_number",
    ("parse", "reads", "decimal"): "prove_value_as_decimal",
    ("parse", "reads", "bool"): "prove_value_as_bool",
    ("parse", "reads", "array"): "prove_value_as_array",
    ("parse", "reads", "object"): "prove_value_as_object",
    ("parse", "validates", "text"): "prove_value_is_text",
    ("parse", "validates", "number"): "prove_value_is_number",
    ("parse", "validates", "decimal"): "prove_value_is_decimal",
    ("parse", "validates", "bool"): "prove_value_is_bool",
    ("parse", "validates", "array"): "prove_value_is_array",
    ("parse", "validates", "object"): "prove_value_is_object",
    ("parse", "validates", "null"): "prove_value_is_null",
    ("parse", "validates", "value"): "prove_validates_value",
    ("parse", "validates", "json"): "prove_validates_json",
    ("parse", "validates", "toml"): "prove_validates_toml",
    ("parse", "creates", "value"): "prove_creates_value",
}


# Overloaded binary functions: same (module, verb, name) but different first param type.
# Key: (module_key, verb, function_name, first_param_type_name) → C function name
_BINARY_C_OVERLOADS: dict[tuple[str, str | None, str, str], str] = {
    ("text", "reads", "length", "Builder"): "prove_text_builder_length",
    # Error: Option overloads
    ("error", "validates", "some", "Option<Integer>"): "prove_error_some_int",
    ("error", "validates", "some", "Option<String>"): "prove_error_some_str",
    ("error", "validates", "none", "Option<Integer>"): "prove_error_none_int",
    ("error", "validates", "none", "Option<String>"): "prove_error_none_str",
    ("error", "reads", "unwrap_or", "Option<Integer>"): "prove_error_unwrap_or_int",
    ("error", "reads", "unwrap_or", "Option<String>"): "prove_error_unwrap_or_str",
    # List: type-specific overloads
    ("list", "reads", "first", "List<Integer>"): "prove_list_ops_first_int",
    ("list", "reads", "first", "List<String>"): "prove_list_ops_first_str",
    ("list", "reads", "last", "List<Integer>"): "prove_list_ops_last_int",
    ("list", "reads", "last", "List<String>"): "prove_list_ops_last_str",
    ("list", "validates", "contains", "List<Integer>"): "prove_list_ops_contains_int",
    ("list", "validates", "contains", "List<String>"): "prove_list_ops_contains_str",
    ("list", "reads", "index", "List<Integer>"): "prove_list_ops_index_int",
    ("list", "reads", "index", "List<String>"): "prove_list_ops_index_str",
    ("list", "transforms", "sort", "List<Integer>"): "prove_list_ops_sort_int",
    ("list", "transforms", "sort", "List<String>"): "prove_list_ops_sort_str",
    # Convert: overloaded functions
    ("convert", "creates", "integer", "String"): "prove_convert_integer_str",
    ("convert", "creates", "integer", "Float"): "prove_convert_integer_float",
    ("convert", "creates", "float", "String"): "prove_convert_float_str",
    ("convert", "creates", "float", "Integer"): "prove_convert_float_int",
    ("convert", "reads", "string", "Integer"): "prove_convert_string_int",
    ("convert", "reads", "string", "Float"): "prove_convert_string_float",
    ("convert", "reads", "string", "Boolean"): "prove_convert_string_bool",
    ("convert", "creates", "character", "Integer"): "prove_convert_character",
    # Math: Integer vs Float overloads
    ("math", "reads", "abs", "Integer"): "prove_math_abs_int",
    ("math", "reads", "abs", "Float"): "prove_math_abs_float",
    ("math", "reads", "min", "Integer"): "prove_math_min_int",
    ("math", "reads", "min", "Float"): "prove_math_min_float",
    ("math", "reads", "max", "Integer"): "prove_math_max_int",
    ("math", "reads", "max", "Float"): "prove_math_max_float",
    ("math", "transforms", "clamp", "Integer"): "prove_math_clamp_int",
    ("math", "transforms", "clamp", "Float"): "prove_math_clamp_float",
}


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


# Map stdlib module names to .prv filenames
# Keys are lowercase; lookup normalizes to lowercase.
_STDLIB_MODULES: dict[str, str] = {
    "io": "input_output.prv",
    "inputoutput": "input_output.prv",
    "character": "character.prv",
    "text": "text.prv",
    "table": "table.prv",
    "parse": "parse.prv",
    "math": "math.prv",
    "convert": "convert.prv",
    "list": "list.prv",
    "format": "format.prv",
    "path": "path.prv",
    "error": "error.prv",
    "pattern": "pattern.prv",
}

# Cache loaded signatures
_cache: dict[str, list[FunctionSignature]] = {}


_KNOWN_TYPES = {
    "Integer": INTEGER,
    "String": STRING,
    "Boolean": BOOLEAN,
    "Character": CHARACTER,
    "Unit": UNIT,
    "Float": PrimitiveType("Float"),
    "Match": PrimitiveType("Match"),
}


def _resolve_type_name(name: str) -> PrimitiveType | ListType | GenericInstance | TypeVariable:
    """Resolve a simple type name to a Type.

    Single uppercase letters that are not known types (e.g. V, T, E)
    are treated as type variables for generic signatures.
    """
    if name in _KNOWN_TYPES:
        return _KNOWN_TYPES[name]
    if len(name) == 1 and name.isupper():
        return TypeVariable(name)
    return PrimitiveType(name)


def load_stdlib(module_name: str) -> list[FunctionSignature]:
    """Load function signatures from a stdlib module.

    Returns an empty list if the module is not found.
    """
    # Normalize: "InputOutput" -> "inputoutput"
    normalized = module_name.lower()

    if normalized in _cache:
        return _cache[normalized]

    filename = _STDLIB_MODULES.get(normalized)
    if filename is None:
        return []

    pkg = importlib.resources.files("prove.stdlib")
    resource = pkg.joinpath(filename)

    try:
        with importlib.resources.as_file(resource) as path:
            source = path.read_text()
    except (FileNotFoundError, TypeError):
        return []

    # Parse the stdlib file to extract function declarations
    try:
        tokens = Lexer(source, f"<stdlib:{module_name}>").lex()
        module = Parser(tokens, f"<stdlib:{module_name}>").parse()
    except Exception:
        return []

    from prove.ast_nodes import FunctionDef, GenericType, ModuleDecl, SimpleType

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
            if hasattr(p.type_expr, "name"):
                pt = _resolve_type_name(p.type_expr.name)
                # Handle generic types like List<Integer>
                if isinstance(p.type_expr, GenericType):
                    args = []
                    for a in p.type_expr.args:
                        if isinstance(a, SimpleType):
                            args.append(_resolve_type_name(a.name))
                        else:
                            args.append(TypeVariable("T"))
                    if p.type_expr.name == "List" and len(args) == 1:
                        pt = ListType(args[0])
                    else:
                        pt = GenericInstance(p.type_expr.name, args)
                param_types.append(pt)
            else:
                param_types.append(ERROR_TY)

        # Resolve return type
        ret_type = BOOLEAN if decl.verb == "validates" else UNIT
        if decl.return_type is not None:
            if isinstance(decl.return_type, GenericType):
                args = []
                for a in decl.return_type.args:
                    if isinstance(a, SimpleType):
                        args.append(_resolve_type_name(a.name))
                    else:
                        args.append(TypeVariable("T"))
                if decl.return_type.name == "List" and len(args) == 1:
                    ret_type = ListType(args[0])
                else:
                    ret_type = GenericInstance(decl.return_type.name, args)
            elif hasattr(decl.return_type, "name"):
                ret_type = _resolve_type_name(decl.return_type.name)

        sig = FunctionSignature(
            verb=decl.verb,
            name=decl.name,
            param_names=param_names,
            param_types=param_types,
            return_type=ret_type,
            can_fail=decl.can_fail,
            span=_DUMMY,
            module=normalized,
            requires=getattr(decl, "requires", []),
        )
        sigs.append(sig)

    _cache[normalized] = sigs
    return sigs


# Stdlib modules that require extra linker flags
_STDLIB_LINK_FLAGS: dict[str, list[str]] = {
    "math": ["-lm"],
}


def stdlib_link_flags(module_name: str) -> list[str]:
    """Return linker flags required by a stdlib module."""
    return _STDLIB_LINK_FLAGS.get(module_name.lower(), [])


def is_stdlib_module(module_name: str) -> bool:
    """Return True if module_name is a known stdlib module."""
    return module_name.lower() in _STDLIB_MODULES


def available_modules() -> list[str]:
    """Return names of all available stdlib modules."""
    return list(_STDLIB_MODULES.keys())


# ── Auto-import support ──────────────────────────────────────────


@dataclass(frozen=True)
class ImportSuggestion:
    """A suggestion for auto-importing a stdlib function."""

    module: str  # display-cased: "InputOutput", etc.
    verb: str | None  # "outputs", "transforms", etc.
    name: str  # "println", "decode", etc.
    signature: str = ""  # "(path: String) String!" display string


# Canonical module keys → display names used in `with <Name> use ...`
_MODULE_DISPLAY_NAMES: dict[str, str] = {
    "io": "InputOutput",
    "inputoutput": "InputOutput",
    "character": "Character",
    "text": "Text",
    "table": "Table",
    "parse": "Parse",
    "math": "Math",
    "convert": "Convert",
    "list": "List",
    "format": "Format",
    "path": "Path",
    "error": "Error",
    "pattern": "Pattern",
}

# Alias keys that should be skipped when building the index
_ALIAS_KEYS = {"inputoutput"}

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
        with importlib.resources.as_file(resource) as path:
            source = path.read_text()
    except (FileNotFoundError, TypeError):
        return None

    try:
        tokens = Lexer(source, f"<stdlib:{module_name}>").lex()
        return Parser(tokens, f"<stdlib:{module_name}>").parse()
    except Exception:
        return None


def build_import_index() -> dict[str, list[ImportSuggestion]]:
    """Return a reverse index: name → list of ImportSuggestion.

    Indexes both functions (with their verb) and types/variant constructors
    (with verb=None). Built once and cached at module level.
    """
    global _import_index
    if _import_index is not None:
        return _import_index

    from prove.ast_nodes import AlgebraicTypeDef, FunctionDef, ModuleDecl, TypeDef

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
        for decl in module.declarations:
            if isinstance(decl, ModuleDecl):
                all_decls.extend(decl.body)
                all_types.extend(decl.types)
            else:
                all_decls.append(decl)

        for decl in all_decls:
            if isinstance(decl, FunctionDef):
                suggestion = ImportSuggestion(
                    module=display,
                    verb=decl.verb,
                    name=decl.name,
                    signature=_function_signature_display(decl),
                )
                index.setdefault(decl.name, []).append(suggestion)

        for td in all_types:
            # Index the type name itself
            index.setdefault(td.name, []).append(
                ImportSuggestion(module=display, verb="types", name=td.name),
            )
            # Index variant constructors for algebraic types
            if isinstance(td.body, AlgebraicTypeDef):
                for variant in td.body.variants:
                    index.setdefault(variant.name, []).append(
                        ImportSuggestion(
                            module=display,
                            verb="types",
                            name=variant.name,
                        ),
                    )

    _import_index = index
    return _import_index


def _reset_import_index() -> None:
    """Clear the cached import index (used by tests)."""
    global _import_index
    _import_index = None
