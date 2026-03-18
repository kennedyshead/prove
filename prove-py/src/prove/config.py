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
class StyleConfig:
    line_length: int = 90


@dataclass
class ProveConfig:
    package: PackageConfig = field(default_factory=PackageConfig)
    build: BuildConfig = field(default_factory=BuildConfig)
    optimize: OptimizeConfig = field(default_factory=OptimizeConfig)
    test: TestConfig = field(default_factory=TestConfig)
    style: StyleConfig = field(default_factory=StyleConfig)


# Directories under src/ that contain shared resources (stdlib .prv files,
# C runtime) rather than user source code.  Exclude from .prv discovery.
_RESERVED_SRC_DIRS = frozenset({"stdlib", "runtime", ".prove_cache"})


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

    if "style" in data:
        sty = data["style"]
        config.style = StyleConfig(
            line_length=sty.get("line_length", 90),
        )

    return config
