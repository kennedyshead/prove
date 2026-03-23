"""Automatic Python package bundling for foreign libpython3 modules.

When the compiler detects a module that uses `foreign "libpython3"` and has
comptime-read `.py` files, this module:
  1. Scans those .py entry points for Python imports (transitively via AST)
  2. Resolves each import to its exact .py file via importlib
  3. Skips stdlib packages (only bundles third-party site-packages)
  4. Zips only the reachable files (not entire package trees)
  5. Writes prove_bundle_data.h as a C byte array into the build gen dir

When standalone=True, also bundles all transitively-imported stdlib .py files
so the binary runs without a Python installation.

The generated header is then #included by py_wrappers.c, which writes the
zip to a temp file and prepends it to sys.path at runtime.
"""

from __future__ import annotations

import ast
import importlib.util
import io
import os
import zipfile
from pathlib import Path

_MAX_SCAN_BYTES = 2 * 1024 * 1024  # skip files larger than 2 MB (huge generated data files)
_SKIP_SUFFIXES = frozenset({".pyc", ".pyo"})
_SKIP_DIRS = frozenset({"__pycache__"})


def _parse_imports(py_file: Path, package: str | None = None) -> set[str]:
    """Return dotted module names imported by a single .py file.

    Returns both bare module names (`import foo.bar`) and from-import targets
    (`from foo import bar` yields `foo` and `foo.bar` — bar may be a submodule).
    When `package` is provided, relative imports are resolved against it so that
    intra-package imports (e.g. `from . import converters`) are followed.
    Files over _MAX_SCAN_BYTES are skipped (machine-generated data files).
    """
    try:
        if py_file.stat().st_size > _MAX_SCAN_BYTES:
            return set()
        tree = ast.parse(py_file.read_text(encoding="utf-8", errors="replace"))
    except (SyntaxError, OSError):
        return set()

    names: set[str] = set()
    pkg_parts = package.split(".") if package else []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                if node.module:
                    names.add(node.module)
                    # 'from foo import bar' — bar may be a submodule
                    for alias in node.names:
                        names.add(f"{node.module}.{alias.name}")
            elif pkg_parts and node.level <= len(pkg_parts):
                # Resolve relative import: level=1 → current package, level=2 → parent, …
                base_parts = pkg_parts[: len(pkg_parts) - (node.level - 1)]
                if node.module:
                    base_parts = base_parts + node.module.split(".")
                base = ".".join(base_parts)
                if base:
                    names.add(base)
                    for alias in node.names:
                        names.add(f"{base}.{alias.name}")
    return names


