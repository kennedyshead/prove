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
}


# Overloaded binary functions: same (module, verb, name) but different first param type.
# Key: (module_key, verb, function_name, first_param_type_name) → C function name
_BINARY_C_OVERLOADS: dict[tuple[str, str | None, str, str], str] = {
    ("text", "reads", "length", "Builder"): "prove_text_builder_length",
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
        ret_type = UNIT
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
        )
        sigs.append(sig)

    _cache[normalized] = sigs
    return sigs


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


# Canonical module keys → display names used in `with <Name> use ...`
_MODULE_DISPLAY_NAMES: dict[str, str] = {
    "io": "InputOutput",
    "inputoutput": "InputOutput",
    "character": "Character",
    "text": "Text",
    "table": "Table",
    "parse": "Parse",
}

# Alias keys that should be skipped when building the index
_ALIAS_KEYS = {"inputoutput"}

_import_index: dict[str, list[ImportSuggestion]] | None = None


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
