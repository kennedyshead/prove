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
    ("io", "outputs", "console"): "prove_println",
    ("io", "inputs", "console"): "prove_readln",
    ("io", "inputs", "file"): "prove_file_read",
    ("io", "outputs", "file"): "prove_file_write",
    ("inputoutput", "outputs", "console"): "prove_println",
    ("inputoutput", "inputs", "console"): "prove_readln",
    ("inputoutput", "inputs", "file"): "prove_file_read",
    ("inputoutput", "outputs", "file"): "prove_file_write",
}


def binary_c_name(module: str, verb: str | None, name: str) -> str | None:
    """Look up the C runtime function for a binary stdlib function."""
    return _BINARY_C_MAP.get((module.lower(), verb, name))

# Map stdlib module names to .prv filenames
# Keys are lowercase; lookup normalizes to lowercase.
_STDLIB_MODULES: dict[str, str] = {
    "io": "input_output.prv",
    "inputoutput": "input_output.prv",
}

# Cache loaded signatures
_cache: dict[str, list[FunctionSignature]] = {}


def _resolve_type_name(name: str) -> PrimitiveType | ListType | GenericInstance | TypeVariable:
    """Resolve a simple type name to a Type."""
    mapping = {
        "Integer": INTEGER,
        "String": STRING,
        "Boolean": BOOLEAN,
        "Unit": UNIT,
    }
    if name in mapping:
        return mapping[name]
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