def _find_used_files(entry_files: set[Path]) -> dict[str, Path]:
    """Transitively resolve third-party files reachable via imports.

    Starts from entry .py files and follows the import graph file-by-file,
    only including modules that are actually imported.  Returns
    {archive_path: fs_path} where archive_path is relative to the top-level
    package's site-packages parent so the zip is directly importable.

    Non-py package data files (e.g. .prv, .json loaded via importlib.resources)
    are included for every top-level package touched.
    """
    import sys

    stdlib_names: frozenset[str] = getattr(sys, "stdlib_module_names", frozenset())

    result: dict[str, Path] = {}  # archive_path -> fs_path
    pkg_parents: dict[str, Path] = {}  # top pkg name -> site-packages dir
    visited: set[str] = set()  # dotted module names already resolved
    # Each entry: (file_path, package_name_or_None)
    # package_name is used to resolve relative imports; None for unknown entry files.
    scan_queue: list[tuple[Path, str | None]] = [(f, None) for f in entry_files]

    def _pkg_parent(top: str) -> Path | None:
        if top in pkg_parents:
            return pkg_parents[top]
        try:
            spec = importlib.util.find_spec(top)
        except (ModuleNotFoundError, ValueError):
            return None
        if spec and spec.submodule_search_locations:
            parent = Path(next(iter(spec.submodule_search_locations))).resolve().parent
            pkg_parents[top] = parent
            return parent
        return None

    def _register(module_name: str, origin: Path) -> None:
        top = module_name.split(".")[0]
        parent = _pkg_parent(top)
        if parent:
            try:
                result[str(origin.resolve().relative_to(parent))] = origin
            except ValueError:
                pass

    while scan_queue:
        files_this_round = list(scan_queue)
        scan_queue = []

        for f, file_package in files_this_round:
            for module_name in _parse_imports(f, package=file_package):
                top = module_name.split(".")[0]
                if top in stdlib_names or top in sys.builtin_module_names:
                    continue
                if module_name in visited:
                    continue
                visited.add(module_name)

                try:
                    spec = importlib.util.find_spec(module_name)
                except Exception:
                    # Covers ModuleNotFoundError, ValueError, AssertionError, and
                    # platform-specific modules (e.g. click._winconsole on non-Windows)
                    # that raise unconditionally on import.
                    continue
                if spec is None or not spec.origin or not spec.origin.endswith(".py"):
                    continue

                origin = Path(spec.origin)
                _register(module_name, origin)
                # Compute the package name for this file so its relative imports resolve.
                # __init__.py files ARE the package; regular files belong to the parent package.
                if origin.name == "__init__.py":
                    child_package: str | None = module_name
                else:
                    parent = ".".join(module_name.split(".")[:-1])
                    child_package = parent or None
                scan_queue.append((origin, child_package))

                # Ensure all parent package __init__.py files are present
                parts = module_name.split(".")
                for i in range(1, len(parts)):
                    parent_name = ".".join(parts[:i])
                    if parent_name in visited:
                        continue
                    visited.add(parent_name)
                    try:
                        pspec = importlib.util.find_spec(parent_name)
                    except (ModuleNotFoundError, ValueError):
                        continue
                    if pspec and pspec.origin and pspec.origin.endswith(".py"):
                        porigin = Path(pspec.origin)
                        _register(parent_name, porigin)
                        # Parent __init__.py — package name is the module name itself
                        scan_queue.append((porigin, parent_name))

    # Include non-py package data for every top-level package we touched
    for pkg_name, parent_dir in pkg_parents.items():
        pkg_dir = parent_dir / pkg_name
        if not pkg_dir.is_dir():
            continue
        for dirpath, dirnames, filenames in os.walk(pkg_dir, followlinks=True):
            dirnames[:] = [d for d in sorted(dirnames) if d not in _SKIP_DIRS]
            for fname in sorted(filenames):
                f = Path(dirpath) / fname
                if f.suffix in _SKIP_SUFFIXES or (f.suffix == ".py" and f.name != "__init__.py"):
                    continue
                try:
                    arc = str(f.resolve().relative_to(parent_dir))
                except ValueError:
                    # Symlink resolved outside parent_dir; use logical path instead
                    try:
                        arc = str(f.relative_to(parent_dir))
                    except ValueError:
                        continue
                result[arc] = f

    return result


def _find_stdlib_modules(
    entry_files: set[Path],
    bundled_files: dict[str, Path],
) -> dict[str, Path]:
    """Transitively find stdlib .py modules imported by entry files and bundled files.

    Returns a dict of {archive_path: fs_path} where archive_path is relative
    to the stdlib directory (so `import pathlib` extracts as `pathlib.py` at the
    root of the zip, making it importable after zip is on sys.path).
    """
    import sys
    import sysconfig

    stdlib_dir = Path(sysconfig.get_path("stdlib"))
    stdlib_names: frozenset[str] = getattr(sys, "stdlib_module_names", frozenset())

    scan_queue: list[Path] = list(entry_files)
    scan_queue.extend(p for p in bundled_files.values() if p.suffix == ".py")

    visited: set[str] = set()
    result: dict[str, Path] = {}

    while scan_queue:
        f = scan_queue.pop()
        for name in _parse_imports(f):
            top = name.split(".")[0]
            if top in visited or top not in stdlib_names:
                continue
            visited.add(top)
            try:
                spec = importlib.util.find_spec(top)
            except (ModuleNotFoundError, ValueError):
                continue
            if spec is None:
                continue
            if spec.submodule_search_locations:
                # Package (directory) — e.g. email, xml, importlib
                pkg_dir = Path(next(iter(spec.submodule_search_locations)))
                for py_file in sorted(pkg_dir.rglob("*.py")):
                    if "__pycache__" in py_file.parts:
                        continue
                    try:
                        arc = str(py_file.relative_to(stdlib_dir))
                    except ValueError:
                        arc = py_file.name
                    result[arc] = py_file
                    scan_queue.append(py_file)
            elif spec.origin and spec.origin.endswith(".py"):
                origin = Path(spec.origin)
                try:
                    arc = str(origin.relative_to(stdlib_dir))
                except ValueError:
                    arc = origin.name
                result[arc] = origin
                scan_queue.append(origin)

    return result


def _zip_files(
    files: dict[str, Path],
    stdlib_files: dict[str, Path] | None = None,
) -> bytes:
    """Zip the given files at their archive paths.

    files: {archive_path: fs_path} for third-party packages
    stdlib_files: {archive_path: fs_path} for stdlib modules (standalone mode)
    """
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for arc_path, fs_path in sorted(files.items()):
            if fs_path.is_file():
                zf.write(fs_path, arc_path)
        if stdlib_files:
            for arc_path, fs_path in sorted(stdlib_files.items()):
                zf.write(fs_path, arc_path)
    return buf.getvalue()


