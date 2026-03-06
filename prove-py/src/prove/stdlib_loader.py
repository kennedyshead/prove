"""Load stdlib module signatures from bundled .prv files."""

from __future__ import annotations

import importlib.resources
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from prove.ast_nodes import Module, TypeDef, TypeExpr

from prove.errors import CompileError
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

# ── Per-module registration ──────────────────────────────────────

# Populated by _register_module() calls below
_BINARY_C_MAP: dict[tuple[str, str | None, str], str] = {}
_BINARY_C_OVERLOADS: dict[tuple[str, str | None, str, str], str] = {}
_STDLIB_MODULES: dict[str, str] = {}
_STDLIB_LINK_FLAGS: dict[str, list[str]] = {}
_MODULE_DISPLAY_NAMES: dict[str, str] = {}


def _register_module(
    name: str,
    *,
    display: str,
    prv_file: str,
    c_map: dict[tuple[str, str], str] | None = None,
    overloads: dict[tuple[str, str, str], str] | None = None,
    link_flags: list[str] | None = None,
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

    if link_flags:
        _STDLIB_LINK_FLAGS[key] = link_flags

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
    "inputoutput",
    display="InputOutput",
    prv_file="input_output.prv",
    aliases=["io"],
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
    },
)

_register_module(
    "character",
    display="Character",
    prv_file="character.prv",
    c_map={
        ("validates", "alpha"): "prove_character_alpha",
        ("validates", "digit"): "prove_character_digit",
        ("validates", "alnum"): "prove_character_alnum",
        ("validates", "upper"): "prove_character_upper",
        ("validates", "lower"): "prove_character_lower",
        ("validates", "space"): "prove_character_space",
        ("reads", "at"): "prove_character_at",
    },
)

_register_module(
    "text",
    display="Text",
    prv_file="text.prv",
    c_map={
        ("reads", "length"): "prove_text_length",
        ("transforms", "slice"): "prove_text_slice",
        ("validates", "starts"): "prove_text_starts_with",
        ("validates", "ends"): "prove_text_ends_with",
        ("validates", "contains"): "prove_text_contains",
        ("reads", "index"): "prove_text_index_of",
        ("transforms", "split"): "prove_text_split",
        ("transforms", "join"): "prove_text_join",
        ("transforms", "trim"): "prove_text_trim",
        ("transforms", "lower"): "prove_text_to_lower",
        ("transforms", "upper"): "prove_text_to_upper",
        ("transforms", "replace"): "prove_text_replace",
        ("transforms", "repeat"): "prove_text_repeat",
        ("creates", "builder"): "prove_text_builder",
        ("transforms", "string"): "prove_text_write",
        ("transforms", "char"): "prove_text_write_char",
        ("reads", "build"): "prove_text_build",
    },
    overloads={
        ("reads", "length", "Builder"): "prove_text_builder_length",
    },
)

_register_module(
    "table",
    display="Table",
    prv_file="table.prv",
    c_map={
        ("creates", "new"): "prove_table_new",
        ("validates", "has"): "prove_table_has",
        ("transforms", "add"): "prove_table_add",
        ("reads", "get"): "prove_table_get",
        ("transforms", "remove"): "prove_table_remove",
        ("reads", "keys"): "prove_table_keys",
        ("reads", "values"): "prove_table_values",
        ("reads", "length"): "prove_table_length",
    },
)

_register_module(
    "pattern",
    display="Pattern",
    prv_file="pattern.prv",
    c_map={
        ("validates", "test"): "prove_pattern_match",
        ("reads", "search"): "prove_pattern_search",
        ("reads", "find_all"): "prove_pattern_find_all",
        ("transforms", "replace"): "prove_pattern_replace",
        ("transforms", "split"): "prove_pattern_split",
        ("reads", "text"): "prove_pattern_text",
        ("reads", "start"): "prove_pattern_start",
        ("reads", "end"): "prove_pattern_end",
    },
)

_register_module(
    "error",
    display="Error",
    prv_file="error.prv",
    c_map={
        ("validates", "ok"): "prove_error_ok",
        ("validates", "err"): "prove_error_err",
    },
    overloads={
        ("validates", "some", "Option<Integer>"): "prove_error_some_int",
        ("validates", "some", "Option<String>"): "prove_error_some_str",
        ("validates", "none", "Option<Integer>"): "prove_error_none_int",
        ("validates", "none", "Option<String>"): "prove_error_none_str",
        ("reads", "unwrap_or", "Option<Integer>"): "prove_error_unwrap_or_int",
        ("reads", "unwrap_or", "Option<String>"): "prove_error_unwrap_or_str",
    },
)

_register_module(
    "path",
    display="Path",
    prv_file="path.prv",
    c_map={
        ("transforms", "join"): "prove_path_join",
        ("reads", "parent"): "prove_path_parent",
        ("reads", "name"): "prove_path_name",
        ("reads", "stem"): "prove_path_stem",
        ("reads", "extension"): "prove_path_extension",
        ("validates", "absolute"): "prove_path_absolute",
        ("transforms", "normalize"): "prove_path_normalize",
    },
)

