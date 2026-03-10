---
title: Table, List & Store - Prove Standard Library
description: Table hash maps, List operations, and Store persistent storage in the Prove standard library.
keywords: Prove Table, Prove List, Prove Store, hash map, list operations
---

# Table, List & Store

## Table

**Module:** `Table` — hash map from `String` keys to values.

Defines a binary type: `Table<Value>` (the hash map).

| Verb | Signature | Description |
|------|-----------|-------------|
| `creates` | `new() Table<Value>` | Create an empty table |
| `validates` | `has(key String, table Table<Value>)` | True if key exists |
| `transforms` | `add(key String, value Value, table Table<Value>) Table<Value>` | Insert or update a key-value pair |
| `reads` | `get(key String, table Table<Value>) Option<Value>` | Look up value by key |
| `transforms` | `remove(key String, table Table<Value>) Table<Value>` | Delete a key from the table |
| `reads` | `keys(table Table<Value>) List<String>` | Get all keys |
| `reads` | `values(table Table<Value>) List<Value>` | Get all values |
| `reads` | `length(table Table<Value>) Integer` | Number of entries |

```prove
Table creates new, validates has, transforms add, reads get keys

reads lookup(name String, db Table<String>) String
from
    Error.unwrap_or(Table.get(name, db), "unknown")
```

---

## List

**Module:** `List` — operations on the built-in `List<Value>` type.

Some operations (contains, index, sort) require concrete element types and have
overloads for `List<Integer>` and `List<String>`.

### Query

| Verb | Signature | Description |
|------|-----------|-------------|
| `reads` | `length(items List<Value>) Integer` | Number of elements |
| `reads` | `first(items List<Value>) Option<Value>` | First element, or None |
| `reads` | `last(items List<Value>) Option<Value>` | Last element, or None |
| `reads` | `value(position Integer, items List<Value>) Value` | Element at position (0-based) |
| `validates` | `empty(items List<Value>)` | True if list has no elements |

### Search

| Verb | Signature | Description |
|------|-----------|-------------|
| `validates` | `contains(items List<Integer>, value Integer)` | Check if integer is in list |
| `validates` | `contains(items List<String>, value String)` | Check if string is in list |
| `reads` | `index(items List<Integer>, value Integer) Option<Integer>` | Find position of integer |
| `reads` | `index(items List<String>, value String) Option<Integer>` | Find position of string |

### Transform

| Verb | Signature | Description |
|------|-----------|-------------|
| `transforms` | `slice(items List<Value>, start Integer, end Integer) List<Value>` | Sub-list from start to end |
| `transforms` | `reverse(items List<Value>) List<Value>` | Reverse element order |
| `transforms` | `sort(items List<Integer>) List<Integer>` | Sort integers ascending |
| `transforms` | `sort(items List<String>) List<String>` | Sort strings lexicographically |

### Create

| Verb | Signature | Description |
|------|-----------|-------------|
| `creates` | `range(start Integer, end Integer) List<Integer>` | Integer sequence [start, end) |

```prove
List reads length first, transforms sort reverse, creates range

reads top_three() List<Integer>
from
    nums as List<Integer> = List.range(1, 100)
    List.reverse(List.sort(nums))
```

---

## Store

**Module:** `Store` — persistent key-value storage with versioning and compilation.

Defines four binary types: `Store` (storage handle), `StoreTable` (table handle), `TableDiff` (structural diff), `Version` (version record).

### Store Operations

| Verb | Signature | Description |
|------|-----------|-------------|
| `outputs` | `store(path String) Result<Store, Error>!` | Create a new store at a directory path |
| `validates` | `store(path String)` | True if store directory exists |

### Table Operations

| Verb | Signature | Description |
|------|-----------|-------------|
| `inputs` | `table(store Store, name String) Result<StoreTable, Error>!` | Load a table by name |
| `outputs` | `table(store Store, table StoreTable) Result<Unit, Error>!` | Save a table with optimistic concurrency |
| `validates` | `table(store Store, name String)` | True if table exists in store |

### Diff and Patch

| Verb | Signature | Description |
|------|-----------|-------------|
| `transforms` | `diff(old StoreTable, new StoreTable) TableDiff` | Compute structural diff between two tables |
| `transforms` | `patch(table StoreTable, diff TableDiff) StoreTable` | Apply a diff to a table |

### Merge

| Verb | Signature | Description |
|------|-----------|-------------|
| `transforms` | `merge(base StoreTable, local TableDiff, remote TableDiff) MergeResult` | Three-way merge (conflicts reported) |
| `transforms` | `merge(base StoreTable, local TableDiff, remote TableDiff, resolver Verb<Conflict, Resolution>) MergeResult` | Three-way merge with conflict resolver |
| `validates` | `merged(result MergeResult)` | True if merge succeeded without conflicts |
| `reads` | `merged(result MergeResult) StoreTable` | Get merged table from successful result |
| `reads` | `conflicts(result MergeResult) List<Conflict>` | Get conflict list from conflicted result |

Additional types: `Conflict` (conflict details), `Resolution` (resolver decision), `MergeResult` (merge outcome).

The 3-arg `merge` detects conflicts and returns them. The 4-arg overload passes each conflict to a resolver callback typed as [`Verb<Conflict, Resolution>`](../types.md#function-types-verb):

```prove
// Merge without resolver — conflicts returned in MergeResult
result as MergeResult = Store.merge(base, local_diff, remote_diff)

// Merge with lambda resolver — keep remote on all conflicts
result as MergeResult = Store.merge(base, local_diff, remote_diff, |c| KeepRemote)
```

### Lookup Compilation

| Verb | Signature | Description |
|------|-----------|-------------|
| `outputs` | `lookup(store Store, name String) Result<Unit, Error>!` | Compile a table to lookup format |
| `inputs` | `lookup(path String) Result<List<String>, Error>!` | Load a compiled lookup |

### Integrity and Versioning

| Verb | Signature | Description |
|------|-----------|-------------|
| `reads` | `integrity(table StoreTable) String` | Compute integrity hash of a table |
| `outputs` | `rollback(store Store, name String, version Integer) Result<StoreTable, Error>!` | Rollback to a previous version |
| `inputs` | `version(store Store, name String) Result<List<Version>, Error>!` | List all versions of a table |

```prove
Store outputs store, inputs table lookup, validates store table, transforms diff patch merge
Store reads integrity merged conflicts, outputs rollback, inputs version
Store validates merged, types Store StoreTable Conflict Resolution MergeResult

inputs load_table(path String, name String) StoreTable!
from
    db as Store = Store.store(path)!
    Store.table(db, name)!
```

### Store-Backed Lookup Types

A `[Lookup]` type with `runtime` instead of `where` is backed by a `StoreTable`. The type definition declares the column schema; data is populated at runtime. See [Store-Backed Lookup](../types.md#store-backed-lookup-runtime) for the type system details.

```prove
type Color:[Lookup] is String | Integer
  runtime

Store outputs store, inputs table, validates store table
    types Store StoreTable

main()!
from
    db as Store = store("/tmp/demo")!
    colors as Color = table(db, "colors")!
    row as Color = Color(Red, "red", 0xFF0000)
    add(colors, row)
    color as Integer = colors:"red"
    console(f"{color}")
```

The `table()` call returns a `StoreTable` which is transparently typed as `Color`. The column schema (String, Integer) is initialized from the type definition when the table is first loaded. Row construction `Color(Red, "red", 0xFF0000)` takes the variant name as first argument, followed by values matching each column type. The `colors:"red"` lookup resolves column indices at compile time.
