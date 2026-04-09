"""Load installed packages for use by the checker and emitter.

Provides two access modes:
  - Fast path (checker): reads exports table only, no AST deserialization.
  - Slow path (emitter): full AST deserialization for C code generation.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from prove.ast_nodes import Module
from prove.lockfile import Lockfile
from prove.package import ExportEntry, load_package_module, read_package
from prove.registry import cache_dir
from prove.symbols import FunctionSignature, SymbolTable
from prove.types import (
    AlgebraicType,
    PrimitiveType,
    RecordType,
    Type,
    VariantInfo,
)


@dataclass
class PackageModuleInfo:
    """Checker-facing view of a package module (no AST deserialization)."""

    package_name: str
    package_version: str
    module_name: str
    types: dict[str, Type] = field(default_factory=dict)
    functions: list[FunctionSignature] = field(default_factory=list)
    constants: dict[str, Type] = field(default_factory=dict)
    pkg_path: Path | None = None


def _resolve_type_name(name: str) -> Type:
    """Resolve a type name string from exports to a Type object."""
    from prove.types import BUILTINS, GenericInstance

    if not name or name == "Unit":
        from prove.types import UNIT

        return UNIT

    # Check builtins
    if name in BUILTINS:
        return BUILTINS[name]

    # Handle generic types like Option<String>, List<Integer>
    if "<" in name and name.endswith(">"):
        base = name[: name.index("<")]
        inner = name[name.index("<") + 1 : -1]
        args = [_resolve_type_name(a.strip()) for a in inner.split(",")]
        return GenericInstance(base, args)

    # Fallback: treat as a named type (record/algebraic/refinement)
    return PrimitiveType(name)


def _build_functions_from_exports(
    exports: list[ExportEntry],
    module_name: str,
) -> list[FunctionSignature]:
    """Convert export entries to FunctionSignatures for the checker."""
    from prove.source import Span
    from prove.types import UNIT

    dummy_span = Span("<package>", 0, 0, 0, 0)
    sigs = []

    for exp in exports:
        if exp.kind != "function":
            continue

        params = json.loads(exp.params) if exp.params else []
        param_names = [p["name"] for p in params]
        param_types = [_resolve_type_name(p["type"]) for p in params]
        return_type = _resolve_type_name(exp.return_type) if exp.return_type else UNIT

        sigs.append(
            FunctionSignature(
                verb=exp.verb,
                name=exp.name,
                param_names=param_names,
                param_types=param_types,
                return_type=return_type,
                can_fail=exp.can_fail,
                span=dummy_span,
                module=module_name.lower(),
                doc_comment=exp.doc,
            )
        )

    return sigs


def _build_types_from_exports(
    exports: list[ExportEntry],
) -> dict[str, Type]:
    """Convert type export entries to resolved Types for the checker."""
    types: dict[str, Type] = {}

    for exp in exports:
        if exp.kind != "type":
            continue

        # The params field contains type body info:
        # For algebraic: "Red|Green|Blue" (variant names)
        # For record: "x,y" (field names)
        # For lookup: "lookup"
        body_info = exp.params or ""

        if "|" in body_info:
            # Algebraic type
            variant_names = body_info.split("|")
            variants = [VariantInfo(name=vn) for vn in variant_names]
            types[exp.name] = AlgebraicType(name=exp.name, variants=variants)
        elif body_info == "lookup":
            # Lookup type — treat as algebraic for now
            types[exp.name] = PrimitiveType(exp.name)
        elif body_info:
            # Record type
            field_names = body_info.split(",")
            # We don't have field types from exports, use placeholder
            fields = {fn.strip(): PrimitiveType("Value") for fn in field_names}
            types[exp.name] = RecordType(name=exp.name, fields=fields)
        else:
            types[exp.name] = PrimitiveType(exp.name)

    return types


def _build_constants_from_exports(
    exports: list[ExportEntry],
) -> dict[str, Type]:
    """Convert constant export entries to types."""
    constants: dict[str, Type] = {}
    for exp in exports:
        if exp.kind != "constant":
            continue
        constants[exp.name] = (
            _resolve_type_name(exp.return_type) if exp.return_type else PrimitiveType("Value")
        )
    return constants


def load_installed_packages(
    project_dir: Path,
    lockfile: Lockfile,
) -> dict[str, PackageModuleInfo]:
    """Load all installed packages' exports (fast path, no AST deser).

    Returns a dict mapping module_name -> PackageModuleInfo.
    Modules from packages are keyed by their module name (e.g., "JsonUtils"),
    not the package name.
    """
    result: dict[str, PackageModuleInfo] = {}
    pkg_cache = cache_dir()

    for pkg in lockfile.packages:
        # Resolve package path: file:// for local, cache for remote
        if pkg.source.startswith("file://"):
            pkg_path = Path(pkg.source[7:])
        else:
            pkg_path = pkg_cache / pkg.name / f"{pkg.version}.prvpkg"
        if not pkg_path.exists():
            continue

        # Apply migrations if needed
        from prove.migrations import migrate_package, needs_migration

        if needs_migration(pkg_path):
            migrate_package(pkg_path)

        try:
            info = read_package(pkg_path)
        except Exception:
            continue

        # Group exports by module
        by_module: dict[str, list[ExportEntry]] = {}
        for exp in info.exports:
            by_module.setdefault(exp.module, []).append(exp)

        for mod_name, exports in by_module.items():
            result[mod_name] = PackageModuleInfo(
                package_name=pkg.name,
                package_version=pkg.version,
                module_name=mod_name,
                types=_build_types_from_exports(exports),
                functions=_build_functions_from_exports(exports, mod_name),
                constants=_build_constants_from_exports(exports),
                pkg_path=pkg_path,
            )

    return result


def load_package_for_emit(pkg_info: PackageModuleInfo) -> tuple[Module, SymbolTable]:
    """Full AST deserialization for C emission (slow path).

    Returns (Module, SymbolTable) ready for the emitter.
    """
    from prove.checker import Checker

    if pkg_info.pkg_path is None:
        raise ValueError(f"no package path for {pkg_info.module_name}")

    module = load_package_module(pkg_info.pkg_path, pkg_info.module_name)

    # Run checker on the deserialized AST to build symbol table
    checker = Checker()
    symbols = checker.check(module)

    return module, symbols
