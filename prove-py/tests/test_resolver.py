"""Tests for the dependency resolver."""

import tempfile
from pathlib import Path
from unittest.mock import patch

from prove.lockfile import LockedPackage, Lockfile
from prove.registry import RegistryPackageInfo, RegistryVersionInfo
from prove.resolver import VersionConstraint, resolve


def test_version_constraint_exact():
    c = VersionConstraint("1.2.3")
    assert c.matches("1.2.3")
    assert not c.matches("1.2.4")
    assert not c.matches("1.3.0")


def test_version_constraint_gte():
    c = VersionConstraint(">=1.2.0")
    assert c.matches("1.2.0")
    assert c.matches("1.3.0")
    assert c.matches("2.0.0")
    assert not c.matches("1.1.9")


def test_version_constraint_range():
    c = VersionConstraint(">=1.0.0,<2.0.0")
    assert c.matches("1.0.0")
    assert c.matches("1.9.9")
    assert not c.matches("2.0.0")
    assert not c.matches("0.9.0")


def test_version_constraint_caret():
    c = VersionConstraint("^1.2.0")
    assert c.matches("1.2.0")
    assert c.matches("1.9.0")
    assert not c.matches("2.0.0")
    assert not c.matches("1.1.0")

    # 0.x caret
    c2 = VersionConstraint("^0.2.0")
    assert c2.matches("0.2.0")
    assert c2.matches("0.2.5")
    assert not c2.matches("0.3.0")
    assert not c2.matches("1.0.0")


def test_resolve_with_locked():
    """Resolve keeps locked versions when they satisfy constraints."""
    existing = Lockfile(
        prove_version="1.0.0",
        packages=[
            LockedPackage("json-utils", "0.3.0", "sha256:abc", "https://example.com/j.prvpkg"),
        ],
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a fake cached package
        pkg_dir = Path(tmpdir) / "json-utils"
        pkg_dir.mkdir()
        pkg_file = pkg_dir / "0.3.0.prvpkg"

        # Create a minimal SQLite package
        import sqlite3

        conn = sqlite3.connect(str(pkg_file))
        conn.executescript(
            """
            CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
            CREATE TABLE exports (module TEXT, kind TEXT, name TEXT, verb TEXT,
                params TEXT, return_type TEXT, can_fail INTEGER, doc TEXT);
            CREATE TABLE strings (id INTEGER PRIMARY KEY, value TEXT);
            CREATE TABLE module_ast (module TEXT PRIMARY KEY, data BLOB);
            CREATE TABLE dependencies (name TEXT, version_constraint TEXT);
            CREATE TABLE assets (key TEXT PRIMARY KEY, data BLOB);
            INSERT INTO meta VALUES ('name', 'json-utils');
            INSERT INTO meta VALUES ('version', '0.3.0');
            INSERT INTO meta VALUES ('prove_version', '1.0.0');
        """
        )
        conn.commit()
        conn.close()

        with patch("prove.registry.cache_dir", return_value=Path(tmpdir)):
            result = resolve(
                [("json-utils", ">=0.2.0")],
                existing_lock=existing,
            )

    assert isinstance(result, Lockfile)
    assert len(result.packages) == 1
    assert result.packages[0].name == "json-utils"
    assert result.packages[0].version == "0.3.0"


def test_resolve_from_registry():
    """Resolve fetches from registry when no lock exists."""
    mock_info = RegistryPackageInfo(
        name="text-helpers",
        description="Text utilities",
        versions=[
            RegistryVersionInfo("0.2.1", "sha256:aaa", "1.0.0"),
            RegistryVersionInfo("0.2.0", "sha256:bbb", "1.0.0"),
            RegistryVersionInfo("0.1.0", "sha256:ccc", "1.0.0"),
        ],
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        pkg_dir = Path(tmpdir) / "text-helpers"
        pkg_dir.mkdir()
        pkg_file = pkg_dir / "0.2.1.prvpkg"

        import sqlite3

        conn = sqlite3.connect(str(pkg_file))
        conn.executescript(
            """
            CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
            CREATE TABLE exports (module TEXT, kind TEXT, name TEXT, verb TEXT,
                params TEXT, return_type TEXT, can_fail INTEGER, doc TEXT);
            CREATE TABLE strings (id INTEGER PRIMARY KEY, value TEXT);
            CREATE TABLE module_ast (module TEXT PRIMARY KEY, data BLOB);
            CREATE TABLE dependencies (name TEXT, version_constraint TEXT);
            CREATE TABLE assets (key TEXT PRIMARY KEY, data BLOB);
            INSERT INTO meta VALUES ('name', 'text-helpers');
            INSERT INTO meta VALUES ('version', '0.2.1');
        """
        )
        conn.commit()
        conn.close()

        with (
            patch("prove.registry.fetch_package_info", return_value=mock_info),
            patch("prove.registry.download_package", return_value=pkg_file),
            patch("prove.resolver.fetch_package_info", return_value=mock_info),
            patch("prove.resolver.download_package", return_value=pkg_file),
            patch("prove.registry.cache_dir", return_value=Path(tmpdir)),
        ):
            result = resolve([("text-helpers", ">=0.2.0")])

    assert isinstance(result, Lockfile)
    assert len(result.packages) == 1
    assert result.packages[0].name == "text-helpers"
    assert result.packages[0].version == "0.2.1"  # Latest matching


def test_resolve_not_found():
    """Resolve returns error for unknown packages."""
    with (
        patch("prove.resolver.fetch_package_info", return_value=None),
    ):
        result = resolve([("nonexistent", "1.0.0")])

    assert isinstance(result, list)
    assert len(result) == 1
    assert "not found" in result[0].message


def test_resolve_local_path():
    """Resolve handles local path dependencies."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create a local "library" project
        lib_dir = tmpdir / "my-lib"
        lib_dir.mkdir()
        src_dir = lib_dir / "src"
        src_dir.mkdir()
        (lib_dir / "prove.toml").write_text('[package]\nname = "my-lib"\nversion = "0.1.0"\n')
        (src_dir / "mylib.prv").write_text(
            "module MyLib\n"
            '  narrative: """My library."""\n\n'
            "/// Add two numbers.\n"
            "creates add(a Integer, b Integer) Integer\n"
            "from\n"
            "  result as Integer = a\n"
            "  result\n"
        )

        with patch("prove.registry.cache_dir", return_value=tmpdir / "cache"):
            result = resolve(
                [("my-lib", "*")],
                local_paths={"my-lib": str(lib_dir)},
            )

        assert isinstance(result, Lockfile), f"expected Lockfile, got {result}"
        assert len(result.packages) == 1
        pkg = result.packages[0]
        assert pkg.name == "my-lib"
        assert pkg.version == "0.1.0"
        assert pkg.source.startswith("file://")
        assert pkg.checksum.startswith("sha256:")


def test_resolve_local_path_not_found():
    """Resolve returns error for missing local path."""
    result = resolve(
        [("bad-lib", "*")],
        local_paths={"bad-lib": "/nonexistent/path"},
    )
    assert isinstance(result, list)
    assert any("no prove.toml" in e.message for e in result)


def test_resolve_no_matching_version():
    """Resolve returns error when no version satisfies constraint."""
    mock_info = RegistryPackageInfo(
        name="old-pkg",
        versions=[
            RegistryVersionInfo("0.1.0", "sha256:xxx", "1.0.0"),
        ],
    )

    with patch("prove.resolver.fetch_package_info", return_value=mock_info):
        result = resolve([("old-pkg", ">=1.0.0")])

    assert isinstance(result, list)
    assert len(result) == 1
    assert "no version" in result[0].message
