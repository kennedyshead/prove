# Optimizer Passes — V1.0 Gap 07

## Overview

The optimizer implements 8 passes (runtime deps, TCO, dead branch elimination,
comptime eval, small function inlining, DCE, memoization candidates, match
compilation). Three documented passes are missing: iterator fusion, copy elision,
and match-to-jump-tables.

## Current State

Working passes in `optimize()` (`optimizer.py:107–116`):

| Pass | Method | Line |
|------|--------|------|
| 0 | `_collect_runtime_deps` | 108 |
| 1 | `_tail_call_optimization` | 109, 138 |
| 2 | `_dead_branch_elimination` | 110, 313 |
| 3 | `_ct_eval_pure_calls` | 111, 373 |
| 4 | `_inline_small_functions` | 112, 578 |
| 5 | `_dead_code_elimination` | 113, 464 |
| 6 | `_identify_memoization_candidates` | 114, 827 |
| 7 | `_match_compilation` | 115, 953 |

Supporting classes:
- `class RuntimeDeps` (`optimizer.py:79`)
- `class MemoizationCandidate` (`optimizer.py:48`)
- `class MemoizationInfo` (`optimizer.py:57`)

## What's Missing

1. **Iterator fusion** — `map(filter(...))` fusing into a single-pass loop.
   Described in `archive/0.5-PLAN.md` Part 2 Phase 2. No code exists.

2. **Copy elision** — avoid copies when source value is not reused after the copy.
   Described in `archive/0.5-PLAN.md` Part 2 Phase 3. No code exists.

3. **Match to jump tables** — compile match expressions into efficient decision
   trees or jump tables for dense integer/enum matches. Described in
   `archive/0.5-PLAN.md` Part 2 Phase 4. Current match compilation
   (`_match_compilation` at `optimizer.py:953`) only merges consecutive match
   expressions — it does NOT generate jump tables.

4. **Doc fix** — `types.md` claims "Pure functions get automatic memoization and
   parallelism". Memoization candidates are identified and tables emitted, but
   parallelism is not implemented.

## Implementation

### Phase 1: Iterator fusion

1. Add a new pass `_iterator_fusion()` to `optimizer.py`.

2. Detect patterns where HOF calls are chained:
   - `map(filter(list, pred), func)` → single loop with conditional apply
   - `filter(map(list, func), pred)` → single loop with apply-then-test
   - `map(map(list, f), g)` → single loop with composed function

3. Rewrite the AST to replace the chain with a single `FunctionDef` containing
   the fused loop body.

4. The emitter already handles individual `map`/`filter` via HOF emission
   (`_emit_calls.py`); the fused version would emit a direct `for` loop in C.

### Phase 2: Copy elision

1. Add a new pass `_copy_elision()` to `optimizer.py`.

2. Perform liveness analysis on local variables to determine whether a value
   is used after it is passed to a function or assigned to another variable.

3. If a value is not used after the copy point, mark it for move semantics
   instead of copy. This builds on the linear types work from gap02 (which
   must be completed first for `_moved_vars` field-path tracking).

4. In the emitter, when a value is marked for move, emit direct pointer
   transfer instead of `memcpy`/`prove_string_copy`.

### Phase 3: Match to jump tables

1. Extend `_match_compilation()` to analyze match expressions for jump-table
   eligibility:
   - Subject is integer or enum type
   - Arms are contiguous or near-contiguous values
   - No complex patterns (guards, nested destructuring)

2. For eligible matches, rewrite the AST to annotate the match as "jump table".

3. In `_emit_stmts.py`, when emitting a jump-table-annotated match:
   - Emit a C `switch` statement (which GCC/Clang optimize to jump tables)
   - For sparse integer matches, emit a lookup table + indirect branch

### Phase 4: Documentation fix

1. Update `types.md` to clarify: "Pure functions get automatic memoization
   [candidates identified and lookup tables emitted]. Parallelism is planned
   but not yet implemented."

## Files to Modify

| File | Change |
|------|--------|
| `optimizer.py:107–116` | Add 3 new passes to `optimize()` |
| `optimizer.py` (new methods) | `_iterator_fusion()`, `_copy_elision()`, `_match_compilation()` extension |
| `_emit_stmts.py` | Jump table emission for annotated match expressions |
| `_emit_calls.py` | Fused loop emission for fused iterator chains |
| `docs/types.md` | Fix memoization/parallelism claim |

## Exit Criteria

- [ ] `map(filter(list, p), f)` fuses into single-pass loop
- [ ] Copy elision avoids unnecessary string/list copies for dead values
- [ ] Dense integer/enum matches emit C `switch` statements
- [ ] Optimizer pass ordering: fusion and elision run before existing DCE pass
- [ ] Tests: unit tests for each new pass (before/after AST comparison)
- [ ] Tests: e2e test showing fused loop in generated C
- [ ] Doc fix: `types.md` parallelism claim qualified
