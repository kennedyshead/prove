# Memory Regions for Local Temporaries — V1.0 Gap 03

## Overview

The region runtime (`prove_region.c/h`) exists and per-function enter/exit calls are
emitted, but no temporary allocations are routed through regions. All allocation still
uses the global arena or malloc. Regions should provide fast bump-allocation for
function-local temporaries that are automatically freed on function exit.

## Current State

Working pieces:

- `prove_region.c` and `prove_region.h` runtime with `enter`/`exit`/`alloc` API
  (`prove-py/src/prove/runtime/prove_region.c`)
- `_global_region` created during runtime init (`prove_runtime.c`)
- Per-function region scoping: `prove_region_enter(prove_global_region())` emitted at
  function entry (`c_emitter.py:595`) and `prove_region_exit(prove_global_region())`
  at function exit (`c_emitter.py:619`), inside `_emit_function()` (`c_emitter.py:548`)
- Region is listed in `_CORE_FILES` (`c_runtime.py`) — always included

## What's Missing

1. **`prove_region_alloc` for temporaries** — no temporary allocations are routed
   through region allocation. String concatenation intermediates, expression
   temporaries, and format buffers all use arena or malloc.

2. **Emitter integration** — the emitter never calls `prove_region_alloc()` in
   generated code; it only emits the enter/exit scaffolding.

3. **Early return cleanup** — if a function returns early (error propagation with `!`,
   match branch return), region exit must still be called.

## Implementation

### Phase 1: Identify temporary allocation sites

Audit the emitter to find all places where temporary values are allocated:

1. **String concatenation** — `_emit_exprs.py` emits `prove_string_concat()` which
   allocates a new string. Intermediate concatenations in chains like `a + b + c`
   create temporaries that are dead after the full expression.

2. **Format string interpolation** — builds temporary buffers for formatted output.

3. **Intermediate list/option construction** — `prove_list_new()`, `prove_option_some()`
   calls that produce values consumed immediately by another call.

4. **Match expression temporaries** — intermediate values in match arm expressions.

### Phase 2: Route temporaries through region allocator

**Prerequisite**: escape analysis design must be completed first. See
`future/escape-analysis.md` for the design problem — determining which values escape
function scope requires a separate analysis pass before this phase can be implemented.

1. In `_emit_exprs.py`, for each identified temporary allocation site, replace the
   arena/malloc call with `prove_region_alloc(prove_global_region(), size)`.

2. Add a `prove_region_alloc_string()` helper in `prove_region.c` that combines
   allocation + string copy for the common case.

3. Ensure region-allocated values are NOT used after the function returns (they are
   freed by `prove_region_exit`). Values that escape the function must use arena.
   The escape analysis pass determines which values escape.

### Phase 3: Early return cleanup

1. In `_emit_stmts.py`, ensure every early return path (error propagation `!`,
   explicit `return`, match branch returns) emits `prove_region_exit()` before
   the `return` statement.

2. Consider a `goto cleanup` pattern: emit a cleanup label before the function's
   normal `prove_region_exit()`, and have early returns jump to it.

### Phase 4: Nested region support

1. For deeply nested scopes (match arms with their own temporaries), consider
   nested region enter/exit pairs for finer-grained cleanup.

2. Evaluate whether per-scope regions add enough benefit vs. per-function regions.

## Files to Modify

| File | Change |
|------|--------|
| `_emit_exprs.py` | Route temporary allocations through `prove_region_alloc` |
| `_emit_stmts.py` | Ensure early return paths call `prove_region_exit` |
| `c_emitter.py:595,619` | May need adjustment for cleanup label pattern |
| `prove_region.c` | Add `prove_region_alloc_string()` and other typed helpers |
| `prove_region.h` | Declare new helper functions |

## Exit Criteria

- [ ] String concatenation intermediates use region allocation
- [ ] Format interpolation buffers use region allocation
- [ ] Early return paths (error propagation, match returns) call region exit
- [ ] Values that escape function scope still use arena (not region)
- [ ] Tests: C runtime tests for region alloc/free lifecycle
- [ ] Tests: e2e test demonstrating region allocation in generated code
- [ ] No memory leaks in valgrind for programs using region-allocated temporaries
