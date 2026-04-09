"""Flat dependency resolver for Prove packages.

Each dependency name resolves to exactly one version across the entire
dependency tree.  No diamond dependencies allowed in v1.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from prove.lockfile import LockedPackage, Lockfile
from prove.package import read_package
from prove.registry import (
    DEFAULT_REGISTRY,
    compute_checksum,
    download_package,
    fetch_package_info,
)


@dataclass
class ResolveError:
    message: str


class VersionConstraint:
    """Parses and evaluates version constraints.

    Supported formats:
      - "0.3.0"           exact match
      - ">=0.2.0"         minimum version
      - ">=0.1.0,<1.0.0"  range
      - "^0.2.0"          compatible (>=0.2.0, <0.3.0 for 0.x; >=1.2.0, <2.0.0 for 1.x+)
    """

    def __init__(self, spec: str) -> None:
        self.spec = spec.strip()
        self._checks: list[tuple[str, tuple[int, ...]]] = []
        self._parse()

    def _parse(self) -> None:
        if self.spec.startswith("^"):
            base = self._parse_version(self.spec[1:])
            self._checks.append((">=", base))
            # Caret: bump leftmost non-zero
            if base[0] > 0:
                upper = (base[0] + 1, 0, 0)
            elif base[1] > 0:
                upper = (0, base[1] + 1, 0)
            else:
                upper = (0, 0, base[2] + 1)
            self._checks.append(("<", upper))
            return

        for part in self.spec.split(","):
            part = part.strip()
            for op in (">=", "<=", ">", "<", "==", "="):
                if part.startswith(op):
                    ver = self._parse_version(part[len(op) :].strip())
                    self._checks.append((op if op != "=" else "==", ver))
                    break
            else:
                # Bare version = exact match
                ver = self._parse_version(part)
                self._checks.append(("==", ver))

    @staticmethod
    def _parse_version(s: str) -> tuple[int, ...]:
        parts = s.strip().split(".")
        result = []
        for p in parts:
            digits = re.match(r"(\d+)", p)
            result.append(int(digits.group(1)) if digits else 0)
        while len(result) < 3:
            result.append(0)
        return tuple(result)

    def matches(self, version: str) -> bool:
        """Check if *version* satisfies this constraint."""
        ver = self._parse_version(version)
        for op, target in self._checks:
            if op == ">=" and ver < target:
                return False
            if op == "<=" and ver > target:
                return False
            if op == ">" and ver <= target:
                return False
            if op == "<" and ver >= target:
                return False
            if op == "==" and ver != target:
                return False
        return True


def resolve(
    dependencies: list[tuple[str, str]],
    registry_url: str = DEFAULT_REGISTRY,
    existing_lock: Lockfile | None = None,
    local_paths: dict[str, str] | None = None,
) -> Lockfile | list[ResolveError]:
    """Resolve dependencies to exact versions.

    For each dependency:
    1. If it has a local path, build .prvpkg from that path.
    2. If locked version satisfies constraint, keep it.
    3. Otherwise fetch index from registry, pick latest matching version.
    4. Download .prvpkg, read transitive deps, resolve recursively.

    Flat resolution: each name → exactly one version.  Conflicts are errors.

    Args:
        dependencies: List of (name, version_constraint) pairs.
        registry_url: Base URL of the package registry.
        existing_lock: Existing lockfile for reuse.
        local_paths: Map of package name → absolute local project path.

    Returns a Lockfile on success, or a list of ResolveErrors on failure.
    """
    from prove import __version__ as prove_version

    if local_paths is None:
        local_paths = {}

    locked = {}
    if existing_lock:
        for pkg in existing_lock.packages:
            locked[pkg.name] = pkg

    resolved: dict[str, LockedPackage] = {}
    errors: list[ResolveError] = []

    # Queue: (name, constraint_str, required_by)
    queue: list[tuple[str, str, str]] = [
        (name, constraint, "<root>") for name, constraint in dependencies
    ]
    visited: set[str] = set()

    while queue:
        name, constraint_str, required_by = queue.pop(0)

        if name in resolved:
            # Check compatibility
            existing = resolved[name]
            if constraint_str != "*":
                constraint = VersionConstraint(constraint_str)
                if not constraint.matches(existing.version):
                    errors.append(
                        ResolveError(
                            f"conflict: '{name}' {existing.version} (required by "
                            f"{required_by}) does not satisfy {constraint_str}"
                        )
                    )
            continue

        if name in visited:
            continue
        visited.add(name)

        # Local path dependency — build .prvpkg from local project
        if name in local_paths:
            local_result = _resolve_local(name, local_paths[name], errors)
            if local_result is not None:
                resolved[name] = local_result
                _add_transitive_from_path(local_result.source, queue, errors, name)
            continue

        # Locked source is a local path — check it still exists
        if name in locked and locked[name].source.startswith("file://"):
            pkg_path = locked[name].source[7:]  # strip file://
            if Path(pkg_path).exists():
                resolved[name] = locked[name]
                _add_transitive_from_path(locked[name].source, queue, errors, name)
                continue
            # Local file gone — fall through to registry resolution

        constraint: VersionConstraint | None = None
        if constraint_str != "*":
            constraint = VersionConstraint(constraint_str)

        # Check if locked version satisfies
        if name in locked:
            if constraint is None or constraint.matches(locked[name].version):
                resolved[name] = locked[name]
                _add_transitive(name, locked[name], queue, errors)
                continue

        # Fetch from registry
        info = fetch_package_info(name, registry_url)
        if info is None:
            errors.append(ResolveError(f"package '{name}' not found in registry"))
            continue

        # Pick latest matching version
        if constraint is not None:
            matching = [v for v in info.versions if constraint.matches(v.version)]
        else:
            matching = list(info.versions)
        if not matching:
            available = ", ".join(v.version for v in info.versions)
            errors.append(
                ResolveError(
                    f"no version of '{name}' satisfies {constraint_str} (available: {available})"
                )
            )
            continue

        # Sort by version descending, pick latest
        matching.sort(key=lambda v: VersionConstraint._parse_version(v.version), reverse=True)
        chosen = matching[0]

        # Download
        pkg_path_dl = download_package(name, chosen.version, registry_url)
        if pkg_path_dl is None:
            errors.append(ResolveError(f"failed to download '{name}' {chosen.version}"))
            continue

        checksum = chosen.checksum or compute_checksum(pkg_path_dl)
        source = f"{registry_url}/packages/{name}/{chosen.version}.prvpkg"

        locked_pkg = LockedPackage(
            name=name,
            version=chosen.version,
            checksum=checksum,
            source=source,
        )
        resolved[name] = locked_pkg

        # Read transitive deps
        _add_transitive(name, locked_pkg, queue, errors)

    if errors:
        return errors

    return Lockfile(
        prove_version=prove_version,
        packages=sorted(resolved.values(), key=lambda p: p.name),
    )


def _resolve_local(
    name: str,
    project_path: str,
    errors: list[ResolveError],
) -> LockedPackage | None:
    """Build a .prvpkg from a local project directory.

    Parses the local project's prove.toml, checks + serializes its modules,
    and produces a .prvpkg in the package cache.
    """
    from prove import __version__
    from prove.builder import lex_and_parse
    from prove.checker import Checker
    from prove.config import discover_prv_files, load_config
    from prove.package import create_package
    from prove.registry import cache_dir

    project_dir = Path(project_path)
    config_path = project_dir / "prove.toml"
    if not config_path.exists():
        errors.append(ResolveError(f"local dependency '{name}': no prove.toml at {project_dir}"))
        return None

    config = load_config(config_path)
    src_dir = project_dir / "src"
    if not src_dir.is_dir():
        src_dir = project_dir

    prv_files = discover_prv_files(src_dir)
    if not prv_files:
        errors.append(ResolveError(f"local dependency '{name}': no .prv files found"))
        return None

    # Parse and check all modules
    modules = {}
    for prv_file in prv_files:
        source = prv_file.read_text()
        try:
            module = lex_and_parse(source, str(prv_file))
        except Exception as e:
            errors.append(ResolveError(f"local dependency '{name}': parse error: {e}"))
            return None

        checker = Checker()
        checker.check(module)
        if checker.has_errors():
            error_msgs = [d.message for d in checker.diagnostics if d.severity.name == "ERROR"]
            errors.append(
                ResolveError(
                    f"local dependency '{name}': check errors: {'; '.join(error_msgs[:3])}"
                )
            )
            return None

        # Extract module name from ModuleDecl
        from prove.ast_nodes import ModuleDecl

        for decl in module.declarations:
            if isinstance(decl, ModuleDecl):
                modules[decl.name] = module
                break

    # Build .prvpkg
    version = config.package.version
    pkg_dir = cache_dir() / name
    pkg_dir.mkdir(parents=True, exist_ok=True)
    pkg_path = pkg_dir / f"{version}.prvpkg"

    deps = [(d.name, d.version_constraint) for d in config.dependencies]

    try:
        create_package(
            pkg_path,
            name=name,
            version=version,
            prove_version=__version__,
            modules=modules,
            dependencies=deps,
        )
    except Exception as e:
        errors.append(ResolveError(f"local dependency '{name}': failed to create package: {e}"))
        return None

    checksum = compute_checksum(pkg_path)
    return LockedPackage(
        name=name,
        version=version,
        checksum=checksum,
        source=f"file://{pkg_path}",
    )


def _add_transitive(
    name: str,
    pkg: LockedPackage,
    queue: list[tuple[str, str, str]],
    errors: list[ResolveError],
) -> None:
    """Read transitive dependencies from a cached .prvpkg and add to queue."""
    # If source is a file:// URL, use that path directly
    if pkg.source.startswith("file://"):
        _add_transitive_from_path(pkg.source, queue, errors, name)
        return

    from prove.registry import cache_dir

    pkg_path = cache_dir() / name / f"{pkg.version}.prvpkg"
    if not pkg_path.exists():
        return

    try:
        info = read_package(pkg_path)
        for dep_name, dep_constraint in info.dependencies:
            queue.append((dep_name, dep_constraint, name))
    except Exception:
        errors.append(ResolveError(f"failed to read transitive deps from '{name}'"))


def _add_transitive_from_path(
    source: str,
    queue: list[tuple[str, str, str]],
    errors: list[ResolveError],
    name: str,
) -> None:
    """Read transitive deps from a file:// source."""
    pkg_path = Path(source[7:]) if source.startswith("file://") else Path(source)
    if not pkg_path.exists():
        return

    try:
        info = read_package(pkg_path)
        for dep_name, dep_constraint in info.dependencies:
            queue.append((dep_name, dep_constraint, name))
    except Exception:
        errors.append(ResolveError(f"failed to read transitive deps from '{name}'"))
