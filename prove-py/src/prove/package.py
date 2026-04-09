"""Create and read .prvpkg (SQLite) package files.

A .prvpkg IS a SQLite database containing:
  - meta: key-value metadata (name, version, prove_version)
  - exports: function/type/constant signatures (checker fast path)
  - strings: interned string table for AST blobs
  - module_ast: binary AST blobs per module
  - dependencies: declared package deps
  - assets: comptime-resolved data (CSV, embedded text)
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from prove.ast_nodes import (
    AlgebraicTypeDef,
    FunctionDef,
    LookupTypeDef,
    Module,
    ModuleDecl,
    RecordTypeDef,
)
from prove.ast_serial import StringIntern, deserialize_module, serialize_module

_SCHEMA = """\
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS exports (
    module TEXT, kind TEXT, name TEXT, verb TEXT,
    params TEXT, return_type TEXT, can_fail INTEGER, doc TEXT
);
CREATE TABLE IF NOT EXISTS strings (id INTEGER PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS module_ast (module TEXT PRIMARY KEY, data BLOB);
CREATE TABLE IF NOT EXISTS dependencies (name TEXT, version_constraint TEXT);
CREATE TABLE IF NOT EXISTS assets (key TEXT PRIMARY KEY, data BLOB);
"""


@dataclass
class ExportEntry:
    """One exported symbol from a package module."""

    module: str
    kind: str  # "function", "type", "constant"
    name: str
    verb: str | None = None
    params: str | None = None  # JSON: [{"name": ..., "type": ...}, ...]
    return_type: str | None = None
    can_fail: bool = False
    doc: str | None = None


@dataclass
class PackageInfo:
    """Metadata + exports from a .prvpkg, without full AST deserialization."""

    name: str
    version: str
    prove_version: str
    exports: list[ExportEntry] = field(default_factory=list)
    dependencies: list[tuple[str, str]] = field(default_factory=list)


def _extract_type_name(type_expr) -> str:
    """Extract a human-readable type name from a TypeExpr AST node."""
    from prove.ast_nodes import GenericType, ModifiedType, SimpleType

    if type_expr is None:
        return "Unit"
    if isinstance(type_expr, SimpleType):
        return type_expr.name
    if isinstance(type_expr, GenericType):
        args = ", ".join(_extract_type_name(a) for a in type_expr.args)
        return f"{type_expr.name}<{args}>"
    if isinstance(type_expr, ModifiedType):
        return type_expr.name
    return str(type(type_expr).__name__)


def _extract_exports(module_name: str, module: Module) -> list[ExportEntry]:
    """Extract export entries from a parsed Module AST.

    Functions can appear in two places:
      - Inside ModuleDecl.body (nested declarations)
      - As top-level Module.declarations (alongside ModuleDecl)

    Types and constants are inside ModuleDecl.types / ModuleDecl.constants.
    """
    import json

    exports: list[ExportEntry] = []

    def _add_function(fd: FunctionDef) -> None:
        params = json.dumps(
            [{"name": p.name, "type": _extract_type_name(p.type_expr)} for p in fd.params]
        )
        exports.append(
            ExportEntry(
                module=module_name,
                kind="function",
                name=fd.name,
                verb=fd.verb,
                params=params,
                return_type=_extract_type_name(fd.return_type),
                can_fail=fd.can_fail,
                doc=fd.doc_comment,
            )
        )

    for decl in module.declarations:
        if isinstance(decl, ModuleDecl):
            # Types
            for td in decl.types:
                kind = "type"
                body_desc = ""
                if isinstance(td.body, AlgebraicTypeDef):
                    body_desc = "|".join(v.name for v in td.body.variants)
                elif isinstance(td.body, RecordTypeDef):
                    body_desc = ",".join(f.name for f in td.body.fields)
                elif isinstance(td.body, LookupTypeDef):
                    body_desc = "lookup"
                exports.append(
                    ExportEntry(
                        module=module_name,
                        kind=kind,
                        name=td.name,
                        params=body_desc,
                        doc=td.doc_comment,
                    )
                )

            # Constants
            for cd in decl.constants:
                exports.append(
                    ExportEntry(
                        module=module_name,
                        kind="constant",
                        name=cd.name,
                        return_type=_extract_type_name(cd.type_expr) if cd.type_expr else None,
                        doc=cd.doc_comment,
                    )
                )

            # Functions inside ModuleDecl body
            for fd in decl.body:
                if isinstance(fd, FunctionDef):
                    _add_function(fd)

        elif isinstance(decl, FunctionDef):
            # Top-level functions (outside ModuleDecl)
            _add_function(decl)

    return exports


def create_package(
    output_path: Path,
    *,
    name: str,
    version: str,
    prove_version: str,
    modules: dict[str, Module],
    dependencies: list[tuple[str, str]] | None = None,
    assets: dict[str, bytes] | None = None,
) -> Path:
    """Create a .prvpkg SQLite database from post-evaluation AST modules.

    Args:
        output_path: Where to write the .prvpkg file.
        name: Package name.
        version: Package version.
        prove_version: Prove compiler version used to build.
        modules: Map of module_name -> Module AST (post-evaluation).
        dependencies: List of (name, version_constraint) pairs.
        assets: Map of key -> raw data for store-backed types.

    Returns:
        The output_path.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        output_path.unlink()

    conn = sqlite3.connect(str(output_path))
    try:
        conn.executescript(_SCHEMA)

        # Meta
        conn.execute("INSERT INTO meta VALUES (?, ?)", ("name", name))
        conn.execute("INSERT INTO meta VALUES (?, ?)", ("version", version))
        conn.execute("INSERT INTO meta VALUES (?, ?)", ("prove_version", prove_version))

        # Modules: serialize AST + extract exports
        for mod_name, module in modules.items():
            data, strings = serialize_module(module)

            # Store string table
            for idx, s in enumerate(strings.all_strings()):
                conn.execute(
                    "INSERT OR REPLACE INTO strings VALUES (?, ?)",
                    (idx, s),
                )

            # Store AST blob (prefixed with string count for reconstruction)
            import struct

            header = struct.pack("<I", strings.size())
            conn.execute(
                "INSERT INTO module_ast VALUES (?, ?)",
                (mod_name, header + data),
            )

            # Extract and store exports
            for exp in _extract_exports(mod_name, module):
                conn.execute(
                    "INSERT INTO exports VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        exp.module,
                        exp.kind,
                        exp.name,
                        exp.verb,
                        exp.params,
                        exp.return_type,
                        1 if exp.can_fail else 0,
                        exp.doc,
                    ),
                )

        # Dependencies
        if dependencies:
            for dep_name, constraint in dependencies:
                conn.execute(
                    "INSERT INTO dependencies VALUES (?, ?)",
                    (dep_name, constraint),
                )

        # Assets
        if assets:
            for key, blob in assets.items():
                conn.execute("INSERT INTO assets VALUES (?, ?)", (key, blob))

        conn.commit()
    finally:
        conn.close()

    return output_path


