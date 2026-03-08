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

## Design Questions

These must be resolved before implementing gap03 Phase 2:

1. **Where does the analysis live?** Options:
   - In the optimizer (new pass after type checking, before emission)
   - In the emitter itself (inline analysis during code generation)
   - In the checker (annotate AST nodes with escape information)

2. **Granularity**: per-variable? per-expression? per-allocation-site?

3. **Conservatism**: when unsure, should the analysis default to "escapes" (safe
   but fewer region allocations) or "does not escape" (more region allocations
   but risk of use-after-free)? Answer: must default to "escapes" for safety.

4. **Interaction with borrow inference** (gap02): if `_infer_param_borrows()` has
   already determined that a parameter is read-only, can we trust that values
   passed to it do not escape? This would allow more values to be region-allocated.

## Status

Not yet designed. This must be resolved before gap03 Phase 2 can be implemented.
Gap 03 Phase 1 (identifying temporary allocation sites) and Phase 3 (early return
cleanup) can proceed without this.
