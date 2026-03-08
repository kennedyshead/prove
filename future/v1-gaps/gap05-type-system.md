# Type System Gaps — V1.0 Gap 05

## Overview

The type system handles refinement types, modifiers, generics, and single/binary lookup
types. Missing features include multi-type lookup, row polymorphism for algebraic types,
and true static rejection of refinement violations (currently emits runtime checks).

## Current State

Working pieces:

- `RefinementType` class (`types.py:50`) with `where` constraints (range, regex, comparison)
- Type modifiers: `Integer:[16 Unsigned]`, `String:[ASCII 255]`, `Mutable`, `Own`
- Generic types: `GenericInstance` (`types.py:57`), `TypeVariable` (`types.py:63`),
  `ListType` (`types.py:74`)
- Single-type lookup: `_lookup_tables` dict on Checker (`checker.py:205`), registration
  from `LookupTypeDef` body (`checker.py:492–493`)
- Binary lookup: `_validate_binary_lookup()` (`checker.py:1038`)
- Lookup access: `_check_lookup_access_expr()` (`_check_types.py:539`) with
  E376/E377/E378 errors (`_check_types.py:548–598`)
- Refinement validation: runtime checks emitted in `_emit_stmts.py:279–438`,
  `_emit_refinement_validation()` (`_emit_stmts.py:446`)

## What's Missing

1. **Multi-type lookup** — `type X:[Lookup] is String | Integer where ...` documented
   in `types.md`. Not implemented.

2. **Row polymorphism** — mentioned in `types.md` algebraic types section. No
   implementation evidence.

3. **Static refinement rejection** — docs claim "compiler rejects invalid values
   statically" but actual implementation inserts runtime checks. True static analysis
   (rejecting `Port(-1)` at compile time without runtime overhead) not implemented.

## Implementation

### Phase 1: Static refinement analysis

This is the highest-priority type system gap because docs make a strong claim about it.

1. In the checker, after resolving a refinement type assignment like
   `port as Port = 8080`, check whether the assigned value is a compile-time constant.

2. If constant: evaluate the refinement constraint at check time. If it fails, emit
   an error immediately (no runtime check needed). If it passes, mark the assignment
   as "statically verified" so the emitter can skip the runtime check.

3. If non-constant: fall through to the existing runtime check emission.

4. This is a best-effort optimization — it handles the common case of literal
   assignments and `comptime` results. Runtime checks remain for dynamic values.

### Phase 2: Multi-type lookup

1. Extend `LookupTypeDef` parsing and checking to allow union base types:
   `type X:[Lookup] is String | Integer`.

2. In `_check_lookup_access_expr()`, resolve lookup access against multiple
   column types, returning the appropriate result type.

3. In the emitter, generate lookup code that handles heterogeneous value columns.

### Phase 3: Row polymorphism

1. Design: row polymorphism allows algebraic types to be extended with additional
   variants without breaking existing pattern matches. A function accepting
   `type Shape is Circle | Square | ...rest` handles known variants and passes
   unknown ones through.

2. Add `...rest` syntax to algebraic type definitions in the parser.

3. In the checker, treat `...rest` as a type variable that captures unmatched
   variants. Exhaustiveness checking must account for the rest row.

4. In the emitter, generate dispatch code that handles the open variant set.

## Files to Modify

| File | Change |
|------|--------|
| `checker.py:492` | Static refinement check for constant assignments |
| `_check_types.py:539` | Multi-type lookup resolution |
| `_emit_stmts.py:446` | Skip runtime check when statically verified |
| `types.py` | Row type representation |
| `parser.py` | `...rest` row syntax in algebraic types |
| `docs/types.md` | Fix claims about static rejection; document row polymorphism |
| `docs/index.md` | Fix claim about static rejection |

## Exit Criteria

- [ ] Constant refinement assignments checked at compile time (no runtime check emitted)
- [ ] Non-constant refinements still produce runtime checks
- [ ] Multi-type lookup types parse, type-check, and emit correctly
- [ ] Row polymorphism syntax parses and type-checks
- [ ] Tests: unit tests for static refinement analysis
- [ ] Tests: e2e test with multi-type lookup
- [ ] Doc fix: `types.md` static rejection claim qualified ("when possible, ...") or
  implementation matches claim
- [ ] Doc fix: `types.md` row polymorphism section reflects actual status
