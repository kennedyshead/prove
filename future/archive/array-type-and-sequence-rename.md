# Array\<T\> Type + Sequence Rename + Range Fusion

## Motivation

`List<T>` stores every element as a boxed `void*`. For numeric workloads this means
heap allocation per element, pointer indirection on every access, and no possibility
of in-place mutation. The primality benchmark takes ~50s vs ~0.1s for equivalent Zig
because `range(3, 5_000_001)` materialises 5M boxed integers.

This plan introduces `Array<T>` — contiguous, unboxed storage — and fuses `range`
into HOF pipelines so the intermediate list is never allocated.

---

## Part 1 — Rename `List` module to `Sequence`

### Why

`List` is being freed up so `Array` functions can live alongside the other collection
operations in the stdlib without name collision. The rename is also semantically
cleaner: a boxed, growable, heterogeneous collection *is* more of a sequence than an
array.

### Scope

| Item | Change |
|---|---|
| `stdlib/list.prv` | Renamed to `stdlib/sequence.prv`; module declaration becomes `module Sequence` |
| `stdlib_loader.py` | `_register_module("List", ...)` → `_register_module("Sequence", ...)` |
| User import syntax | `List creates range` → `Sequence creates range` |
| `optimizer.py` `RuntimeDeps` | Update `STDLIB_RUNTIME_LIBS` key if it references `"List"` |
| Docs + examples | Update all `.prv` files that import from `List` |

No changes to function names, signatures, or the C runtime (`prove_list.h/.c`).
The runtime struct stays `ProveList`; the rename is purely at the Prove language layer.

### Not in scope

No backward-compatibility alias. This is pre-1.0; a clean break is fine.

---

## Part 2 — `Array<T>` type

### Semantics

`Array<T>` is a fixed-size, contiguous, unboxed collection. Size is set at creation
and does not change. Elements are stored directly (e.g. `int64_t[]` for `Integer`),
not as `void*`.

`:[Mutable]` enables in-place `set`. Without it, `Array<T>` is read-only after
creation.

### Conservative stdlib API (expand only when a concrete use case arises)

```prove
module Array
  narrative: """Fixed-size unboxed arrays for numeric and boolean workloads."""

  /// Create an array of given size, every element initialised to default
  creates array(size Integer, default T) Array<T>
  binary

  /// Get element at index; no bounds check in release builds
  reads get(arr Array<T>, idx Integer) T
  binary

  /// Return copy of array with element at idx replaced by val
  transforms set(arr Array<T>, idx Integer, val T) Array<T>
  binary

  /// In-place mutation — only valid on Array<T>:[Mutable]
  transforms set(arr Array<T>:[Mutable], idx Integer, val T) Array<T>:[Mutable]
  binary

  /// Number of elements
  reads length(arr Array<T>) Integer
  binary

  /// Copy array contents into a new List<T>
  creates to_sequence(arr Array<T>) List<T>
  binary

  /// Copy list contents into a new Array<T>
  creates from_sequence(items List<T>, default T) Array<T>
  binary
```

No `map`, `filter`, or `reduce` on `Array` in this version. Those return `List` by
nature (output size unknown for `filter`) and add complexity. Add later if needed.

### C runtime (`runtime/prove_array.h` + `runtime/prove_array.c`)

```c
typedef struct {
    void    *data;        // flat buffer: int64_t*, bool*, ProveString** etc.
    int64_t  length;
    int64_t  elem_size;   // bytes per element
} ProveArray;

ProveArray *prove_array_new(int64_t length, int64_t elem_size, void *default_val);
void       *prove_array_get(ProveArray *arr, int64_t idx);
ProveArray *prove_array_set(ProveArray *arr, int64_t idx, void *val);  // copy-on-write
void        prove_array_set_mut(ProveArray *arr, int64_t idx, void *val);  // in-place
int64_t     prove_array_length(ProveArray *arr);
```

`prove_array_set` (immutable path) allocates a new `ProveArray` with a copied buffer.
`prove_array_set_mut` writes directly into `arr->data`. The checker enforces that
`set_mut` is only reachable through `Array<T>:[Mutable]`.

### Type system (`types.py`)

Add `ArrayType(element: Type)` as a distinct type, parallel to `ListType`.
`types_compatible(ArrayType(T), ArrayType(T))` — exact match only, no coercion to
`ListType` implicitly.

