"""TOML config loading for prove.toml."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path


def _expand_flags(flags: list[str], base: Path) -> list[str]:
    """Expand ~ and resolve relative paths in compiler/linker flags."""
    result = []
    for flag in flags:
        for prefix in ("-I", "-L", "-Wl,-rpath,"):
            if flag.startswith(prefix):
                p = os.path.expanduser(flag[len(prefix) :])
                resolved = str((base / p).resolve()) if not os.path.isabs(p) else p
                flag = prefix + resolved
                break
        else:
            flag = os.path.expanduser(flag)
        result.append(flag)
    return result


@dataclass
class PackageConfig:
    name: str = "untitled"
    version: str = "0.0.0"
    authors: list[str] = field(default_factory=list)
    license: str = ""


@dataclass
class BuildConfig:
    target: str = "native"
    mutate: bool = True
    debug: bool = False
    c_flags: list[str] = field(default_factory=list)
    link_flags: list[str] = field(default_factory=list)
    c_sources: list[str] = field(default_factory=list)
    pre_build: list[list[str]] = field(default_factory=list)
    ccache: bool = True
    vendor_libs: list[str] = field(default_factory=list)


@dataclass
class OptimizeConfig:
    enabled: bool = True
    pgo: bool = False
    strip: bool = True
    tune_host: bool = False
    gc_sections: bool = True


@dataclass
class TestConfig:
    property_rounds: int = 1000


@dataclass
class DependencyConfig:
    name: str
    version_constraint: str
    path: str | None = None  # Local path to package project (relative to prove.toml)


@dataclass
class ProveConfig:
    package: PackageConfig = field(default_factory=PackageConfig)
    build: BuildConfig = field(default_factory=BuildConfig)
    optimize: OptimizeConfig = field(default_factory=OptimizeConfig)
    test: TestConfig = field(default_factory=TestConfig)
    dependencies: list[DependencyConfig] = field(default_factory=list)


# Directories under src/ that contain shared resources (stdlib .prv files,
# C runtime) rather than user source code.  Exclude from .prv discovery.
_RESERVED_SRC_DIRS = frozenset({"stdlib", "runtime", ".prove"})


def discover_prv_files(root: Path) -> list[Path]:
    """Return sorted .prv source files under *root*, excluding reserved dirs."""
    return sorted(
        p for p in root.rglob("*.prv") if not (_RESERVED_SRC_DIRS & set(p.relative_to(root).parts))
    )


def find_config(start_path: Path | None = None) -> Path:
    """Walk up directories to find prove.toml. Raises FileNotFoundError."""
    path = (start_path or Path.cwd()).resolve()
    if path.is_file():
        path = path.parent
    while True:
        candidate = path / "prove.toml"
        if candidate.exists():
            return candidate
        parent = path.parent
        if parent == path:
            raise FileNotFoundError("No prove.toml found in any parent directory")
        path = parent


def load_config(path: Path) -> ProveConfig:
    """Parse a prove.toml file into a ProveConfig."""
    with open(path, "rb") as f:
        data = tomllib.load(f)

    config = ProveConfig()

    if "package" in data:
        pkg = data["package"]
        config.package = PackageConfig(
            name=pkg.get("name", "untitled"),
            version=pkg.get("version", "0.0.0"),
            authors=pkg.get("authors", []),
            license=pkg.get("license", ""),
        )

    if "build" in data:
        bld = data["build"]
        config.build = BuildConfig(
            target=bld.get("target", "native"),
            mutate=bld.get("mutate", True),
            debug=bld.get("debug", False),
            c_flags=_expand_flags(bld.get("c_flags", []), path.parent),
            link_flags=_expand_flags(bld.get("link_flags", []), path.parent),
            c_sources=bld.get("c_sources", []),
            pre_build=bld.get("pre_build", []),
            ccache=bld.get("ccache", True),
            vendor_libs=bld.get("vendor_libs", []),
        )

    if "optimize" in data:
        opt = data["optimize"]
        config.optimize = OptimizeConfig(
            enabled=opt.get("enabled", True),
            pgo=opt.get("pgo", False),
            strip=opt.get("strip", True),
            tune_host=opt.get("tune_host", False),
            gc_sections=opt.get("gc_sections", True),
        )
    elif "build" in data and "optimize" in data["build"]:
        # Backward compat: [build] optimize = true/false
        config.optimize = OptimizeConfig(
            enabled=data["build"]["optimize"],
        )

    if "test" in data:
        tst = data["test"]
        config.test = TestConfig(
            property_rounds=tst.get("property_rounds", 1000),
        )

    if "dependencies" in data:
        deps = data["dependencies"]
        for name, value in deps.items():
            if isinstance(value, dict):
                # Table form: name = { path = "...", version = "..." }
                dep_path = value.get("path")
                if dep_path:
                    # Resolve relative to prove.toml location
                    dep_path = str((path.parent / dep_path).resolve())
                config.dependencies.append(
                    DependencyConfig(
                        name=name,
                        version_constraint=value.get("version", "*"),
                        path=dep_path,
                    )
                )
            else:
                # Simple form: name = "version"
                config.dependencies.append(
                    DependencyConfig(name=name, version_constraint=str(value))
                )

    return config


def write_dependency(
    config_path: Path,
    name: str,
    version_constraint: str,
    *,
    dep_path: str | None = None,
) -> None:
    """Add or update a dependency in prove.toml.

    If *dep_path* is given, writes a table form: ``name = { path = "..." }``.
    Otherwise writes simple form: ``name = "version"``.
    """
    text = config_path.read_text()
    if "[dependencies]" not in text:
        text = text.rstrip() + "\n\n[dependencies]\n"

    if dep_path:
        new_value = f'{name} = {{ path = "{dep_path}" }}'
    else:
        new_value = f'{name} = "{version_constraint}"'

    # Check if dependency already exists
    lines = text.split("\n")
    found = False
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith(f"{name} ") or stripped.startswith(f"{name}="):
            lines[i] = new_value
            found = True
            break
    if not found:
        # Find [dependencies] section and append
        for i, line in enumerate(lines):
            if line.strip() == "[dependencies]":
                lines.insert(i + 1, new_value)
                break
    config_path.write_text("\n".join(lines))


def remove_dependency(config_path: Path, name: str) -> bool:
    """Remove a dependency from prove.toml. Returns True if found."""
    text = config_path.read_text()
    lines = text.split("\n")
    found = False
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith(f"{name} ") or stripped.startswith(f"{name}="):
            lines.pop(i)
            found = True
            break
    if found:
        config_path.write_text("\n".join(lines))
    return found
