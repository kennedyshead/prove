# impl03: Database Stdlib

## Overview

General-purpose stdlib module for managing lookup tables (`:[Lookup]` types). Provides storage, versioning, diffs, merges, and compilation to binary lookup tables.

This module is infrastructure — it knows nothing about what the lookup tables contain. Domain-specific logic (ML weights, user data, configuration) is built on top by application code.

## Module

```prove
/// Database for managing lookup tables.
/// Handles storage, versioning, diffs, merges, and binary compilation.

module Database

/// Initialize a new database in given directory.
creates database(path String) Database!

/// Load a lookup table by name.
loads(db Database, name String) DatabaseTable!

/// Save a lookup table. Rejects if version is stale.
saves(db Database, table DatabaseTable) Unit!

/// Compute diff between two tables.
diffs(old DatabaseTable, new DatabaseTable) TableDiff!

/// Apply diff to a table.
patches(table DatabaseTable, diff TableDiff) DatabaseTable!

/// Three-way merge with user-provided conflict resolver.
merges(base DatabaseTable, local TableDiff, remote TableDiff, resolver (Conflict) Resolution) MergeResult!

/// Compile table to binary lookup.
compiles(db Database, name String) Binary!

/// Load compiled binary from file.
loads_binary(path String) Binary!

/// Get integrity hash of a table.
integrity(table DatabaseTable) String!

/// Rollback to a previous version.
rollbacks(db Database, name String, version Integer) DatabaseTable!

/// List all versions of a table.
versions(db Database, name String) List<Version>!

end
```

## Types

- `Database` — database handle (directory-backed)
- `DatabaseTable` — a versioned lookup table (variants + columns + version number)
- `TableDiff` — structural diff between two tables
- `MergeResult` — merge outcome: `Ok(DatabaseTable)` or `Err(String)`
- `Binary` — compiled binary lookup table
- `Version` — version metadata (number, timestamp, hash)

### Conflict and Resolution (for custom merge)

```prove
/// A conflict detected during three-way merge.
type Conflict is
    ValueConflict(variant String, column String, local Value, remote Value)
    AdditionConflict(variant String, local List<Value>, remote List<Value>)
    SchemaConflict(base_columns List<String>, changed_columns List<String>)

/// How to resolve a single conflict.
type Resolution is
    KeepLocal
    KeepRemote
    UseValue(value Value)
    Reject(reason String)
```

See `future/database-merge-conflicts.md` for full conflict semantics.

## Concurrency Model

Version-based optimistic concurrency. Every `DatabaseTable` carries a version number incremented on each save. If the stored version has advanced past what the caller loaded, `saves` returns `Err(StaleVersion)`.

```prove
// Load version 3
table as DatabaseTable = loads(db, "http_status")!

// Another process saves version 4 in the meantime...

// This fails — our version 3 is stale
match saves(db, table)
    Ok(_) => log("Saved")
    Err(StaleVersion(_, _)) =>
        // Reload, re-apply changes, retry
        fresh as DatabaseTable = loads(db, "http_status")!
        // ...
```

No file locking. No blocking. Stale writes fail fast.

## Implementation

Uses existing parser/AST infrastructure from the compiler to read and write `.prv` files containing `:[Lookup]` type definitions.

### Storage Layout

```
database_dir/
    http_status/
        current.prv       # Current version
        versions/
            1.prv
            2.prv
            ...
```

## Exit Criteria

- [ ] Database module in stdlib
- [ ] Version-based `saves` with stale rejection
- [ ] `diffs` / `patches` work for variant additions, removals, and value changes
- [ ] `merges` accepts user-provided resolver function
- [ ] `compiles` produces binary from table
- [ ] `integrity` / `versions` / `rollbacks` work
- [ ] Tests pass
- [ ] Docs updated: `stdlib.md` (Database module), `database-merge-conflicts.md` folded in or referenced
