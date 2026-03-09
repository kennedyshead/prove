# Escape Analysis Design — Prerequisite for Gap 03

## Problem

Gap 03 (memory regions) needs to route temporary allocations through
`prove_region_alloc` instead of arena/malloc. Region-allocated values are freed
when `prove_region_exit` is called at function exit. This means region allocation
is only safe for values that do NOT escape the function scope.

The emitter needs a way to determine, at code generation time, whether a value
escapes its enclosing function.

## What "Escapes" Means

A value escapes a function if any of these hold:

1. **Returned** — the value is part of the function's return expression
2. **Stored in a parameter** — the value is written into a mutable parameter's field
3. **Stored in a global** — the value is assigned to module-level state
4. **Passed to an escaping function** — the value is passed to a function that
   stores it beyond the call (e.g., `list_append(list, value)` where `list` outlives
   the current scope)

A value does NOT escape if:

1. It is consumed within the same expression (e.g., intermediate string concat)
2. It is passed to a function that only reads it (pure function, borrow parameter)
3. It is used only in local variable assignments within the function

## Implementation

**Location**: Optimizer (new pass after type checking, before emission)

**Granularity**: Per-variable - tracks which local variables escape

**Conservatism**: Defaults to "escapes" (safe but fewer region allocations)

### Architecture

1. **EscapeInfo class** (`optimizer.py`): Tracks escape information per function
   - `mark_escapes(func_name, var_name)`: Mark a variable as escaping
   - `escapes(func_name, var_name)`: Check if a variable escapes (conservative)
   - `is_noescape_call(func_name, call_name)`: Check if a call is pure

2. **Escape analysis pass** (`optimizer.py:_escape_analysis`):
   - Analyzes each function body
   - Collects local variables
   - Marks variables that escape (passed to non-pure functions, assigned to mutable params)

3. **Integration**:
   - Optimizer collects escape info and makes it available via `get_escape_info()`
   - Builder passes escape info to CEmitter
   - CEmitter can use this info to decide allocation strategy

### Known Pure Functions

The analysis tracks a set of known pure functions that don't cause escape:
- `string.length`, `string.is_empty`, `string.to_upper`, `string.to_lower`
- `string.trim`, `string.reverse`
- `list.length`, `list.is_empty`, `list.first`, `list.last`
- `list.sum`, `list.product`
- `table.length`

## Remaining Work

To fully implement region-based allocation:

1. **Runtime changes**: Create region-aware allocation functions (e.g., `prove_list_new_region(region, capacity)`) or add init functions to allocate structs in region before passing to functions

2. **Emitter integration**: Use escape info to:
   - Generate region enter/exit at function boundaries
   - Use region allocation for non-escaping allocations

3. **Function boundary handling**: Add region enter at function start and region exit at all return points

## Status

**Implemented**: Escape analysis infrastructure in optimizer

The analysis pass runs during optimization and collects escape information.
The infrastructure is in place but region allocation integration requires
additional runtime and emitter changes.
