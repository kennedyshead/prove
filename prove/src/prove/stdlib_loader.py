"""Load stdlib module signatures from bundled .prv files."""

from __future__ import annotations

import importlib.resources

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

# Map stdlib module names to .prv filenames
# Keys are lowercase; lookup normalizes to lowercase.
_STDLIB_MODULES: dict[str, str] = {
    "io": "io.prv",
    "http": "http.prv",
    "json": "json.prv",
    "list_utils": "list_utils.prv",
    "string_utils": "string_utils.prv",
    "listutils": "list_utils.prv",
    "stringutils": "string_utils.prv",
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
    # Normalize: "Io" -> "io", "ListUtils" -> "listutils"
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

    from prove.ast_nodes import FunctionDef, GenericType, SimpleType

    sigs: list[FunctionSignature] = []
    for decl in module.declarations:
        if not isinstance(decl, FunctionDef):
            continue

        param_types = []
        param_names = []
        for p in decl.params:
            param_names.append(p.name)
            if hasattr(p.type_expr, 'name'):
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
            elif hasattr(decl.return_type, 'name'):
                ret_type = _resolve_type_name(decl.return_type.name)

        sig = FunctionSignature(
            verb=decl.verb,
            name=decl.name,
            param_names=param_names,
            param_types=param_types,
            return_type=ret_type,
            can_fail=decl.can_fail,
            span=_DUMMY,
        )
        sigs.append(sig)

    _cache[normalized] = sigs
    return sigs


def available_modules() -> list[str]:
    """Return names of all available stdlib modules."""
    return list(_STDLIB_MODULES.keys())
