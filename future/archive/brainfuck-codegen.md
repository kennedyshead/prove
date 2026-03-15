# Brainfuck Benchmark C Emitter Optimization

## Problem Statement

The Brainfuck benchmark (`benchmarks/brainfuck/`) generates slow C code due to:

1. **Tape implemented as Prove_Array** - Every cell access is a function call (`prove_array_get_int`/`prove_array_set_mut_int`)
2. **Recursive parsing** - One function call per BF character instead of iterative loop
3. **Nested match chains** - eval_dispatch uses if-else instead of switch statement
4. **No operation fusion** - `++++` emits 4 separate opcodes instead of one with arg=4

**Current performance:** Slow due to function call overhead in hot loops.

## Relationship to Existing Plans

This builds on `optimize-codegen.md`:
- Extends the **BitArray** concept to **plain uint8_t array** for tape
- Adds **switch statement** optimization for opcode dispatch
- Adds **operation fusion** optimization (compressing repeated ops)

## Goals

1. Emit tape as plain C array (`uint8_t tape[30000]`) instead of `Prove_Array*`
2. Use switch statement for opcode dispatch in eval loop
3. Fuse adjacent operations (`++++` → `op +4`)
4. Single-pass parsing instead of recursive character-by-character

## Implementation

### 1. Detect Fixed-Size Buffer Pattern

In `optimizer.py`, detect:
```prove
tape as Array<Integer>:[Mutable] = array(TAPE_SIZE, 0)
```

Where:
- `TAPE_SIZE` is a compile-time constant
- Array is only indexed, never resized
- Used in tight loop

### 2. Emit as Plain C Array

In `_emit_exprs.py`, add pattern:

**Current:**
```c
Prove_Array* tape = prove_array_new_int(TAPE_SIZE, 0);
int64_t val = prove_array_get_int(tape, ptr);  // function call
prove_array_set_mut_int(tape, ptr, val);       // function call
```

**Optimized:**
```c
static uint8_t tape[TAPE_SIZE];  // stack/static, no allocation
uint8_t val = tape[ptr];         // direct array access
tape[ptr] = val;                 // direct array access
```

### 3. Switch Statement for Opcode Dispatch

The `eval_dispatch` function already uses `match` on `op_type`. Ensure it emits as C switch:

**Current:**
```c
if (op_type == 0) { ... } else if (op_type == 1) { ... } // etc
```

**Optimized:**
```c
switch (op_type) {
    case 0: // Inc
        tape[ptr] = (tape[ptr] + op_arg) & 255;
        pc++;
        break;
    case 1: // Dec
        tape[ptr] = (tape[ptr] - op_arg + 256) & 255;
        pc++;
        break;
    case 2: // Right
        ptr += op_arg;
        pc++;
        break;
    // ...
}
```

### 4. Operation Fusion

Add optimization pass to fuse:
- `++++` (4x Inc) → `Inc(4)`
- `----` (4x Dec) → `Dec(4)`  
- `>>>>` (4x Right) → `Right(4)`
- `<<<<` (4x Left) → `Left(4)`

### 5. Single-Pass Iterative Parsing

Replace recursive parsing:
```prove
transforms parse_char(...) 
  terminates: src_len - src_idx
```

With iterative:
```prove
transforms parse(source String) Array<Integer>
  // Single while loop, no recursion
```

## Files to Modify

| File | Change |
|------|--------|
| `optimizer.py` | Add `_optimize_brainfuck_patterns()` pass |
| `_emit_exprs.py` | Add `_emit_array_as_c_buffer()` detection |
| `_emit_stmts.py` | Ensure switch for integer match dispatch |

## Benchmark Validation

```bash
# Before optimization
time ./build/brainfuck

# After optimization  
time ./build/brainfuck
```

Expected: **10-50x speedup** from plain C array access alone.
