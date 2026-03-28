---
title: Table, List, Array & Store - Prove Standard Library
description: Table hash maps, List operations, Array fixed-size buffers, and Store persistent storage in the Prove standard library.
keywords: Prove Table, Prove List, Prove Array, Prove Store, hash map, list operations, array
---

# Table, List, Array & Store

## Table

**Module:** `Table` — hash map from `String` keys to values.

Defines a binary type: `Table<Value>` (the hash map).

| Verb | Signature | Description |
|------|-----------|-------------|
| `creates` | `new() Table<Value>` | Create an empty table |
| `validates` | `has(key String, table Table<Value>)` | True if key exists |
| `reads` | `add(key String, value Value, table Table<Value>) Table<Value>` | Insert or update a key-value pair |
| `reads` | `get(key String, table Table<Value>) Option<Value>` | Look up value by key |
| `reads` | `remove(key String, table Table<Value>) Table<Value>` | Delete a key from the table |
| `creates` | `keys(table Table<Value>) List<String>` | Get all keys |
| `reads` | `values(table Table<Value>) List<Value>` | Get all values |
| `creates` | `length(table Table<Value>) Integer` | Number of entries |
| `creates` | `table(v Value) Table<Value>` | Extract object content from a Value |

```prove
  Table creates new table keys validates has reads add remove get

reads lookup(name String, db Table<String>) String
from
    Error.unwrap_or(Table.get(name, db), "unknown")
```

---

## Array

**Module:** `Array` — fixed-size contiguous arrays with typed elements. Also accessible via the `Sequence` module alias.

`Array<T>` is a flat, unboxed buffer with a fixed length set at creation time. Elements are stored directly (no boxing), making it cache-friendly and suitable for numeric computation, sieves, bitfields, and working buffers.

Unlike `List<Value>`, an `Array<T>` has a concrete element type and a fixed size. The two modifiers that matter most:

- `Array<T>` (default) — **copy-on-write**: `set` returns a new array, leaving the original unchanged.
- `Array<T>:[Mutable]` — **in-place mutation**: `set` modifies the array directly and returns the same pointer. Use this for large working buffers updated in a tight loop.

### Construction

| Verb | Signature | Description |
|------|-----------|-------------|
| `creates` | `array(size Integer, default Boolean) Array<Boolean>` | Allocate a boolean array filled with `default` |
| `creates` | `array(size Integer, default Integer) Array<Integer>` | Allocate an integer array filled with `default` |
| `creates` | `array(size Integer, default Decimal) Array<Decimal>` | Allocate a decimal array filled with `default` |
| `creates` | `array(size Integer, default Boolean) Array<Boolean>:[Mutable]` | Allocate a mutable boolean array |
| `creates` | `array(size Integer, default Integer) Array<Integer>:[Mutable]` | Allocate a mutable integer array |
| `creates` | `array(size Integer, default Decimal) Array<Decimal>:[Mutable]` | Allocate a mutable decimal array |

The element type and mutability are inferred from context (the declared type of the receiving variable).

### Access

| Verb | Signature | Description |
|------|-----------|-------------|
| `reads` | `get(arr Array<Boolean>, idx Integer) Boolean` | Read element at index |
| `reads` | `get(arr Array<Integer>, idx Integer) Integer` | Read element at index |
| `creates` | `length(arr Array<T>) Integer` | Number of elements |

Both overloads work identically on mutable (`:[Mutable]`) and immutable arrays.

### Mutation

| Verb | Signature | Description |
|------|-----------|-------------|
| `reads` | `set(arr Array<Boolean>, idx Integer, val Boolean) Array<Boolean>` | Copy-on-write: return new array with element replaced |
| `reads` | `set(arr Array<Integer>, idx Integer, val Integer) Array<Integer>` | Copy-on-write: return new array with element replaced |
| `reads` | `set(arr Array<Boolean>:[Mutable], idx Integer, val Boolean) Array<Boolean>:[Mutable]` | In-place: modify array and return same pointer |
| `reads` | `set(arr Array<Integer>:[Mutable], idx Integer, val Integer) Array<Integer>:[Mutable]` | In-place: modify array and return same pointer |