### Checker

- `set` on plain `Array<T>` → resolves to copy-on-write `prove_array_set`
- `set` on `Array<T>:[Mutable]` → resolves to in-place `prove_array_set_mut`
- Passing `Array<T>:[Mutable]` to a `validates`/`reads`/`transforms` parameter that
  is not `:[Mutable]` → E341 (existing mutable borrow check)

### C emitter

`map_type(ArrayType(T))` → `CTypeInfo(decl="ProveArray*", is_pointer=True)`.
Accessors emit the correct element cast based on `T` (same pattern as existing
`prove_list_get` casts in fused emitters).

---

## Part 3 — Range fusion

### Problem

`range(start, end)` materialises a full `ProveList` of integers before any HOF runs.
For `range(3, 5_000_001)` that is 5M allocations before a single predicate is tested.

### Solution

When the optimizer detects `range(...)` as the source of a fused HOF pipeline, replace
the materialised list with a C `for` loop that drives the pipeline directly. No
`ProveList` is allocated.

### Patterns to fuse (optimizer pass, extends existing `_fuse_iterators_in_expr`)

| Source pattern | Fused name | Loop structure |
|---|---|---|
| `filter(range(s,e), p)` | `__fused_filter_range` | `for i in [s,e): if p(i) push i` |
| `map(range(s,e), f)` | `__fused_map_range` | `for i in [s,e): push f(i)` |
| `each(range(s,e), g)` | `__fused_each_range` | `for i in [s,e): g(i)` |
| `reduce(range(s,e), init, g)` | `__fused_reduce_range` | `for i in [s,e): acc = g(acc,i)` |
| `filter(filter(range(s,e), p1), p2)` | combine existing `__fused_filter_filter` + range source | handled by two-pass fusion: range → filter_filter |

The range source fusions compose with the existing HOF fusions because the outer
pattern recognises `__fused_*_range` as the inner arg. No special-casing needed beyond
the range-source rules above.

### Emitter changes (`_emit_calls.py`)

Each `__fused_*_range` emitter:
1. Emits `int64_t {start} = {s}; int64_t {end} = {e};`
2. Opens `for (int64_t {i} = {start}; {i} < {end}; {i}++) {`
3. Inlines predicate / function via existing `_emit_fused_lambda_inline`
4. Returns result temp (list pointer for filter/map, scalar for reduce, void for each)

No `ProveList` is created for the range itself. The output list (`filter`/`map`
results) is still a `ProveList` — that is a separate concern.

---

## Implementation order

1. **Sequence rename** — low risk, mechanical, unblocks clean naming for everything else
2. **Range fusion** — pure optimizer + emitter work, no type system changes, high
   performance payoff, can be validated against the existing benchmark immediately
3. **`ProveArray` C runtime** — standalone, no compiler changes needed yet
4. **`ArrayType` in type system** — `types.py` + `c_types.py`
5. **Stdlib signatures** — `stdlib/array.prv` + `stdlib_loader.py`
6. **Checker enforcement** — `:[Mutable]` + `set` dispatch
7. **C emitter paths** — emit `ProveArray` accessors with correct casts

---

## Create examlpe in examples folder

We need to make sure that the code compiles and work as intended!

## Update docs and AGENTS.md

Dont forget to update the docs and AGENTS.md when done

## Out of scope for this plan

Each item has its own follow-up plan:

- **`map`/`filter`/`reduce` on `Array<T>`** → `array-hof-operations.md`
  Return type for `filter` is unclear (output length unknown); defer until a
  concrete use case drives the design.

- **Typed `ProveList`** — superseded by `Array<T>`. No follow-up plan needed;
  `Array` covers the use case without retrofitting the existing `Prove_List` runtime.

- **Sieve of Eratosthenes** → `sieve-of-eratosthenes.md`
  Expressible in user code once `Array<Boolean>:[Mutable]` + `set` + stepped `range`
  exist. Also identifies the stepped `range(start, end, step)` blocker.

- **Bounds-checked `get` / `Result`-returning variant** → `array-safe-access.md`
  Conservative default is unchecked access. Safe variants (`get_safe`, `get_or_fail`)
  added when the first program needs dynamic index access.


