# Concurrency — V1.0 Gap 10

## Overview

Concurrency features (`par_map`, structured concurrency, `Async` effect type) are
documented in `design.md` and `syntax.md` but have zero implementation — no AST
nodes, no type system support, no runtime primitives. This is the largest gap.
Structured concurrency (Phase 3) and Windows support are post-1.0; everything
else is V1.0.

## Current State

- `docs/design.md` mentions `par_map` and structured concurrency
- `docs/syntax.md` mentions effect types with CamelCase (`IO`, `Fail`, `Async`)
- No `par_map` or parallel/concurrent references anywhere in `prove-py/src/`
- No `EffectType` class in `types.py`
- No concurrency runtime files
- The async verbs plan (`future/store/impl01-async-verbs.md`) covers store-
  specific async but is separate from general concurrency

## What's Missing

1. **`par_map` runtime** — parallel map operation over lists
2. **Structured concurrency** — typed, no data races
3. **`Async` effect type** — effect types in the type system
4. **Doc fix** — `syntax.md` claims "Effects: CamelCase (IO, Fail, Async)" but no
   effect types exist

## Implementation

### Assessment: What's realistic for V1.0?

Full structured concurrency is a large feature. Recommended V1.0 scope:

- **V1.0**: `par_map` as a single, safe concurrency primitive + effect type scaffolding
- **Post-1.0**: Full structured concurrency, async verbs, complex effect composition

### Phase 1: Effect type scaffolding

1. Add `EffectType` class to `types.py` representing effects like `IO`, `Fail`, `Async`.

2. Effects annotate function return types: `transforms foo(x Integer) Integer & Async`
   means "pure function with async effect".

3. In the checker, track effect propagation: if `foo` has effect `Async`, callers
   of `foo` must also declare `Async` (or be in an async context).

4. For V1.0, effects are informational — they produce warnings when violated but do
   not block compilation. This lets the infrastructure exist without requiring all
   code to be effect-annotated.

### Phase 2: `par_map` runtime

1. Design decision: **process-based** parallelism (not threads).
   - Prove's functional model (no shared mutable state) maps naturally to processes
   - Process isolation prevents data races by construction
   - Use `fork()` on Linux/macOS (Windows support is post-1.0)

2. Add `prove_par_map.c/h` to the runtime:
   - `prove_par_map(list, func, num_workers)` — splits list into chunks, forks
     worker processes, applies func to each chunk, collects results
   - Worker communication via shared memory or pipes
   - Fallback to sequential `map` if `num_workers == 1` or fork unavailable

3. In the emitter, emit `prove_par_map()` calls when the optimizer identifies
   `map()` calls on large lists with pure functions.

4. Add `STDLIB_RUNTIME_LIBS` entry and `_RUNTIME_FUNCTIONS` mapping in `c_runtime.py`.

### Phase 3: Structured concurrency primitives (post-1.0)

Deferred to post-1.0:

1. Task spawning and joining
2. Cancellation propagation
3. Error handling across concurrent tasks
4. Resource cleanup on task failure
5. Windows `par_map` support

### Phase 4: Documentation fix

1. Update `syntax.md` to document `& Async` syntax and clarify that effect types
   produce warnings (not errors) for V1.0.

2. Update `design.md` concurrency section to reflect actual implementation scope
   (Linux/macOS `par_map` + effect scaffolding for V1.0; structured concurrency
   and Windows support post-1.0).

## Files to Modify

| File | Change |
|------|--------|
| `types.py` | Add `EffectType` class |
| `checker.py` | Effect propagation checking |
| `parser.py` | `& Effect` syntax on return types |
| `c_emitter.py` | `par_map` emission |
| `prove_par_map.c/h` (new) | Parallel map runtime |
| `c_runtime.py` | Add runtime metadata for par_map |
| `docs/syntax.md` | Fix effect type claim |
| `docs/design.md` | Update concurrency section |

## Exit Criteria

### V1.0 minimum (Phases 1–2)

- [ ] `EffectType` class exists in type system
- [ ] Effect propagation tracked (warnings for violations)
- [ ] `par_map` runtime compiles and runs on Linux/macOS
- [ ] `par_map` falls back to sequential for single worker
- [ ] Tests: C runtime tests for `par_map`
- [ ] Tests: e2e test with `par_map` example
- [ ] Doc fix: `syntax.md` and `design.md` reflect actual concurrency scope

### Post-1.0 (Phase 3)

- [ ] Structured concurrency primitives
- [ ] Cancellation propagation
- [ ] Cross-task error handling
- [ ] Windows `par_map` support