The dispatch between copy-on-write and in-place is resolved by the array's type — no separate function name needed.

### Example — immutable (copy-on-write)

```prove
  Array creates array length
  Array reads get set

main() Result<Unit, Error>!
from
    flags as Array<Boolean> = array(5, false)
    flags2 as Array<Boolean> = set(flags, 2, true)   // flags unchanged
    size as Integer = length(flags2)
    val as Boolean = get(flags2, 2)
    console(f"size={size} element[2]={val}")
```

### Example — mutable (in-place)

```prove
  Array creates array
  Array reads get set

// Sieve of Eratosthenes: count primes up to limit
reads count_primes(limit Integer) Integer
from
    is_composite as Array<Boolean>:[Mutable] = array(limit + 1, false)
    marked0 as Array<Boolean>:[Mutable] = set(is_composite, 0, true)
    marked1 as Array<Boolean>:[Mutable] = set(marked0, 1, true)
    sieved as Array<Boolean>:[Mutable] = sieve_pass(marked1, 2, limit)
    count_true_false(sieved, 2, limit, 0)
```

The `:[Mutable]` annotation tells the compiler to use in-place mutation — no intermediate copies are allocated during the sieve loop.

### Conversion

Convert arrays to lists and extract CSV rows.

| Verb | Signature | Description |
|------|-----------|-------------|
| `creates` | `list(arr Array<Boolean>) List<Boolean>` | Copy array contents into a new list |
| `creates` | `list(arr Array<Integer>) List<Integer>` | Copy array contents into a new list |
| `creates` | `list(arr Array<Decimal>) List<Decimal>` | Copy array contents into a new list |
| `creates` | `list(csv Value<Csv>) List<List<String>>` | Extract CSV rows as a list of lists |
| `creates` | `list(v Value) List<Value>` | Extract array content from a Value |

The CSV overload requires importing the `Csv` type from `Parse`.

### Import aliases

`Array`, `Sequence`, and `List` all refer to the same module. The preferred alias depends on context:

- `Array` — when working with `Array<T>` (fixed-size buffers)
- `List` or `Sequence` — when working with `List<Value>` (dynamic lists)

```prove
// These are equivalent:
  Array creates array
  Sequence creates array
```

---

## List

**Module:** `List` — operations on the built-in `List<Value>` type.

Some operations (contains, index, sort) require concrete element types and have
overloads for `List<Integer>`, `List<String>`, `List<Float>`, and `List<Decimal>`.
Typed `first`/`last` overloads are also available for Float and Decimal lists.

### Query

| Verb | Signature | Description |
|------|-----------|-------------|
| `creates` | `length(items List<Value>) Integer` | Number of elements |
| `reads` | `first(items List<Value>) Option<Value>` | First element, or None |
| `reads` | `first(items List<Integer>) Option<Integer>` | First integer, or None |
| `reads` | `first(items List<String>) Option<String>` | First string, or None |
| `reads` | `first(items List<Float>) Option<Float>` | First float, or None |
| `reads` | `first(items List<Decimal>) Option<Decimal>` | First decimal, or None |
| `reads` | `last(items List<Value>) Option<Value>` | Last element, or None |
| `reads` | `last(items List<Integer>) Option<Integer>` | Last integer, or None |
| `reads` | `last(items List<String>) Option<String>` | Last string, or None |
| `reads` | `last(items List<Float>) Option<Float>` | Last float, or None |
| `reads` | `last(items List<Decimal>) Option<Decimal>` | Last decimal, or None |
| `reads` | `value(position Integer, items List<Value>) Option<Value>` | Element at position (0-based), or None |
| `validates` | `empty(items List<Value>)` | True if list has no elements |

### Search

