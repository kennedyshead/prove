"""Tests for AST migrations."""

import sqlite3
import tempfile
from pathlib import Path

from prove.migrations import get_migration_path, migrate_package, needs_migration


def _create_test_pkg(tmpdir: Path, prove_version: str = "0.9.0") -> Path:
    """Create a minimal .prvpkg with the given prove_version."""
    pkg_path = tmpdir / "test.prvpkg"
    conn = sqlite3.connect(str(pkg_path))
    conn.executescript(
        """
        CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
        CREATE TABLE exports (module TEXT, kind TEXT, name TEXT, verb TEXT,
            params TEXT, return_type TEXT, can_fail INTEGER, doc TEXT);
        CREATE TABLE strings (id INTEGER PRIMARY KEY, value TEXT);
        CREATE TABLE module_ast (module TEXT PRIMARY KEY, data BLOB);
        CREATE TABLE dependencies (name TEXT, version_constraint TEXT);
        CREATE TABLE assets (key TEXT PRIMARY KEY, data BLOB);
    """
    )
    conn.execute("INSERT INTO meta VALUES ('name', 'test')")
    conn.execute("INSERT INTO meta VALUES ('version', '1.0.0')")
    conn.execute("INSERT INTO meta VALUES ('prove_version', ?)", (prove_version,))
    conn.commit()
    conn.close()
    return pkg_path


def test_needs_migration():
    with tempfile.TemporaryDirectory() as tmpdir:
        pkg_path = _create_test_pkg(Path(tmpdir), "0.9.0")
        # Different from current version, so needs migration
        assert needs_migration(pkg_path) is True


def test_needs_migration_current():
    from prove import __version__

    with tempfile.TemporaryDirectory() as tmpdir:
        pkg_path = _create_test_pkg(Path(tmpdir), __version__)
        assert needs_migration(pkg_path) is False


def test_migrate_package_updates_version():
    from prove import __version__

    with tempfile.TemporaryDirectory() as tmpdir:
        pkg_path = _create_test_pkg(Path(tmpdir), "0.9.0")
        result = migrate_package(pkg_path)
        assert result is True

        # Check version was updated
        conn = sqlite3.connect(str(pkg_path))
        row = conn.execute("SELECT value FROM meta WHERE key = 'prove_version'").fetchone()
        conn.close()
        assert row[0] == __version__


def test_migrate_package_no_op():
    from prove import __version__

    with tempfile.TemporaryDirectory() as tmpdir:
        pkg_path = _create_test_pkg(Path(tmpdir), __version__)
        result = migrate_package(pkg_path)
        assert result is False  # Already current


def test_get_migration_path_empty():
    """No migrations needed for same version."""
    assert get_migration_path("1.0.0", "1.0.0") == []


def test_get_migration_path_unknown():
    """Unknown versions return empty path."""
    assert get_migration_path("0.0.1", "99.0.0") == []


def test_migration_with_sql():
    """Test that SQL migrations are actually applied."""
    from prove.migrations import MIGRATIONS

    # Temporarily add a test migration
    test_migration = ("0.9.0", ["ALTER TABLE meta ADD COLUMN test_col TEXT DEFAULT 'migrated'"])
    MIGRATIONS.append(test_migration)

    # Rebuild index
    from prove import migrations

    migrations._VERSION_INDEX = {ver: i for i, (ver, _) in enumerate(MIGRATIONS)}

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            pkg_path = _create_test_pkg(Path(tmpdir), "0.9.0")
            result = migrate_package(pkg_path, target_version="1.0.0")
            assert result is True

            # Verify the migration was applied
            conn = sqlite3.connect(str(pkg_path))
            # The ALTER TABLE should have added the column
            row = conn.execute("PRAGMA table_info(meta)").fetchall()
            col_names = [r[1] for r in row]
            assert "test_col" in col_names
            conn.close()
    finally:
        # Clean up
        MIGRATIONS.pop()
        migrations._VERSION_INDEX = {ver: i for i, (ver, _) in enumerate(MIGRATIONS)}
