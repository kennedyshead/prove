"""TOML config loading for prove.toml."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class PackageConfig:
    name: str = "untitled"
    version: str = "0.0.0"
    authors: list[str] = field(default_factory=list)
    license: str = ""


@dataclass
class BuildConfig:
    target: str = "native"
    optimize: bool = False


@dataclass
class TestConfig:
    property_rounds: int = 1000


@dataclass
class ProveConfig:
    package: PackageConfig = field(default_factory=PackageConfig)
    build: BuildConfig = field(default_factory=BuildConfig)
    test: TestConfig = field(default_factory=TestConfig)


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
            optimize=bld.get("optimize", False),
        )

    if "test" in data:
        tst = data["test"]
        config.test = TestConfig(
            property_rounds=tst.get("property_rounds", 1000),
        )

    return config