| Verb | Signature | Description |
|------|-----------|-------------|
| `validates` | `contains(items List<Integer>, value Integer)` | Check if integer is in list |
| `validates` | `contains(items List<String>, value String)` | Check if string is in list |
| `validates` | `contains(items List<Float>, value Float)` | Check if float is in list |
| `validates` | `contains(items List<Decimal>, value Decimal)` | Check if decimal is in list |
| `creates` | `index(items List<Integer>, value Integer) Option<Integer>` | Find position of integer |
| `creates` | `index(items List<String>, value String) Option<Integer>` | Find position of string |
| `creates` | `index(items List<Float>, value Float) Option<Integer>` | Find position of float |
| `creates` | `index(items List<Decimal>, value Decimal) Option<Integer>` | Find position of decimal |

### Transform

| Verb | Signature | Description |
|------|-----------|-------------|
| `reads` | `slice(items List<Value>, start Integer, end Integer) List<Value>` | Sub-list from start to end |
| `reads` | `reverse(items List<Value>) List<Value>` | Reverse element order |
| `reads` | `sort(items List<Integer>) List<Integer>` | Sort integers ascending |
| `reads` | `sort(items List<String>) List<String>` | Sort strings lexicographically |
| `reads` | `sort(items List<Float>) List<Float>` | Sort floats ascending |
| `reads` | `sort(items List<Decimal>) List<Decimal>` | Sort decimals ascending |

### Create

| Verb | Signature | Description |
|------|-----------|-------------|
| `creates` | `range(start Integer, end Integer) List<Integer>` | Integer sequence [start, end) |
| `creates` | `range(start Integer, end Integer, step Integer) List<Integer>` | Integer sequence with step |

### Element Access

| Verb | Signature | Description |
|------|-----------|-------------|
| `reads` | `get(items List<Integer>, idx Integer) Integer` | Get integer element at index |
| `reads` | `get(items List<String>, idx Integer) String` | Get string element at index |
| `reads` | `get(items List<Float>, idx Integer) Float` | Get float element at index |
| `reads` | `get(items List<Decimal>, idx Integer) Decimal` | Get decimal element at index |
| `reads` | `get(items List<Value>, idx Integer) Value` | Get value element at index |
| `reads` | `get_safe(items List<Integer>, idx Integer) Option<Integer>` | Safe get integer at index |
| `reads` | `get_safe(items List<String>, idx Integer) Option<String>` | Safe get string at index |
| `reads` | `set(items List<Value>, idx Integer, val Value) List<Value>` | Return list with element replaced |
| `reads` | `remove(items List<Value>, idx Integer) List<Value>` | Return list with element removed |

```prove
  List creates length reads first sort reverse slice creates range

creates top_three() List<Integer>
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
| `creates` | `diff(old StoreTable, new StoreTable) TableDiff` | Compute structural diff between two tables |
| `reads` | `patch(table StoreTable, diff TableDiff) StoreTable` | Apply a diff to a table |

### Merge

| Verb | Signature | Description |
|------|-----------|-------------|
| `creates` | `merge(base StoreTable, local TableDiff, remote TableDiff) MergeResult` | Three-way merge (conflicts reported) |
| `creates` | `merge(base StoreTable, local TableDiff, remote TableDiff, resolver Verb<Conflict, Resolution>) MergeResult` | Three-way merge with conflict resolver |
| `validates` | `merged(result MergeResult)` | True if merge succeeded without conflicts |
| `creates` | `merged(result MergeResult) StoreTable` | Get merged table from successful result |
| `creates` | `conflicts(result MergeResult) List<Conflict>` | Get conflict list from conflicted result |

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
| `creates` | `integrity(table StoreTable) String` | Compute integrity hash of a table |
| `outputs` | `rollback(store Store, name String, version Integer) Result<StoreTable, Error>!` | Rollback to a previous version |
| `inputs` | `version(store Store, name String) Result<List<Version>, Error>!` | List all versions of a table |

```prove
  Store outputs store inputs table lookup validates store table creates diff merge merged conflicts integrity reads patch
  Store outputs rollback inputs version
  Store validates merged types Store StoreTable Conflict Resolution MergeResult

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

  Store outputs store inputs table validates store table
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
