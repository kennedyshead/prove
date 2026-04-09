"""AST migration support for .prvpkg files.

Each Prove release may change the .prvpkg schema.  Migrations are SQL
statements applied to the SQLite database to bring it up to the current
compiler version.

Migration entries map ``from_version → list[SQL_statements]`` and are
applied sequentially to reach the target version.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from prove import __version__

# Ordered list of (version, sql_statements).
# Each entry upgrades FROM the listed version TO the next entry's version.
# Add new migrations at the end as the schema evolves.
MIGRATIONS: list[tuple[str, list[str]]] = [
    # Example migration (placeholder for future schema changes):
    # ("1.0.0", [
    #     "ALTER TABLE exports ADD COLUMN visibility TEXT DEFAULT 'public'",
    # ]),
]

# Build version → index mapping for fast lookup
_VERSION_INDEX: dict[str, int] = {ver: i for i, (ver, _) in enumerate(MIGRATIONS)}


def get_migration_path(from_version: str, to_version: str) -> list[str]:
    """Return the SQL statements needed to migrate from one version to another.

    Returns an empty list if no migration is needed or if the versions
    are not in the migration chain.
    """
    if from_version == to_version:
        return []

    start = _VERSION_INDEX.get(from_version)
    if start is None:
        return []

    # Find the target version or use all remaining migrations
    statements: list[str] = []
    for i in range(start, len(MIGRATIONS)):
        ver, stmts = MIGRATIONS[i]
        statements.extend(stmts)
        # Check if the next entry's version matches the target
        if i + 1 < len(MIGRATIONS) and MIGRATIONS[i + 1][0] == to_version:
            break
        if ver == to_version:
            break

    return statements


def migrate_package(pkg_path: Path, target_version: str | None = None) -> bool:
    """Apply pending migrations to a .prvpkg file.

    Args:
        pkg_path: Path to the .prvpkg SQLite database.
        target_version: Target Prove version (defaults to current).

    Returns:
        True if any migrations were applied, False otherwise.
    """
    if target_version is None:
        target_version = __version__

    conn = sqlite3.connect(str(pkg_path))
    try:
        row = conn.execute("SELECT value FROM meta WHERE key = 'prove_version'").fetchone()
        if row is None:
            return False

        current_version = row[0]
        if current_version == target_version:
            return False

        statements = get_migration_path(current_version, target_version)
        if not statements:
            # No migration path — just update the version
            conn.execute(
                "UPDATE meta SET value = ? WHERE key = 'prove_version'",
                (target_version,),
            )
            conn.commit()
            return True

        for stmt in statements:
            conn.execute(stmt)

        conn.execute(
            "UPDATE meta SET value = ? WHERE key = 'prove_version'",
            (target_version,),
        )
        conn.commit()
        return True
    except sqlite3.Error:
        return False
    finally:
        conn.close()


def needs_migration(pkg_path: Path) -> bool:
    """Check if a .prvpkg file needs migration to the current version."""
    conn = sqlite3.connect(str(pkg_path))
    try:
        row = conn.execute("SELECT value FROM meta WHERE key = 'prove_version'").fetchone()
        if row is None:
            return False
        return row[0] != __version__
    except sqlite3.Error:
        return False
    finally:
        conn.close()