def read_package(pkg_path: Path) -> PackageInfo:
    """Read package metadata + exports without deserializing AST.

    This is the fast path used by the checker to resolve package imports.
    """
    conn = sqlite3.connect(str(pkg_path))
    try:
        # Meta
        meta = dict(conn.execute("SELECT key, value FROM meta").fetchall())

        # Exports
        exports = []
        for row in conn.execute("SELECT * FROM exports").fetchall():
            exports.append(
                ExportEntry(
                    module=row[0],
                    kind=row[1],
                    name=row[2],
                    verb=row[3],
                    params=row[4],
                    return_type=row[5],
                    can_fail=bool(row[6]),
                    doc=row[7],
                )
            )

        # Dependencies
        deps = conn.execute("SELECT name, version_constraint FROM dependencies").fetchall()

        return PackageInfo(
            name=meta.get("name", ""),
            version=meta.get("version", ""),
            prove_version=meta.get("prove_version", ""),
            exports=exports,
            dependencies=deps,
        )
    finally:
        conn.close()


def load_package_module(pkg_path: Path, module_name: str) -> Module:
    """Fully deserialize a module's AST from a .prvpkg file.

    This is the slow path used by the emitter to generate C code.
    """
    import struct

    conn = sqlite3.connect(str(pkg_path))
    try:
        row = conn.execute(
            "SELECT data FROM module_ast WHERE module = ?",
            (module_name,),
        ).fetchone()
        if row is None:
            raise KeyError(f"module '{module_name}' not found in {pkg_path}")

        blob = row[0]
        # Read string count header
        str_count = struct.unpack_from("<I", blob, 0)[0]
        ast_data = blob[4:]

        # Reconstruct string table
        strings_rows = conn.execute("SELECT id, value FROM strings ORDER BY id").fetchall()
        string_list = [""] * max(str_count, len(strings_rows))
        for sid, sval in strings_rows:
            if sid < len(string_list):
                string_list[sid] = sval

        strings = StringIntern.from_list(string_list[:str_count])
        return deserialize_module(ast_data, strings)
    finally:
        conn.close()


def extract_signatures(pkg_path: Path, module_name: str) -> list[ExportEntry]:
    """Extract function signatures for a specific module (fast path)."""
    conn = sqlite3.connect(str(pkg_path))
    try:
        rows = conn.execute(
            "SELECT * FROM exports WHERE module = ? AND kind = 'function'",
            (module_name,),
        ).fetchall()
        return [
            ExportEntry(
                module=row[0],
                kind=row[1],
                name=row[2],
                verb=row[3],
                params=row[4],
                return_type=row[5],
                can_fail=bool(row[6]),
                doc=row[7],
            )
            for row in rows
        ]
    finally:
        conn.close()


def extract_types(pkg_path: Path, module_name: str) -> list[ExportEntry]:
    """Extract type exports for a specific module."""
    conn = sqlite3.connect(str(pkg_path))
    try:
        rows = conn.execute(
            "SELECT * FROM exports WHERE module = ? AND kind = 'type'",
            (module_name,),
        ).fetchall()
        return [
            ExportEntry(
                module=row[0],
                kind=row[1],
                name=row[2],
                verb=row[3],
                params=row[4],
                return_type=row[5],
                can_fail=bool(row[6]),
                doc=row[7],
            )
            for row in rows
        ]
    finally:
        conn.close()


def get_asset(pkg_path: Path, key: str) -> bytes | None:
    """Retrieve an asset blob from a .prvpkg file."""
    conn = sqlite3.connect(str(pkg_path))
    try:
        row = conn.execute("SELECT data FROM assets WHERE key = ?", (key,)).fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def list_modules(pkg_path: Path) -> list[str]:
    """List all module names in a .prvpkg file."""
    conn = sqlite3.connect(str(pkg_path))
    try:
        rows = conn.execute("SELECT module FROM module_ast").fetchall()
        return [r[0] for r in rows]
    finally:
        conn.close()
