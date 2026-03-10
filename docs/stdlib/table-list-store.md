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

**Module:** `Store` — persistent key-value storage.

*Store is planned but not yet fully documented. Documentation will be added once the module is stable.*
