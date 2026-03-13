# Array\<T\> Safe (Bounds-Checked) Access

**Depends on:** `array-type-and-sequence-rename.md` fully implemented.

## Motivation

The base `Array` plan provides unchecked `get` and `set` — no bounds check, no error
on out-of-range index. This is appropriate for hot paths where the programmer has
proven correctness (e.g. inside a fused loop). However, user-facing code that computes
indices dynamically needs a safe variant that returns `Option<T>` rather than producing 
undefined behaviour or a segfault.

## Design

Two access patterns, each with a distinct verb that signals intent:

```prove
module Array
  // ... existing functions ...

  /// Get element at index, or None if out of bounds
  reads get_safe(arr Array<T>, idx Integer) Option<T>
  binary

  /// Set element at index; returns None if out of bounds
  transforms set_safe(arr Array<T>, idx Integer, val T) Option<Array<T>>
  binary
```

The existing `get`/`set` remain — they are the unchecked fast path. Safe variants
are opt-in by name.

## C runtime additions (`prove_array.h/.c`)

```c
// Returns NULL on out-of-bounds (caller wraps in Option)
void *prove_array_get_safe(ProveArray *arr, int64_t idx);

// Copy-on-write set; returns NULL on out-of-bounds
ProveArray *prove_array_set_safe(ProveArray *arr, int64_t idx, void *val);
```

The bounds check is `idx < 0 || idx >= arr->length`.

## Checker

`get_safe` returns `Option<T>` — callers handle via `match`.

## When to add this

Add when a concrete user program needs safe array access with dynamic indices. Until
then the unchecked variants + programmer discipline (loop bounds) are sufficient.
Good trigger: the first e2e test that uses `get` with a runtime-computed index that
could be out of range.

---

## Documentation & AGENTS Updates

When this work is implemented:

- **`docs/stdlib/table-list-store.md`** — Add `get_safe` and `set_safe` rows to the
  Array Access and Mutation tables. Add an example showing the `match` pattern for
  safe index access and when to prefer it over the unchecked `get`/`set`.
- **`AGENTS.md`** — Update the Stdlib section: `Array` module now has 6 access/mutation
  functions (`get`, `set`, `get_safe`, `set_safe`, plus mutable variants). Note that
  `get_safe` returns `Option<T>`, requiring `match` at call sites.
- Run `mkdocs build --strict` after editing the stdlib page.
