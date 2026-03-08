# Comptime Execution — V1.0 Gap 01

## Overview

The comptime interpreter exists and handles constant-folding of pure calls in the
optimizer, but `comptime { ... }` blocks in user code are parsed without producing C
output. Build dependency tracking for comptime `read()` is not wired, and comptime
match for conditional compilation is not functional.

## Current State

Working pieces:

- `comptime` keyword lexed, parsed (`parser.py:1667–1702`), and type-checked (E410–E422)
- `ComptimeInterpreter` class (`interpreter.py:44`) with `evaluate()` and
  `evaluate_pure_call()` methods
- Optimizer pass 3 (`optimizer.py:111`) calls `_ct_eval_pure_calls` (`optimizer.py:373`)
  to fold pure calls with constant arguments
- `read()` function available in comptime context for file I/O
- `_eval_comptime()` method exists in emitter (`c_emitter.py:415`) with
  `_comptime_result_to_c()` (`c_emitter.py:436`)

## What's Missing

1. **Comptime block execution** — `comptime { ... }` blocks are parsed but emit no C
   code. The emitter's `_eval_comptime()` exists but is not called from statement
   emission paths.

2. **Build dependency tracking** — files accessed via comptime `read()` should become
   build dependencies so that changes trigger recompilation. Not wired into `builder.py`.

3. **Comptime match** — documented in `docs/compiler.md` as conditional compilation
   mechanism. No evidence of working implementation in the emitter.

## Implementation

### Phase 1: Wire comptime blocks in emitter

1. In `_emit_stmts.py`, add a handler for `ComptimeBlock` AST nodes that:
   - Creates a `ComptimeInterpreter` instance
   - Evaluates the block body
   - Converts results to C constants via `_comptime_result_to_c()`
   - Emits the constants as `#define` or `static const` declarations

2. In `c_emitter.py`, ensure `_eval_comptime()` is reachable from the statement
   emission dispatch.

### Phase 2: Build dependency tracking

1. Extend `ComptimeInterpreter` to record all file paths accessed via `read()` into
   a `dependencies: list[str]` attribute.

2. In `builder.py`, after running the optimizer (which calls the interpreter), collect
   `ComptimeResult.dependencies` and store them alongside the build artifacts.

3. On subsequent builds, check modification times of dependency files to determine
   whether recompilation is needed.

### Phase 3: Comptime match

1. Support `comptime match` as a conditional compilation mechanism:
   ```prove
   comptime match platform()
       "linux" => // emit linux-specific code
       "macos" => // emit macos-specific code
   ```

2. Evaluate the match expression at compile time, select the matching branch, and
   only emit C code for that branch. Non-matching branches are discarded entirely.

3. Ensure the parser accepts `match` inside `comptime` blocks.

## Files to Modify

| File | Change |
|------|--------|
| `_emit_stmts.py` | Add `ComptimeBlock` handler in statement dispatch |
| `c_emitter.py:415` | Ensure `_eval_comptime()` integrates with statement emission |
| `interpreter.py:44` | Add `dependencies` tracking to `ComptimeInterpreter` |
| `builder.py` | Wire dependency file list into build staleness check |
| `optimizer.py:373` | Pass dependency info through from `_ct_eval_pure_calls` |

## Exit Criteria

- [ ] `comptime { ... }` blocks execute at compile time and produce C constants
- [ ] A working example demonstrating comptime block execution
- [ ] Files read via comptime `read()` tracked as build dependencies
- [ ] Comptime match selects branches at compile time
- [ ] `module_features_demo` example no longer expected-to-fail for comptime
- [ ] Tests: unit tests for comptime block emission, e2e test with comptime example
- [ ] Docs: `compiler.md` comptime section verified against implementation
