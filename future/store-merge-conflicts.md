# Store Merge Conflicts

## Overview

Conflict handling when modifying lookup tables managed by the Store stdlib. The Store operates on general-purpose lookup tables (any `:[Lookup]` type), not domain-specific data.

## Design Principle

The Store stdlib provides conflict **detection** and **infrastructure**. It does not implement domain-specific resolution logic. Resolution is either:

1. **Default** — version-based optimistic concurrency (reject stale writes)
2. **Custom** — user-provided resolver via algebraic match

## Version-Based Concurrency (Default)

Every `StoreTable` carries a version number. When saving, the caller must provide the version they loaded. If the stored version has advanced, the write is rejected with an `Error`.

```prove
// Load at version 3
ast as StoreTable = load(db, "http_status")!   // version: 3

// Meanwhile, another process saves version 4...

// This fails — version 3 is stale
saves(db, ast)!
// => Err(StaleVersion(expected: 4, got: 3))
```

The caller handles this at the call site with a match:

```prove
match saves(db, ast)
    Ok(_) => log("Saved")
    Err(StaleVersion(expected, got)) =>
        // Reload and retry, or report to user
        fresh as StoreTable = load(db, "http_status")!
        merged as StoreTable = apply_my_changes(fresh)
        saves(db, merged)!
```

This is standard optimistic concurrency control. No locks, no blocking. Stale writes fail fast.

## Custom Conflict Resolution

For cases where the caller wants to merge rather than reject, the Store provides a `merges` function that accepts a user-written resolver. The resolver is a function that pattern-matches on `Conflict` — an algebraic type describing what diverged.

### Conflict Types

```prove
/// A conflict detected during three-way merge.
type Conflict is
    /// Same variant modified differently in local and remote.
    ValueConflict(variant String, column String, local Value, remote Value)
    /// Same variant name added by both sides with different values.
    AdditionConflict(variant String, local List<Value>, remote List<Value>)
    /// Schema structure changed (columns added/removed/reordered).
    SchemaConflict(base_columns List<String>, changed_columns List<String>)
```

### Resolution Type

```prove
/// How to resolve a single conflict.
type Resolution is
    /// Keep the local (ours) value.
    KeepLocal
    /// Keep the remote (theirs) value.
    KeepRemote
    /// Provide a custom merged value.
    UseValue(value Value)
    /// Reject — abort the merge with an error.
    Reject(reason String)
```

### User-Written Resolver

The resolver is a plain Prove function. The user writes it, the Store calls it:

```prove
/// Example: resolver for an HttpStatus lookup table.
transforms resolve_http(conflict Conflict) Resolution
from
    match conflict
        // For value conflicts, prefer the remote version
        ValueConflict(_, _, _, _) => KeepRemote
        // Accept new variants from both sides (use remote values)
        AdditionConflict(_, _, _) => KeepRemote
        // Never allow schema changes via merge
        SchemaConflict(_, _) => Reject("Schema migration required")
```

### Merge Call

```prove
// Three-way merge with custom resolver
result as MergeResult = merges(base, local_diff, remote_diff, resolve_http)!

match result
    Ok(merged_ast) => saves(db, merged_ast)!
    Err(rejected) => log("Merge rejected: " + rejected.reason)
```

## Conflict Categories

### 1. Value Conflict

Same variant, same column, different values in local and remote diffs:

```
Base:      Ok | "OK" | 200
Local:     Ok | "OK" | 201      (changed code)
Remote:    Ok | "Success" | 200  (changed name)
```

Produces two `ValueConflict` entries — one for column 1 ("OK" vs "Success"), one for column 2 (201 vs 200). Each resolved independently by the user's resolver.

### 2. Addition Conflict

Both sides add a variant with the same name but different values:

```
Local adds:   Timeout | "Timeout" | 408
Remote adds:  Timeout | "Request Timeout" | 408
```

Produces an `AdditionConflict`. If both sides add variants with different names, they merge cleanly — no conflict.

### 3. Schema Conflict

Column structure changed (columns added, removed, or reordered):

```
Base:    type HttpStatus is String Integer
Local:   type HttpStatus is String Integer Boolean
```

Produces a `SchemaConflict`. This cannot be resolved by value-level merging — it requires explicit migration outside the merge system.

## Non-Conflicts (Clean Merges)

These cases merge automatically without invoking the resolver:

- **Same change both sides** — local and remote made the identical edit. No conflict.
- **Non-overlapping additions** — local adds `Timeout`, remote adds `Gone`. Both included.
- **Non-overlapping edits** — local edits `Ok`, remote edits `NotFound`. Both applied.

## Edge Cases

### Empty Store

Loading from a path that doesn't exist:
- `load` returns `Err(NotFound)` — caller decides whether to create

### Malformed Data

Corrupted or unparseable lookup table:
- `load` returns `Err(ParseError)` — caller handles
- Store never silently accepts bad data

### Concurrent Modification

Multiple processes modifying the same table:
- Default: version-based rejection handles this naturally
- Custom merge: caller can retry with fresh base after rejection

### Binary Invalidation

Binary out of sync with source lookup table:
- `compiles` always produces a fresh binary from the current AST
- Caller is responsible for recompiling after merge
- `integrity` hash allows verifying binary matches source

## Implementation Phases

### Phase 1: Version-Based Saves

- Every `StoreTable` tracks a version number
- `saves` rejects stale versions with `Err(StaleVersion)`
- Full recompile after each save

### Phase 2: Three-Way Merge with Custom Resolver

- `diffs` computes structural diff between two ASTs
- `merges` accepts a user-provided resolver function
- Resolver receives `Conflict`, returns `Resolution`

### Phase 3: Integrity and Rollback

- `integrity` returns hash of current AST state
- `versions` lists version history
- `rollbacks` restores a previous version

## References

- impl02: Binary lookup tables (`:[Lookup]` modifier)
- impl03: Store stdlib (module API)
- impl06: Dynamic runtime modification (runtime use of Store)
