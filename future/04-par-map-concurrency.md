# `par_map` Concurrency

**Status:** Exploring
**Roadmap:** Runtime scaffolding exists but is not callable from user code

## Problem

The C runtime has a complete `prove_par_map` implementation
(`prove_par_map.c/h`) that parallelises a map operation over a list using
pthreads, with automatic sequential fallback. However, there is no Prove-level
syntax or stdlib function that emits a call to this runtime, so users cannot
access parallel mapping.

## Goal

Expose `par_map` to Prove user code through a safe, verb-compatible interface
that preserves Prove's purity guarantees.

## Current State

### Runtime (`prove_par_map.c`)

- `prove_par_map(list, fn, num_workers)` — thread-pool parallel map.
- `Prove_MapFn` typedef: `void *(*)(void *)` — single element in, single out.
- Sequential fallback when `num_workers <= 1` or list is small.
- Graceful degradation: if `pthread_create` fails, that chunk runs sequentially.
- Non-pthreads fallback: always sequential.

### Builder (`builder.py:312`)

- Already links `-lpthread` unconditionally.

### C Runtime Registry (`c_runtime.py:446`)

- `prove_par_map` is registered in `_RUNTIME_FUNCTIONS`.

### What's Missing

- No Prove-level function signature for `par_map`.
- No checker or emitter path that generates `prove_par_map()` calls.
- No mechanism to convert a Prove pure function reference to a `Prove_MapFn`
  C function pointer.

## Design Considerations

### Where to Expose It

par_map(list, fn)` alongside existing `map`, `filter`, `reduce`.

### Purity Enforcement

The key safety invariant: `par_map` only accepts pure functions (`transforms`,
`validates`, `reads`, `creates`, `matches`). The checker already enforces verb
families — it must reject IO verbs (`inputs`, `outputs`, `streams`) and async
verbs (`detached`, `attached`, `listens`) in the function argument.

This is already partially handled: `HOF_BUILTINS` in `types.py:191` lists
`map`, `filter`, `reduce`, `each`. Adding `par_map` to this set enables the
existing HOF type-checking machinery.

### Worker Count

Two approaches:

1. **Automatic** — Runtime picks worker count based on available cores
   (`sysconf(_SC_NPROCESSORS_ONLN)`).
2. **User-specified** — `par_map(list List<Value>, verb Verb, workers Option<Integer>)` with optional third arg.

Automatic by default, optional override. The runtime already
supports `num_workers` parameter.

### Function Pointer Emission

The emitter must generate a C function pointer compatible with `Prove_MapFn`.
For monomorphic pure functions this is straightforward — the emitter already
generates top-level C functions for Prove functions. The challenge is:

- **Closures / captured variables** — `par_map` cannot safely share mutable
  state. Pure verbs guarantee no mutation, but captured read-only bindings
  still need to be threaded through somehow. The `Prove_MapFn` signature takes
  a single `void *` — closures would need a trampoline.
- **Generic functions** — Need monomorphised instantiation before taking the
  address.

### Minimum Viable Version

Start with the simplest case: `par_map` over a list with a named pure function
(no closures, no lambdas). This covers the primary use case and avoids the
closure complexity.

We need to create a plan for full support!

## Implementation Phases

### Phase 1: Checker

- Add `par_map` to `BUILTIN_FUNCTIONS` and `HOF_BUILTINS` in `types.py`.
- Infer return type: `par_map(List<A>, (A) -> B) -> List<B>`.
- Enforce: callback must be a named function with a pure verb.
- Optional third parameter: `Integer` for worker count.

### Phase 2: Emitter

- In `_emit_calls.py`, handle `par_map` call dispatch.
- Emit `prove_par_map(list_expr, fn_ptr, num_workers)`.
- For named functions, emit the function's C name directly as `fn_ptr`.
- Default `num_workers` to 0 (let runtime auto-detect; requires small runtime
  change to treat 0 as "auto").

### Phase 3: Runtime Enhancement

- Add auto-detect: when `num_workers == 0`, query CPU count.
- Consider minimum chunk size threshold (don't parallelise tiny lists).

### Phase 4: Closure Support (Future)

- Generate trampoline functions that carry captured bindings.
- Thread-local or per-chunk context passing.

## Open Questions

- Should `par_map` guarantee element ordering in the result? (Currently yes —
  the runtime pre-allocates output slots by index.)
- Should there be a `par_filter` or `par_reduce`? (Probably defer — map is
  the cleanest parallel primitive.)
- Should the optimizer auto-promote `map` to `par_map` for large lists?
  (Risky — changes semantics for side-effecting `each`. Only safe for pure
  verbs.)

## Files Likely Touched

- `types.py` — add `par_map` to `BUILTIN_FUNCTIONS`, `HOF_BUILTINS`
- `checker.py` — type inference for `par_map` calls
- `_check_calls.py` — call validation, purity enforcement
- `_emit_calls.py` — C code generation for `prove_par_map()`
- `c_runtime.py` — verify `prove_par_map` registration
- `prove_par_map.c` — add auto-detect for `num_workers == 0`
- `stdlib_loader.py` — if exposed via List module instead
- `optimizer.py` — `RuntimeDeps` to include `prove_par_map` when used
