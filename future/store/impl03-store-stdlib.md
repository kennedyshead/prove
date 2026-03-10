# impl03: Store Stdlib

## Overview

General-purpose stdlib module for managing lookup tables (`:[Lookup]` types). Provides storage, versioning, diffs, merges, and compilation to lookup tables.

This module is infrastructure — it knows nothing about what the lookup tables contain. Domain-specific logic (ML weights, user data, configuration) is built on top by application code.

## Module

```prove
/// Store for managing lookup tables.
/// Handles storage, versioning, diffs, merges, and binary compilation.

module Store

/// Initialize a new store in given directory.
creates store(path String) Store!

/// Load a lookup table by name.
loads(db Store, name String) StoreTable!

/// Save a lookup table. Rejects if version is stale.
saves(db Store, table StoreTable) Unit!

/// Compute diff between two tables.
diffs(old StoreTable, new StoreTable) TableDiff!

/// Apply diff to a table.
patches(table StoreTable, diff TableDiff) StoreTable!

/// Three-way merge of two diffs against a base table.
transforms merge(base StoreTable, local TableDiff, remote TableDiff) MergeResult

/// Three-way merge with user-provided conflict resolver.
transforms merge(base StoreTable, local TableDiff, remote TableDiff, resolver Verb<Conflict, Resolution>) MergeResult

/// Compile table to binary lookup.
compiles(db Store, name String) Binary!

/// Load compiled binary from file.
loads_binary(path String) Binary!

/// Get integrity hash of a table.
integrity(table StoreTable) String!

/// Rollback to a previous version.
rollbacks(db Store, name String, version Integer) StoreTable!

/// List all versions of a table.
versions(db Store, name String) List<Version>!

end
```

## Types

- `Store` — store handle (directory-backed)
- `StoreTable` — a versioned lookup table (variants + columns + version number)
- `TableDiff` — structural diff between two tables
- `MergeResult` — merge outcome: `Ok(StoreTable)` or `Err(String)`
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

See `future/store-merge-conflicts.md` for full conflict semantics.

## Concurrency Model

Version-based optimistic concurrency. Every `StoreTable` carries a version number incremented on each save. If the stored version has advanced past what the caller loaded, `saves` returns `Err(StaleVersion)`.

```prove
// Load version 3
table as StoreTable = loads(db, "http_status")!

// Another process saves version 4 in the meantime...

// This fails — our version 3 is stale
match saves(db, table)
    Ok(_) => log("Saved")
    Err(StaleVersion(_, _)) =>
        // Reload, re-apply changes, retry
        fresh as StoreTable = loads(db, "http_status")!
        // ...
```

No file locking. No blocking. Stale writes fail fast.

## Implementation

Uses existing parser/AST infrastructure from the compiler to read and write `.prv` files containing `:[Lookup]` type definitions.

### Storage Layout

```
store_dir/
    http_status/
        current.prv       # Current version
        versions/
            1.prv
            2.prv
            ...
```

## Exit Criteria

- [x] Store module in stdlib
- [x] Version-based `saves` with stale rejection
- [x] `diffs` / `patches` work for variant additions, removals, and value changes
- [x] `merge` accepts user-provided resolver function via `Verb<Conflict, Resolution>`
- [x] `compiles` produces binary from table
- [x] `integrity` / `versions` / `rollbacks` work
- [x] Tests pass
- [x] Docs updated: `stdlib.md` (Store module), `store-merge-conflicts.md` folded in or referenced
- [x] Add Store to the Language Tour on the home page (index.md) — spotlight as a unique feature
