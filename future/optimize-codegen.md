# Optimize C Code Generation

## Problem Statement

The current Prove compiler generates C code with significant runtime overhead for algorithms that use `Array<Boolean>` and `Table<Value>` data structures. This is evident in the primes benchmark:

**Current Generated Code Issues:**
1. **Unnecessary runtime safety** — Type/bounds/null checks the compiler already guarantees
2. **Excessive reference counting** — Every `prove_retain()`/`prove_release()` call adds overhead
3. **Generic data structures** — Uses `Prove_Array*` and `Prove_Table*` with dynamic dispatch
4. **Recursive functions without optimization** — Tail recursion emits loops but retains overhead
5. **Unused includes** — 16+ headers included, many unused
6. **Unused memoization tables** — Declared but never used

### Compiler-First Principle

Per the Prove design philosophy:
> **The compiler is the primary safety mechanism. The C runtime is a last resort.**

Since Prove's type system already guarantees:
- **Bounds safety** — Array indices are validated at compile time
- **Null safety** — Non-null types cannot be null
- **Type correctness** — Tags are verified by the checker

The generated C code in `--release` mode should skip all these runtime checks.

**Performance Impact:**
- Current: 0.243s for primes benchmark (UPPER_BOUND = 5,000,000)
- Optimized: 0.057s (~4x faster)
- The generated code also produces incorrect output (numbers not matching prefix)

## Goals

1. Detect high-performance patterns in the AST and emit optimized C
2. Replace generic Prove runtime structures with native C equivalents
3. Maintain semantic equivalence with original Prove code
4. Add compiler flags to enable/disable optimizations
5. Preserve debuggability and error messages

## Optimization Strategies

The key insight: **since Prove's compiler already guarantees type safety, the generated C only needs these guarantees in debug mode.**

### Runtime Checks to Elide in Release Mode

| Check | When Safe to Remove | Current Overhead |
|-------|---------------------|------------------|
| Array bounds | Compiler validates index range | Function call + branch |
| Null pointer | `!` types guarantee non-null | Function call + branch |
| Type tags | Checker verifies at compile time | Function call + branch |
| Refcount inc/dec | Compiler tracks ownership | `prove_retain`/`prove_release` |
| Division by zero | `requires` contracts or literals | Runtime guard |

### How It Works

**Debug mode (default):**
```c
// Full safety checks enabled
if (idx >= array->length) prove_panic("bounds");
prove_retain(array);
```

**Release mode (`-DPROVE_RELEASE`):**
```c
// Compiler already guaranteed idx is valid
// No bounds check needed
```

The `-DPROVE_RELEASE` flag already exists in the runtime but isn't fully utilized by the emitter. This plan extends its usage.

### 1. BitArray for `Array<Boolean>:[Mutable]`

The compiler guarantees:
- Array index `n` is always valid (0 ≤ n ≤ limit)
- No out-of-bounds access

**Current:**
```c
Prove_Array* sieve = prove_array_new_bool(limit + 1, false);
bool current = prove_array_get_bool(sieve, n);  // runtime bounds check
prove_array_set_mut_bool(sieve, n, false);       // runtime bounds check + retain
```

**Optimized (release mode):**
```c
typedef struct {
    uint8_t* data;
    size_t size;
} BitArray;

static inline void bitarray_set(BitArray* ba, size_t idx, bool val) {
    ba->data[idx >> 3] = (ba->data[idx >> 3] & ~(1 << (idx & 7))) | (val << (idx & 7));
}

static inline bool bitarray_get(BitArray* ba, size_t idx) {
    return (ba->data[idx >> 3] >> (idx & 7)) & 1;
}
// No bounds checks - compiler guarantees idx < size
```

**Implementation:**
- Add detection in `_emit_types.py` for `Array<Boolean>:[Mutable]`
- Emit `BitArray` struct definition instead of `Prove_Array*`
- Replace `prove_array_get_bool` → `bitarray_get`
- Replace `prove_array_set_mut_bool` → `bitarray_set`
- Eliminate `prove_retain`/`prove_release` for these types

### 2. Native Trie for Digit-Keyed Tables

**Current:**
```c
Prove_Table* trie = prove_table_new();
Prove_Table* child = prove_value_as_object(prove_option_unwrap(prove_table_get(digit_key, node)));
Prove_Table* updated = prv_transforms_trie_insert_digits_Table_String_Integer_Integer(trie, digits, 0, str_len);
```

**Optimized:**
```c
typedef struct TrieNode {
    struct TrieNode* children[10];  // Digit keys 0-9
    bool is_end;
} TrieNode;

static TrieNode* trie_node_new(void) { ... }
static void trie_insert(TrieNode* root, int64_t num) { ... }
```

**Implementation:**
- Add detection for `Table<Value>` where:
  - Keys are single-character digits (0-9)
  - Value type is `Table<Value>` (nested structure)
- Emit native `TrieNode` struct
- Replace table operations with direct array access

### 3. Tail Recursion → Iteration with Region Scope Elimination

**Current:**
```c
Prove_Array* prv_transforms_atkin_step1_x_Array_Integer_Integer(Prove_Array* sieve, int64_t x, int64_t limit) {
    prove_retain(sieve);
    while (1) {
        if (((x * x) > limit)) {
            return sieve;
        } else {
            Prove_Array* updated = prv_transforms_atkin_step1_y_Array_Integer_Integer_Integer(sieve, x, 1L, limit);
            prove_retain(updated);  // Unnecessary
            // ... continue with tmp assignments
        }
    }
}
```

