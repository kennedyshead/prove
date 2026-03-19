"""Build a registry of local (sibling) modules for cross-file compilation.

Three-phase approach:
  1. Parse all .prv files, collect locally-defined types
  2. Resolve sibling type imports (so cross-module type re-exports work)
  3. Build function signatures using complete type registries

The registry is handed to each Checker so it can resolve imports from
sibling modules.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from prove.errors import CompileError
from prove.lexer import Lexer
from prove.parser import Parser
from prove.source import Span
from prove.symbols import FunctionSignature
from prove.types import (
    BOOLEAN,
    BUILTINS,
    ERROR_TY,
    UNIT,
    AlgebraicType,
    ArrayType,
    GenericInstance,
    ListType,
    PrimitiveType,
    RecordType,
    RefinementType,
    Type,
    TypeVariable,
    VariantInfo,
)

_DUMMY = Span("<local>", 0, 0, 0, 0)


@dataclass
class LocalModuleInfo:
    """Resolved type and function information for a local module."""

    name: str
    types: dict[str, Type] = field(default_factory=dict)
    functions: list[FunctionSignature] = field(default_factory=list)


def build_module_registry(
    prv_files: list[Path],
) -> dict[str, LocalModuleInfo]:
    """Parse all .prv files and extract module-level type and function info.

    Returns a dict mapping module name -> LocalModuleInfo.

    Three phases:
      1. Parse & collect locally-defined types
      2. Resolve sibling type imports (re-exports)
      3. Build function signatures using complete type registries
    """
    from prove.ast_nodes import (
        AlgebraicTypeDef,
        FunctionDef,
        ModuleDecl,
    )

    registry: dict[str, LocalModuleInfo] = {}
    # Intermediate data needed across phases: mod_decl, type_registry, parsed module
    phase_data: dict[str, tuple[ModuleDecl, dict[str, Type], object]] = {}

    # --- Phase 1: Parse & collect local types ---
    for prv_file in prv_files:
        source = prv_file.read_text()
        filename = str(prv_file)

        try:
            tokens = Lexer(source, filename).lex()
            module = Parser(tokens, filename).parse()
        except (CompileError, Exception):
            continue

        # Find the module name from the ModuleDecl
        module_name: str | None = None
        mod_decl: ModuleDecl | None = None
        for decl in module.declarations:
            if isinstance(decl, ModuleDecl):
                module_name = decl.name
                mod_decl = decl
                break

        if module_name is None or mod_decl is None:
            continue

        info = LocalModuleInfo(name=module_name)

        # Resolve types from this module using a minimal type resolver
        type_registry: dict[str, Type] = dict(BUILTINS)
        # Also register generic builtins
        type_registry["Result"] = GenericInstance(
            "Result",
            [TypeVariable("Value"), TypeVariable("Error")],
        )
        type_registry["Option"] = GenericInstance(
            "Option",
            [TypeVariable("Value")],
        )
        type_registry["List"] = ListType(TypeVariable("Value"))
        type_registry["Error"] = PrimitiveType("Error")

        for td in mod_decl.types:
            resolved = _resolve_type_def(td, type_registry)
            if resolved is not None:
                type_registry[td.name] = resolved
                info.types[td.name] = resolved

                # Register variant constructors for algebraic types
                if isinstance(td.body, AlgebraicTypeDef) and isinstance(resolved, AlgebraicType):
                    for v in td.body.variants:
                        vfield_types = [
                            _resolve_type_expr_simple(f.type_expr, type_registry) for f in v.fields
                        ]
                        vsig = FunctionSignature(
                            verb=None,
                            name=v.name,
                            param_names=[f.name for f in v.fields],
                            param_types=vfield_types,
                            return_type=resolved,
                            can_fail=False,
                            span=v.span,
                            module=module_name.lower(),
                            requires=[],
                        )
                        info.functions.append(vsig)

        registry[module_name] = info
        phase_data[module_name] = (mod_decl, type_registry, module)

    # --- Phase 2: Resolve sibling type imports ---
    # Fixed-point loop: keep resolving until no new types propagate.
    # This handles transitive re-exports (A defines T, B imports T from A,
    # C imports T from B) regardless of iteration order.
    changed = True
    while changed:
        changed = False
        for module_name, (mod_decl, type_registry, _module) in phase_data.items():
            info = registry[module_name]
            for imp in mod_decl.imports:
                sibling = registry.get(imp.module)
                if sibling is None:
                    continue  # stdlib or unknown module — skip
                for item in imp.items:
                    # Type imports: explicit "types" verb or bare CamelCase name
                    if item.verb == "types" or (item.verb is None and item.name[:1].isupper()):
                        if item.name not in info.types:
                            imported_type = sibling.types.get(item.name)
                            if imported_type is not None:
                                type_registry[item.name] = imported_type
                                info.types[item.name] = imported_type
                                changed = True

    # --- Phase 3: Build function signatures ---
    for module_name, (_mod_decl, type_registry, module) in phase_data.items():  # type: ignore[assignment]
        info = registry[module_name]
        for decl in module.declarations:
            if isinstance(decl, FunctionDef):
                param_types = [
                    _resolve_type_expr_simple(p.type_expr, type_registry) for p in decl.params
                ]
                return_type = (
                    _resolve_type_expr_simple(decl.return_type, type_registry)
                    if decl.return_type
                    else (BOOLEAN if decl.verb == "validates" else UNIT)
                )
                sig = FunctionSignature(
                    verb=decl.verb,
                    name=decl.name,
                    param_names=[p.name for p in decl.params],
                    param_types=param_types,
                    return_type=return_type,
                    can_fail=decl.can_fail,
                    span=decl.span,
                    module=module_name.lower(),
                    requires=decl.requires,
                )
                info.functions.append(sig)

    return registry


def _resolve_type_def(
    td: object,
    type_registry: dict[str, Type],
) -> Type | None:
    """Resolve a TypeDef body into a Type using a minimal registry."""
    from prove.ast_nodes import (
        AlgebraicTypeDef,
        BinaryDef,
        RecordTypeDef,
        RefinementTypeDef,
        TypeDef,
    )

    if not isinstance(td, TypeDef):
        return None

    body = td.body
    type_params = tuple(td.type_params)

    if isinstance(body, RecordTypeDef):
        fields: dict[str, Type] = {}
        for f in body.fields:
            fields[f.name] = _resolve_type_expr_simple(f.type_expr, type_registry)
        return RecordType(td.name, fields, type_params)

    if isinstance(body, AlgebraicTypeDef):
        variants: list[VariantInfo] = []
        for v in body.variants:
            vfields: dict[str, Type] = {}
            for f in v.fields:
                vfields[f.name] = _resolve_type_expr_simple(f.type_expr, type_registry)
            variants.append(VariantInfo(v.name, vfields))
        return AlgebraicType(td.name, variants, type_params)

    if isinstance(body, RefinementTypeDef):
        base = _resolve_type_expr_simple(body.base_type, type_registry)
        return RefinementType(td.name, base, body.constraint)

    if isinstance(body, BinaryDef):
        return PrimitiveType(td.name)

    return None


def _resolve_type_expr_simple(
    type_expr: object,
    type_registry: dict[str, Type],
) -> Type:
    """Resolve a type expression using only a flat name registry."""
    from prove.ast_nodes import GenericType, ModifiedType, SimpleType

    if isinstance(type_expr, SimpleType):
        resolved = type_registry.get(type_expr.name)
        if resolved is not None:
            return resolved
        return PrimitiveType(type_expr.name)

    if isinstance(type_expr, GenericType):
        args = [_resolve_type_expr_simple(a, type_registry) for a in type_expr.args]
        if type_expr.name == "List" and len(args) == 1:
            return ListType(args[0])
        if type_expr.name == "Array" and len(args) == 1:
            return ArrayType(args[0])
        return GenericInstance(type_expr.name, args)

    if isinstance(type_expr, ModifiedType):
        mods = tuple((m.name, m.value) for m in type_expr.modifiers)
        return PrimitiveType(type_expr.name, mods)

    return ERROR_TY
