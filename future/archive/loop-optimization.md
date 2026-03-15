# Loop Optimization Passes

## Problem Statement

The Prove compiler generates inefficient C code for loops that contain dead code or have trivial patterns. TCO-converted recursive functions produce `while(1)` loops that often contain:

1. **Dead value creation** — variables assigned but never read
2. **Trivial counting/accumulation** — loops that could be folded to O(1)
3. **Unnecessary temporaries** — self-assignments in TCO tail-continue blocks
4. **Verbose control flow** — `while(1) { if(cond) return; else { body; continue; } }` instead of `for` loops

### Example: Current TCO Output

A recursive function like:
```prv
reads count(n Integer, acc Integer) Integer
from
    match n <= 0
        True -> acc
        False -> count(n - 1, acc + 1)
```

Produces this C after TCO:
```c
int64_t prv_reads_count_Integer_Integer(int64_t n, int64_t acc) {
    while (1) {
        if ((n <= 0L)) {
            return acc;
        } else {
            int64_t _tmp0 = (n - 1L);
            int64_t _tmp1 = (acc + 1L);
            n = _tmp0;      // _tmp0 is unnecessary — could assign directly
            acc = _tmp1;
            continue;       // redundant at end of while(1)
        }
    }
}
```

The entire loop could be folded to `return acc + n;` — no loop needed.

## Goals

1. Detect loops where created values are never read
2. Fold trivial counting/accumulating loops to O(1) computations
3. Simplify control flow (while(1)+if -> for loop)
4. Eliminate unnecessary temporary variables
5. Preserve semantics for loops with actual side effects

## Analysis Required

### Value Flow Analysis

Determine if a value created in a loop is:
1. **Returned** from the loop function
2. **Used** in a subsequent computation
3. **Passed** to another function that uses it
4. **Never used** (dead code)

### Side Effect Detection

A loop has side effects if it:
- Performs I/O (print, read, file ops)
- Mutates global state
- Mutates a non-local variable
- Calls a function that has side effects

If a loop has no side effects and its result is based only on loop-invariant computations, it can be folded.

## Implementation Plan

### Phase 1: Value Usage Analysis in Optimizer

**Location:** `prove-py/src/prove/optimizer.py`

Add a new pass that analyzes value usage within loops:

```python
def _analyze_value_usage(self, module: Module) -> Module:
    """Analyze which values are used after creation."""
    # For each function:
    #   - Track which variables are written
    #   - Track which variables are read
    #   - Identify dead writes (written but never read)
    return module
```

**Key helper methods:**
```python
def _find_read_vars(self, stmts: list) -> set[str]:
    """Find all variables read in statements."""

def _find_written_vars(self, stmts: list) -> set[str]:
    """Find all variables written in statements."""

def _is_dead_write(self, var: str, stmts: list) -> bool:
    """Check if variable is written but never read."""
```

### Phase 2: Dead Code Detection in Loops

**Location:** `prove-py/src/prove/optimizer.py`

Detect loops where loop body has no side effects:

```python
def _loop_has_side_effects(self, loop: WhileLoop) -> bool:
    """Check if loop body performs observable actions."""
    # Check for:
    # - Function calls to I/O functions
    # - Mutations of non-local state
    # - Returns of non-accumulated values
    return True  # Conservative default

def _can_fold_loop(self, loop: WhileLoop, acc_var: str) -> bool:
    """Check if loop can be folded to O(1)."""
    # 1. Loop must have no side effects
    # 2. Accumulator must be updated by loop-invariant computation
    # 3. Must have clear termination condition
```

### Phase 3: Trivial Loop Folding

**Location:** `prove-py/src/prove/optimizer.py`

When a loop can be folded:

```python
def _fold_trivial_loop(self, loop: WhileLoop, acc_var: str) -> Expr:
    """Convert trivial loop to direct computation."""

    # Pattern 1: Loop just counts iterations
    # while(cond) { remaining--; acc++; }
    # -> acc + remaining

    # Pattern 2: Loop computes invariant
    # while(cond) { acc += f(invariant); remaining--; }
    # -> acc + f(invariant) * remaining
```

### Phase 4: Simplify Control Flow

**Location:** `prove-py/src/prove/_emit_stmts.py`

When emitting loops, simplify common patterns:

```python
def _emit_while_loop(self, wl: WhileLoop) -> None:
    # Detect while(1) { if (cond) return; else { body; continue; } }
    # Simplify to: for (;cond; ) { body }
```

## Patterns to Detect

### Pattern 1: Dead Value Creation
```prv
reads loop(data ByteArray, remaining Integer, acc Integer) Integer
from
    match remaining <= 0
        True -> acc
        False ->
            encoded = encode(data)  // Never used after this!
            loop(data, remaining - 1, acc + length(encoded))
```

### Pattern 2: Trivial Counter
```prv
reads count(n Integer, acc Integer) Integer
from
    match n <= 0
        True -> acc
        False -> count(n - 1, acc + 1)
```
-> `acc + n`

### Pattern 3: Loop-Invariant Accumulation
```prv
reads sum(data List<Integer>, n Integer, acc Integer) Integer
from
    match n <= 0
        True -> acc
        False -> sum(data, n - 1, acc + first(data))
```
-> `acc + first(data) * n`

## Files to Modify

### 1. `prove-py/src/prove/optimizer.py`

**Changes:**
- Add `_analyze_value_usage()` pass
- Add `_find_read_vars()`, `_find_written_vars()` helpers
- Add `_loop_has_side_effects()` detection
- Add `_can_fold_loop()` analysis
- Add `_fold_trivial_loop()` transformation

**New passes in `optimize()` method:**
```python
module = self._escape_analysis(module)
module = self._analyze_value_usage(module)      # NEW
module = self._loop_simplification(module)       # NEW
module = self._fold_trivial_loops(module)        # NEW
return module
```

### 2. `prove-py/src/prove/_emit_stmts.py`

**Changes:**
- Simplify control flow in `_emit_while_loop()`
- Remove redundant `continue` statements
- Optimize temporary variable emission

## Testing

### Unit Tests
1. Add tests for value usage analysis
2. Add tests for dead code detection in loops
3. Add tests for trivial loop folding
4. Ensure existing tests still pass

## Open Questions

1. **How conservative should we be?** Dead code elimination can change behavior if the created value has destructor side effects.

2. **How to handle region allocation?** If a dead value would have been allocated in a region, does skipping it cause issues?

3. **Interaction with TCO:** If a loop is already being converted to TCO, should we also try to fold it? (TCO produces the while(1) loops that these passes target, so yes — these passes run after TCO.)

4. **How to detect all side effects?** Need comprehensive list of functions with side effects (I/O, mutable state, etc.)

## Scope

This plan focuses on optimizations within single loops:
- Eliminating dead code (values created but never read)
- Folding loops whose result can be computed in O(1)
- Simplifying the control flow that TCO conversion produces

It does **not** cover multi-loop fusion (merging two loops over the same collection) or cross-function inlining.