**Optimized:**
```c
static void atkin_sieve(BitArray* sieve, int64_t limit) {
    int64_t sqrt_limit = sqrt(limit);
    for (int64_t x = 1; x <= sqrt_limit; x++) {
        for (int64_t y = 1; y <= sqrt_limit; y++) {
            // Direct bit operations, no function calls
        }
    }
}
```

**Implementation:**
- Enhance optimizer's TCO pass to:
  1. Inline function bodies completely
  2. Convert nested loops to single flat loop
  3. Eliminate all `prove_retain`/`prove_release` calls in hot paths

### 4. Smart Include Generation

**Current:** 16 includes, many unused
**Optimized:** Only emit includes that are actually used

```python
# In c_emitter.py
def _emit_includes(self) -> list[str]:
    needed = set()
    # Scan AST for needed runtime functions
    # Only emit headers that provide those functions
```

## Files to Modify

### Core Emitter Changes

1. **`prove-py/src/prove/_emit_types.py`**
   - Add `BitArray` type detection and emission
   - Add `TrieNode` type detection and emission
   - Modify `map_type()` to return native C types for special cases

2. **`prove-py/src/prove/_emit_exprs.py`**
   - Replace `prove_array_get_bool` → `bitarray_get`
   - Replace `prove_array_set_mut_bool` → `bitarray_set`
   - Remove `prove_retain` calls for BitArray types

3. **`prove-py/src/prove/_emit_stmts.py`**
   - Optimize variable declarations for native types
   - Remove reference counting for optimized types

4. **`prove-py/src/prove/_emit_calls.py`**
   - Skip retain/release for optimized types
   - Inline small functions that operate on BitArray/Trie

5. **`prove-py/src/prove/c_emitter.py`**
   - Add `--release` or `--optimize` flag handling
   - Add pattern detection for optimization opportunities
   - Add native type definitions emission

### Optimizer Changes

6. **`prove-py/src/prove/optimizer.py`**
   - Enhance TCO to fully inline and flatten recursive patterns
   - Add pattern matching for:
     - Sieve of Atkin algorithm structure
     - Trie building/search patterns
   - Add "hot path" analysis to identify optimization targets

### New Files

7. **`prove-py/src/prove/_emit_native_types.py`** (new)
   - All native C type definitions
   - Helper functions for BitArray, Trie
   - Pattern detection logic

## Implementation Phases

### Phase 1: Runtime Check Elision + BitArray (Low Risk) — DONE

1. **`-DPROVE_RELEASE` flag:** passed by `builder.py` when `optimize and not debug`
2. **`prove_bitarray.h`** added: inline `prove_bitarray_new/get/set` that bypass `memcpy` overhead
3. **Emitter rewrite:** `_bitarray_rewrite()` in `_emit_calls.py` rewrites `prove_array_new_bool`→`prove_bitarray_new`, `prove_array_get_bool`→`prove_bitarray_get`, `prove_array_set_mut_bool`→`prove_bitarray_set` in release mode
4. **Bounds check elision:** `prove_array.c` get/set functions now have `#ifndef PROVE_RELEASE` guards on bounds checks
5. **`release_mode` flag:** threaded from `builder.py` → `CEmitter.__init__` → mixins
6. Primes benchmark verified: 17 bitarray calls in generated C, runs correctly

### Phase 2: Include Cleanup (Low Risk)
1. Add dependency tracking for runtime functions
2. Only emit needed includes
3. Verify all tests still pass

### Phase 3: Native Trie (Medium Risk)
1. Detect digit-keyed table patterns
2. Emit `TrieNode` struct
3. Replace table get/has/add with direct access
4. Handle edge cases (non-digit keys)

### Phase 4: TCO Enhancement (Medium Risk)
1. Extend optimizer to fully inline recursive patterns
2. Eliminate unnecessary retain/release in hot paths
3. Add algorithm-specific optimizations

### Phase 5: Benchmark Validation
1. Run all existing tests
2. Benchmark performance improvements
3. Verify correctness against reference implementations

## Compiler Flags

```toml
# prove.toml
[optimize]
enabled = true                    # Enable all optimizations
release = true                    # Enable -DPROVE_RELEASE
bitarray = true                   # Use native bit arrays
trie = true                       # Use native trie for digit tables  
inline-recursive = true           # Inline tail-recursive functions
strip-includes = true             # Only emit needed includes
elide-checks = true               # Remove runtime checks (compiler guarantees safety)
```

Or command line:
```bash
prove build src/main.prv --release --optimize=full
prove build src/main.prv --optimize=bitarray,trie,elide-checks
```

**How `-DPROVE_RELEASE` works:**
- `prove_array_get_bool()` → inline macro with no bounds check
- `prove_table_get()` → direct hash access, no null check
- `prove_retain()` → no-op (or minimized)
- Division guards → only for variable denominators

## Compatibility Considerations

1. **Debug mode** — Keep original slow path for debugging
2. **Error messages** — Must still show original Prove source locations
3. **Foreign function interface** — Optimize only pure Prove code
4. **Type safety** — Generated C must still be type-safe

## Testing Plan

1. **Unit tests** — Existing tests must pass
2. **Benchmark tests** — Primes, fib, etc. should show improvement
3. **Correctness tests** — Output must match reference implementations
4. **Performance regression** — Track benchmark times over changes

## Open Questions

1. Should optimizations be enabled by default in `--release` mode?
2. How to handle `Table<Value>` that has mixed key types?
3. What's the minimum optimization threshold to enable auto-optimization?
4. How to expose these as user-tunable options?

## References

- Current benchmark: `benchmarks/primes/`
- Optimized reference: `benchmarks/primes/optimized_primes.c`
- C runtime: `prove-py/src/prove/runtime/`