_register_module(
    "format",
    display="Format",
    prv_file="format.prv",
    c_map={
        ("transforms", "pad_left"): "prove_format_pad_left",
        ("transforms", "pad_right"): "prove_format_pad_right",
        ("transforms", "center"): "prove_format_center",
        ("transforms", "hex"): "prove_format_hex",
        ("transforms", "bin"): "prove_format_binary",
        ("transforms", "octal"): "prove_format_octal",
        ("transforms", "decimal"): "prove_format_decimal",
    },
)

_register_module(
    "list",
    display="List",
    prv_file="list.prv",
    c_map={
        ("reads", "length"): "prove_list_ops_length",
        ("validates", "empty"): "prove_list_ops_empty",
        ("transforms", "slice"): "prove_list_ops_slice",
        ("transforms", "reverse"): "prove_list_ops_reverse",
        ("creates", "range"): "prove_list_ops_range",
    },
    overloads={
        ("reads", "first", "List<Integer>"): "prove_list_ops_first_int",
        ("reads", "first", "List<String>"): "prove_list_ops_first_str",
        ("reads", "last", "List<Integer>"): "prove_list_ops_last_int",
        ("reads", "last", "List<String>"): "prove_list_ops_last_str",
        ("validates", "contains", "List<Integer>"): "prove_list_ops_contains_int",
        ("validates", "contains", "List<String>"): "prove_list_ops_contains_str",
        ("reads", "index", "List<Integer>"): "prove_list_ops_index_int",
        ("reads", "index", "List<String>"): "prove_list_ops_index_str",
        ("transforms", "sort", "List<Integer>"): "prove_list_ops_sort_int",
        ("transforms", "sort", "List<String>"): "prove_list_ops_sort_str",
    },
)

_register_module(
    "types",
    display="Types",
    prv_file="types.prv",
    c_map={
        ("reads", "code"): "prove_convert_code",
    },
    overloads={
        ("creates", "integer", "String"): "prove_convert_integer_str",
        ("creates", "integer", "Float"): "prove_convert_integer_float",
        ("creates", "float", "String"): "prove_convert_float_str",
        ("creates", "float", "Integer"): "prove_convert_float_int",
        ("reads", "string", "Integer"): "prove_convert_string_int",
        ("reads", "string", "Float"): "prove_convert_string_float",
        ("reads", "string", "Boolean"): "prove_convert_string_bool",
        ("creates", "character", "Integer"): "prove_convert_character",
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
        ("reads", "floor"): "prove_math_floor",
        ("reads", "ceil"): "prove_math_ceil",
        ("reads", "round"): "prove_math_round",
        ("reads", "log"): "prove_math_log",
    },
    overloads={
        ("reads", "abs", "Integer"): "prove_math_abs_int",
        ("reads", "abs", "Float"): "prove_math_abs_float",
        ("reads", "min", "Integer"): "prove_math_min_int",
        ("reads", "min", "Float"): "prove_math_min_float",
        ("reads", "max", "Integer"): "prove_math_max_int",
        ("reads", "max", "Float"): "prove_math_max_float",
        ("transforms", "clamp", "Integer"): "prove_math_clamp_int",
        ("transforms", "clamp", "Float"): "prove_math_clamp_float",
    },
)

_register_module(
    "parse",
    display="Parse",
    prv_file="parse.prv",
    c_map={
        ("creates", "toml"): "prove_parse_toml",
        ("reads", "toml"): "prove_emit_toml",
        ("creates", "json"): "prove_parse_json",
        ("reads", "json"): "prove_emit_json",
        ("reads", "tag"): "prove_value_tag",
        ("reads", "text"): "prove_value_as_text",
        ("reads", "number"): "prove_value_as_number",
        ("reads", "decimal"): "prove_value_as_decimal",
        ("reads", "bool"): "prove_value_as_bool",
        ("reads", "array"): "prove_value_as_array",
        ("reads", "object"): "prove_value_as_object",
        ("validates", "text"): "prove_value_is_text",
        ("validates", "number"): "prove_value_is_number",
        ("validates", "decimal"): "prove_value_is_decimal",
        ("validates", "bool"): "prove_value_is_bool",
        ("validates", "array"): "prove_value_is_array",
        ("validates", "object"): "prove_value_is_object",
        ("validates", "null"): "prove_value_is_null",
        ("validates", "value"): "prove_validates_value",
        ("validates", "json"): "prove_validates_json",
        ("validates", "toml"): "prove_validates_toml",
        ("creates", "value"): "prove_creates_value",
    },
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
    except (CompileError, ValueError, IndexError):
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
    docstring: str = ""  # doc comment from function definition
    type_def: str = ""  # for types: multiline type definition


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
            f" is {td.body.value_type.name} at {td.body.key_type.name if hasattr(td.body, 'key_type') else '??'}"
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

    from prove.ast_nodes import AlgebraicTypeDef, FunctionDef, ModuleDecl

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
            if AlgebraicTypeDef and isinstance(td.body, AlgebraicTypeDef):
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
