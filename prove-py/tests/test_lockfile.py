"""Tests for lockfile and config dependency support."""

import tempfile
from pathlib import Path

from prove.config import load_config, remove_dependency, write_dependency
from prove.lockfile import LockedPackage, Lockfile, lockfile_is_stale, read_lockfile, write_lockfile


def test_lockfile_roundtrip():
    lockfile = Lockfile(
        prove_version="1.1.0",
        packages=[
            LockedPackage(
                name="json-utils",
                version="0.3.0",
                checksum="sha256:abc123",
                source="https://registry.prove-lang.org/packages/json-utils/0.3.0.prvpkg",
            ),
            LockedPackage(
                name="text-helpers",
                version="0.2.1",
                checksum="sha256:def456",
                source="https://registry.prove-lang.org/packages/text-helpers/0.2.1.prvpkg",
            ),
        ],
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "prove.lock"
        write_lockfile(path, lockfile)

        restored = read_lockfile(path)
        assert restored is not None
        assert restored.prove_version == "1.1.0"
        assert len(restored.packages) == 2
        assert restored.packages[0].name == "json-utils"
        assert restored.packages[0].version == "0.3.0"
        assert restored.packages[0].checksum == "sha256:abc123"
        assert restored.packages[1].name == "text-helpers"


def test_read_lockfile_missing():
    path = Path("/nonexistent/prove.lock")
    assert read_lockfile(path) is None


def test_lockfile_is_stale():
    lockfile = Lockfile(
        prove_version="1.0.0",
        packages=[
            LockedPackage("json-utils", "0.3.0", "sha256:abc", "https://example.com/j.prvpkg"),
        ],
    )

    # Not stale when deps match
    assert not lockfile_is_stale(lockfile, [("json-utils", "0.3.0")])

    # Stale: missing dep
    assert lockfile_is_stale(lockfile, [("json-utils", "0.3.0"), ("new-dep", "1.0.0")])

    # Stale: extra package in lock
    assert lockfile_is_stale(lockfile, [])

    # Stale: version mismatch (exact)
    assert lockfile_is_stale(lockfile, [("json-utils", "0.4.0")])

    # Not stale: range constraint (not checked strictly)
    assert not lockfile_is_stale(lockfile, [("json-utils", ">=0.2.0")])


def test_config_dependencies():
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "prove.toml"
        config_path.write_text(
            '[package]\nname = "myproject"\nversion = "1.0.0"\n\n'
            '[dependencies]\njson-utils = "0.3.0"\ntext-helpers = ">=0.2.0"\n'
        )

        config = load_config(config_path)
        assert len(config.dependencies) == 2
        assert config.dependencies[0].name == "json-utils"
        assert config.dependencies[0].version_constraint == "0.3.0"
        assert config.dependencies[1].name == "text-helpers"
        assert config.dependencies[1].version_constraint == ">=0.2.0"


def test_config_no_dependencies():
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "prove.toml"
        config_path.write_text('[package]\nname = "myproject"\n')

        config = load_config(config_path)
        assert config.dependencies == []


def test_write_dependency():
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "prove.toml"
        config_path.write_text('[package]\nname = "myproject"\n')

        write_dependency(config_path, "json-utils", "0.3.0")
        config = load_config(config_path)
        assert len(config.dependencies) == 1
        assert config.dependencies[0].name == "json-utils"

        # Update existing
        write_dependency(config_path, "json-utils", "0.4.0")
        config = load_config(config_path)
        assert len(config.dependencies) == 1
        assert config.dependencies[0].version_constraint == "0.4.0"


def test_remove_dependency():
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "prove.toml"
        config_path.write_text(
            '[package]\nname = "myproject"\n\n[dependencies]\njson-utils = "0.3.0"\n'
        )

        assert remove_dependency(config_path, "json-utils") is True
        config = load_config(config_path)
        assert len(config.dependencies) == 0

        # Removing nonexistent returns False
        assert remove_dependency(config_path, "nonexistent") is False


def test_config_path_dependency():
    """Config parses { path = "..." } dependency format."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "prove.toml"
        config_path.write_text(
            '[package]\nname = "myproject"\n\n'
            "[dependencies]\n"
            'my-lib = { path = "../my-lib" }\n'
            'other = "1.0.0"\n'
        )

        config = load_config(config_path)
        assert len(config.dependencies) == 2

        # Path dependency
        my_lib = config.dependencies[0]
        assert my_lib.name == "my-lib"
        assert my_lib.path is not None
        assert my_lib.version_constraint == "*"

        # Regular dependency
        other = config.dependencies[1]
        assert other.name == "other"
        assert other.path is None
        assert other.version_constraint == "1.0.0"


def test_config_path_dependency_with_version():
    """Config parses { path = "...", version = "..." } format."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "prove.toml"
        config_path.write_text(
            '[package]\nname = "myproject"\n\n'
            "[dependencies]\n"
            'my-lib = { path = "../my-lib", version = "0.1.0" }\n'
        )

        config = load_config(config_path)
        dep = config.dependencies[0]
        assert dep.name == "my-lib"
        assert dep.path is not None
        assert dep.version_constraint == "0.1.0"


def test_write_path_dependency():
    """write_dependency with dep_path produces table form."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "prove.toml"
        config_path.write_text('[package]\nname = "myproject"\n')

        write_dependency(config_path, "my-lib", "*", dep_path="../my-lib")
        config = load_config(config_path)
        assert len(config.dependencies) == 1
        dep = config.dependencies[0]
        assert dep.name == "my-lib"
        assert dep.path is not None
        assert "my-lib" in dep.path


def test_lockfile_with_local_source():
    """Lockfile preserves file:// sources."""
    lockfile = Lockfile(
        prove_version="1.0.0",
        packages=[
            LockedPackage(
                "my-lib",
                "0.1.0",
                "sha256:abc",
                "file:///tmp/cache/my-lib/0.1.0.prvpkg",
            ),
        ],
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "prove.lock"
        write_lockfile(path, lockfile)
        restored = read_lockfile(path)

        assert restored is not None
        assert len(restored.packages) == 1
        assert restored.packages[0].source == "file:///tmp/cache/my-lib/0.1.0.prvpkg"