def _write_c_header(data: bytes, out_path: Path) -> None:
    """Write the zip bytes as a C header with a static byte array."""
    lines = [
        "/* Auto-generated by prove compiler — do not edit. */\n",
        "/* Re-generated on every `prove build` that uses foreign libpython3. */\n",
        "#pragma once\n",
        "#include <stddef.h>\n\n",
        "static const unsigned char prove_bundle_zip[] = {\n",
    ]
    for i, b in enumerate(data):
        if i % 16 == 0:
            lines.append("    ")
        lines.append(f"0x{b:02x},")
        lines.append("\n" if i % 16 == 15 else " ")
    if len(data) % 16 != 0:
        lines.append("\n")
    lines.append("};\n")
    lines.append(f"static const size_t prove_bundle_zip_len = {len(data)};\n")
    out_path.write_text("".join(lines))


def _discover_venv_paths() -> list[str]:
    """Find additional Python paths from the project virtualenv.

    The embedded Python in proof doesn't activate the venv, so its sys.path
    lacks the venv's site-packages and any .pth-added directories (e.g. editable
    installs).  This function locates the venv and reconstructs those paths.
    """
    import glob as _glob

    venv_dir: str | None = os.environ.get("VIRTUAL_ENV")
    if not venv_dir:
        # Walk up from cwd looking for .venv
        d = Path.cwd()
        for _ in range(5):
            candidate = d / ".venv"
            if candidate.is_dir():
                venv_dir = str(candidate)
                break
            d = d.parent
    if not venv_dir:
        return []

    paths: list[str] = []
    # Find site-packages directories in the venv
    for sp_str in _glob.glob(os.path.join(venv_dir, "lib", "python*", "site-packages")):
        sp = Path(sp_str)
        if not sp.is_dir():
            continue
        paths.append(str(sp))
        # Process .pth files — these add paths for editable installs
        for pth in sp.glob("*.pth"):
            for line in pth.read_text(encoding="utf-8", errors="ignore").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or line.startswith("import "):
                    continue
                p = Path(line)
                if not p.is_absolute():
                    p = sp / p
                if p.is_dir():
                    paths.append(str(p.resolve()))
    return paths


def _find_files_on_disk(entry_files: set[Path]) -> dict[str, Path]:
    """Locate third-party packages on the real filesystem when running from a bundle.

    Uses importlib.machinery.PathFinder with an augmented search path (venv
    site-packages + .pth paths) to bypass sys.modules and find packages
    installed on disk.  Returns {archive_path: fs_path} in the same format
    as _find_used_files().
    """
    import sys
    from importlib.machinery import PathFinder

    stdlib_names: frozenset[str] = getattr(sys, "stdlib_module_names", frozenset())
    search_path = [p for p in sys.path if not _is_bundle_zip(p)]
    search_path.extend(_discover_venv_paths())

    # Collect top-level package names imported by the entry files
    top_packages: set[str] = set()
    for f in entry_files:
        for name in _parse_imports(f):
            top = name.split(".")[0]
            if top not in stdlib_names and top not in sys.builtin_module_names:
                top_packages.add(top)

    result: dict[str, Path] = {}
    for pkg_name in sorted(top_packages):
        spec = PathFinder.find_spec(pkg_name, search_path)
        if not spec or not spec.submodule_search_locations:
            continue
        pkg_dir = Path(next(iter(spec.submodule_search_locations))).resolve()
        if not pkg_dir.is_dir():
            continue
        parent = pkg_dir.parent
        for dirpath, dirnames, filenames in os.walk(pkg_dir, followlinks=True):
            dirnames[:] = [d for d in sorted(dirnames) if d not in _SKIP_DIRS]
            for fname in sorted(filenames):
                f = Path(dirpath) / fname
                if f.suffix in _SKIP_SUFFIXES:
                    continue
                try:
                    arc = str(f.resolve().relative_to(parent))
                except ValueError:
                    try:
                        arc = str(f.relative_to(parent))
                    except ValueError:
                        continue
                result[arc] = f

    return result


def _is_bundle_zip(path_entry: str) -> bool:
    """True if a sys.path entry is a prove bundle zip."""
    return path_entry.endswith(".zip") and "prove_bundle" in path_entry


