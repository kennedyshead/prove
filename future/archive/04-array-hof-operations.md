# Array\<T\> HOF Operations

**Depends on:** `array-type-and-sequence-rename.md` fully implemented.

## Motivation

Once `Array<T>` exists, users will naturally want `map`/`filter`/`reduce`/`each` on it.
The current `Sequence` (List) HOF functions require a `Prove_List*` input and cannot
operate on `ProveArray*` without a full conversion. For numeric workloads this means
an unnecessary round-trip through boxed storage.

## The return-type problem

`map` and `reduce` are straightforward — output size equals input size (map) or is a
scalar (reduce). `filter` is the hard case: output size is unknown at compile time.

| Operation | Output type | Decision |
|---|---|---|
| `map(arr Array<T>, f) ` | `Array<U>` — same length | Allocate new `ProveArray` of same length |
| `reduce(arr Array<T>, init U, f)` | `U` — scalar | Accumulate directly, no allocation |
| `each(arr Array<T>, f)` | `Unit` | In-place loop, no allocation |
| `filter(arr Array<T>, p)` | **`Sequence<T>`** — unknown length | Return `Prove_List*`, not `ProveArray*` |

`filter` returns `Sequence<T>` because the output length is unknown. This is explicit
in the type — the user sees that filtering breaks out of `Array`-land.

## Stdlib API

```prove
module Array
  // ... existing functions ...

  /// Apply f to every element, returning a new array of the same length
  transforms map(arr Array<T>, f Function<T, U>) Array<U>
  binary

  /// Accumulate elements with f, starting from init
  reads reduce(arr Array<T>, init U, f Function<U, T, U>) U
  binary

  /// Run f for each element; returns Unit
  outputs each(arr Array<T>, f Function<T, Unit>)
  binary

  /// Keep elements matching predicate; returns Sequence because length is unknown
  creates filter(arr Array<T>, p Function<T, Boolean>) Sequence<T>
  binary
```

## C runtime additions (`prove_array.h/.c`)

```c
// map: allocate new ProveArray of same length, apply fn to each element
ProveArray *prove_array_map(ProveArray *arr, void *(*fn)(void *));

// reduce: accumulate with binary fn starting from init
void *prove_array_reduce(ProveArray *arr, void *init, void *(*fn)(void *, void *));

// each: call fn for side effect on each element
void prove_array_each(ProveArray *arr, void (*fn)(void *));

// filter: output is Prove_List (unknown length)
Prove_List *prove_array_filter(ProveArray *arr, int64_t (*pred)(void *));
```

## Optimizer fusions

These patterns become fuseable once the Array HOF exists:

| Pattern | Fused form | Notes |
|---|---|---|
| `map(map(arr, f), g)` | single-pass `Array<U>` | compose f and g |
| `reduce(map(arr, f), init, g)` | single-pass scalar | map then accumulate |
| `each(map(arr, f), g)` | single-pass void | map then side-effect |
| `filter(map(arr, f), p)` | single-pass `Sequence<T>` | map then test |

Fusions follow the same `__fused_*` pattern as the existing `Sequence` fusions.
Extend `_fuse_iterators_in_expr` in `optimizer.py`.

## Emitter changes

`_emit_calls.py` dispatch: add `map`/`reduce`/`each`/`filter` overloads that check
whether the first argument is an `ArrayType`. If so, route to `_emit_array_hof_*`
methods. If `ListType`, use existing `_emit_hof_*` methods. Type-inference via
`_infer_expr_type(expr.args[0])`.

## Implementation order

1. C runtime functions above
2. Stdlib signatures in `stdlib/array.prv`
3. `stdlib_loader.py` registration
4. Emitter dispatch (type-check first arg in `_emit_hof_*` or add a pre-check)
5. Optimizer fusions
6. Tests: unit tests for each operation + e2e test showing `reduce(map(array(...), f), init, g)` runs in one pass

---

## Documentation & AGENTS Updates

When this work is implemented:

- **`docs/stdlib/table-list-store.md`** — Add a "Higher-Order Operations" section under
  Array with a table of `map`, `reduce`, `each`, `filter`, their signatures, and return
  types. Emphasize that `filter` returns `List<Value>` (not `Array<T>`) because output
  length is unknown, and explain the optimizer fusions available.
- **`AGENTS.md`** — Under `optimizer.py`, note: "Array HOF fusions — `map(map(...))`,
  `reduce(map(...))`, `filter(map(...))` — are fused by `_fuse_iterators_in_expr` using
  `__fused_array_*` runtime calls, analogous to existing Sequence fusions."
- Run `mkdocs build --strict` after editing the stdlib page.
