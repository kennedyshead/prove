# Loop Simplification and Dead Code Elimination

## Problem Statement

The Prove compiler generates inefficient C code for loops that contain dead code or have trivial patterns. This is evident in the brainfuck benchmark where the generated C code contains loops that create objects but never use them:

### Current Issues

**1. Dead code in loop body:**
```c
// Encode loop - creates encoded string but never uses it
int64_t prv_reads_encode_loop_ByteArray_Integer_Integer(...) {
    while (1) {
        if ((remaining <= 0L)) {
            return acc;
        } else {
            Prove_String* encoded = prove_parse_base64_encode(data);  // CREATED BUT NEVER USED
            prove_retain(encoded);
            // ... continue with remaining - 1, acc + length(encoded)
        }
    }
}

// Decode loop - creates decoded but never uses it
int64_t prv_reads_decode_loop_String_Integer_Integer(...) {
    while (1) {
        if ((remaining <= 0L)) {
            return acc;
        } else {
            Prove_ByteArray* decoded = prove_parse_base64_decode(encoded);  // CREATED BUT NEVER USED
            prove_retain(decoded);
            // ... continue with remaining - 1, acc + 1
        }
    }
}
```

**2. Unnecessary temporary assignments:**
```c
Prove_String* _tmp1 = data;
int64_t _tmp2 = (remaining - 1L);
int64_t _tmp3 = (acc + prove_text_length(encoded));
data = _tmp1;           // Useless self-assignment
remaining = _tmp2;
acc = _tmp3;
```

**3. Complex control flow that could be simplified:**
```c
while (1) {
    if ((remaining <= 0L)) {
        return acc;
    } else {
        // ... body
        continue;  // continue at end of while(1) is redundant
    }
}
```

### Expected Optimizations

**1. Dead code elimination in loops:**
```c
// BEFORE: Creates encoded, retains it, computes its length
// AFTER: Just compute the result directly without allocation
int64_t encode_result = prove_text_length(encoded) * remaining;
return acc + encode_result;
```

**2. Trivial loop folding:**
```c
// BEFORE: Loop that just counts
// AFTER: O(1) computation
return acc + remaining;  // No loop needed
```

**3. Simplified control flow:**
```c
// BEFORE: while(1) { if... continue }
// AFTER: for loop
for (int64_t remaining = initial_remaining; remaining > 0; remaining--) {
    // actual work
}
```

## Goals

1. Detect loops where created values are never read
2. Fold trivial counting/accumulating loops to O(1) computations
3. Simplify control flow (while(1)+if → for loop)
4. Eliminate unnecessary temporary variables
5. Preserve semantics for loops with actual side effects

## Analysis Required

### Value Flow Analysis

Need to determine if a value created in a loop is:
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
    # → acc + remaining
    
    # Pattern 2: Loop computes invariant
    # while(cond) { acc += f(invariant); remaining--; }
    # → acc + f(invariant) * remaining
```

### Phase 4: Simplify Control Flow

**Location:** `prove-py/src/prove/_emit_stmts.py`

When emitting loops, simplify common patterns:

```python
def _emit_while_loop(self, wl: WhileLoop) -> None:
    # Detect while(1) { if (cond) return; else { body; continue; } }
    # Simplify to: for (;cond; ) { body }
```

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

## Patterns to Detect

### Pattern 1: Dead Value Creation
```prv
verb encode(data ByteArray, remaining Integer, acc Integer) Integer
from
    if remaining <= 0
        acc
    else
        encoded = encode(data)  # Never used!
        encode(data, remaining - 1, acc + length(encoded))
```

### Pattern 2: Trivial Counter
```prv
verb count(n Integer, acc Integer) Integer
from
    if n <= 0
        acc
    else
        count(n - 1, acc + 1)
```
→ `acc + n`

### Pattern 3: Loop-Invariant Accumulation
```prv
verb sum(data List<Integer>, n Integer, acc Integer) Integer
from
    if n <= 0
        acc
    else
        // first(data) is loop-invariant
        sum(data, n - 1, acc + first(data))
```
→ `acc + first(data) * n`

## Testing

### Unit Tests
1. Add tests for value usage analysis
2. Add tests for dead code detection in loops
3. Add tests for trivial loop folding
4. Ensure existing tests still pass

### Benchmark Validation
1. Run brainfuck benchmark before/after
2. Compare generated C code
3. Verify output correctness

### Expected Results

**brainfuck benchmark:**
- Before: O(n) loop with allocations per iteration
- After: O(1) computation
- Speedup: Significant (eliminates 8192 base64 encode/decode calls)

## Relationship to Existing Plans

This plan complements:
- **json-optimize.md**: Focuses on fusing multiple loops over same collection
- **optimize-codegen.md**: Focuses on runtime check elision and native types

This plan focuses on:
- Eliminating dead code within single loops
- Folding loops that don't need to iterate

## Open Questions

1. **How conservative should we be?** Dead code elimination can change behavior if the created value has destructor side effects.

2. **How to handle region allocation?** If a dead value would have been allocated in a region, does skipping it cause issues?

3. **Interaction with TCO:** If a loop is already being converted to TCO, should we also try to fold it?

4. **How to detect all side effects?** Need comprehensive list of functions with side effects (I/O, mutable state, etc.)

## References

- Current benchmark: `benchmarks/brainfuck/`
- Optimizer passes: `prove-py/src/prove/optimizer.py`
- Loop emission: `prove-py/src/prove/_emit_stmts.py:_emit_while_loop()`