def _find_existing_bundle_zip() -> Path | None:
    """Find the bundle zip on sys.path when running from an already-bundled binary.

    py_wrappers.c writes the bundle to .prove_bundle.zip next to the binary
    and prepends it to sys.path.  We look for that zip so we can re-emit it
    into the new build.
    """
    import sys

    for entry in sys.path:
        if _is_bundle_zip(entry):
            p = Path(entry)
            if p.is_file():
                return p
    return None


def maybe_generate_bundle(
    modules_and_symbols: list,
    comptime_deps: set[Path],
    gen_dir: Path,
    *,
    standalone: bool = False,
) -> bool:
    """Generate prove_bundle_data.h if the project embeds Python.

    Returns True if the header was written, False if the project does not
    use foreign libpython3 (no-op for projects that don't embed Python).

    When standalone=True, also bundles all transitively-imported Python stdlib
    .py files so the binary runs without a Python installation on the target.

    Raises SystemExit with a clear message if no bundleable files are found
    so the error surfaces before C compilation rather than as a runtime crash.
    """
    from prove.ast_nodes import ModuleDecl

    # Detect foreign "libpython3" in any module
    uses_libpython = any(
        fb.library == "libpython3"
        for module, _ in modules_and_symbols
        for decl in module.declarations
        if isinstance(decl, ModuleDecl)
        for fb in decl.foreign_blocks
    )
    if not uses_libpython:
        # Write an empty stub so py_wrappers.c compiles without errors
        stub = gen_dir / "prove_bundle_data.h"
        if not stub.exists():
            stub.write_text(
                "/* No Python FFI — empty bundle. */\n"
                "#pragma once\n"
                "#include <stddef.h>\n"
                "static const unsigned char prove_bundle_zip[] = {};\n"
                "static const size_t prove_bundle_zip_len = 0;\n"
            )
        return False

    py_entry_files = {p for p in comptime_deps if p.suffix == ".py"}
    if not py_entry_files:
        return False

    files = _find_used_files(py_entry_files)

    # If all resolved files are inside a zip (running from a bundled binary),
    # the bundle zip shadows the real installed package.  Augment sys.path
    # with the venv's paths, remove the bundle zip, and clear cached prove
    # modules so _find_used_files resolves from the real filesystem.
    if files and all(not fs_path.is_file() for fs_path in files.values()):
        import sys

        stdlib_names: frozenset[str] = getattr(sys, "stdlib_module_names", frozenset())
        original_path = sys.path[:]
        saved_modules: dict[str, object] = {}
        # Clear all non-stdlib modules so find_spec searches the real
        # filesystem instead of returning cached zip-based specs.
        for key in list(sys.modules):
            top = key.split(".")[0]
            if top not in stdlib_names and top not in sys.builtin_module_names:
                saved_modules[key] = sys.modules.pop(key)

        sys.path = [p for p in sys.path if not _is_bundle_zip(p)]
        sys.path.extend(_discover_venv_paths())
        importlib.invalidate_caches()
        try:
            files = _find_used_files(py_entry_files)
        finally:
            sys.path = original_path
            sys.modules.update(saved_modules)
            importlib.invalidate_caches()

    # Last resort: copy the existing bundle zip from the running binary
    if files and all(not fs_path.is_file() for fs_path in files.values()):
        existing_zip = _find_existing_bundle_zip()
        if existing_zip is None:
            return False
        data = existing_zip.read_bytes()
        out_path = gen_dir / "prove_bundle_data.h"
        _write_c_header(data, out_path)
        print(f"re-bundled python packages from existing bundle → {len(data):,} bytes")
        return True

    if not files:
        raise SystemExit(
            "error: foreign libpython3 detected but no bundleable files found.\n"
            "       Make sure the required packages are installed in the active venv.\n"
            f"       Entry files scanned: {sorted(str(p) for p in py_entry_files)}"
        )

    # Do NOT bundle stdlib .py files into the zip.  The statically-linked
    # Python interpreter already has its stdlib prefix baked in and will find
    # os/sys/glob/pathlib/etc. from the system.  Putting stdlib files in the
    # zip prepends them onto sys.path *after* Py_Initialize() has already
    # imported some stdlib modules from the system path, causing version
    # mismatches (e.g. glob.py from the zip lacks symbols that the
    # already-loaded pathlib expects from the system glob).
    data = _zip_files(files)
    out_path = gen_dir / "prove_bundle_data.h"
    _write_c_header(data, out_path)

    py_count = sum(1 for p in files if p.endswith(".py"))
    data_count = len(files) - py_count
    data_note = f" + {data_count} data files" if data_count else ""
    libpython_note = " + libpython3 (static)" if standalone else ""
    print(
        f"bundled python packages → {py_count} source files{data_note},"
        f" {len(data):,} bytes{libpython_note}"
    )
    return True
