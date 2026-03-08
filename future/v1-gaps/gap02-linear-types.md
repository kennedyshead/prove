# Linear Types & Ownership — V1.0 Gap 02

## Overview

Basic move tracking exists for assignment and call-argument positions, but complex
expression moves, nested field moves, and return-position moves are not tracked.
The `Own` modifier and `BorrowType` infrastructure is in place but under-utilized.

## Current State

Working pieces:

- `Own` modifier: checked via `has_own_modifier()` (`types.py:379`)
- `BorrowType` class defined (`types.py:86`) and used in the `Type` union (`types.py:104`)
- `_moved_vars: set[str]` on Checker (`checker.py:209`), cleared per function (`checker.py:818`)
- Assignment move: `_moved_vars.add(assign.value.name)` (`checker.py:1538`)
- Use-after-move check on identifier access (`checker.py:1651`)
- `_check_moved_var()` method (`checker.py:2200`)
- Call-arg move tracking: `_track_moved_args()` (`_check_calls.py:411`) and
  `_track_moved_expr()` (`_check_calls.py:427`)
- Borrow inference: `_infer_param_borrows()` (`checker.py:2117`) active at
  function scope entry (`checker.py:840–845`)

## What's Missing

1. **Complex expression moves** — chained operations on owned values (e.g.,
   `process(transform(owned_val))`) do not track intermediate ownership transfer.

2. **Nested field moves** — moving a field of an owned value (e.g., `x.inner`)
   does not mark the parent as partially moved or the field as moved.

3. **Return-position moves** — returning an owned value from a function does not
   consume it from the caller's perspective when the return value is ignored.

4. **Generic ownership** — `List<T:[Own]>` and `Option<T:[Own]>` do not propagate
   ownership semantics through generic containers.

5. **Doc fix** — `design.md` claims "Reference counting only where ownership shared"
   but RC is not ownership-aware; it uses scope-based release only.

## Implementation

### Phase 1: Complex expression moves

1. In `_track_moved_expr()` (`_check_calls.py:427`), extend tracking beyond simple
   identifiers to handle:
   - Method chains: `a.transform().process()` — track that `a` is consumed
   - Nested calls: `f(g(owned))` — track that `owned` is consumed by `g`
   - Binary expressions: `owned + other` — track consumption if `+` takes ownership

2. Add a recursive expression walker that identifies all owned-value leaves in an
   expression tree and marks them as moved.

### Phase 2: Nested field moves

1. Extend `_moved_vars` from `set[str]` to track field paths (e.g., `"x.inner"`).

2. When an owned field is moved, mark the field path as moved and the parent as
   partially moved. Subsequent access to the parent (not just the field) should
   emit E340.

3. Handle reassignment to a moved field as restoring partial validity.

### Phase 3: Return-position moves

1. When a function returns an owned value (type with `:[Own]` modifier), track that
   the local variable used in the return expression is consumed.

2. If a function call returning an owned type has its result discarded, emit an error
   (resource leak — owned value dropped without explicit handling).

### Phase 4: Generic ownership propagation

1. When `List<T:[Own]>` or `Option<T:[Own]>` is used, ensure that extracting elements
   follows ownership rules (moving out of a list element, unwrapping an option).

2. Extend `_check_moved_var()` to understand generic container access patterns.

### Phase 5: Documentation fix

1. Update `design.md` to accurately describe the current RC model: scope-based
   release via `prove_rc_release()` at function exit, not ownership-aware RC.

## Files to Modify

| File | Change |
|------|--------|
| `_check_calls.py:427` | Extend `_track_moved_expr()` for complex expressions |
| `checker.py:209` | Upgrade `_moved_vars` to support field paths |
| `checker.py:1651` | Extend use-after-move check for partial moves |
| `checker.py:2200` | Extend `_check_moved_var()` for nested fields |
| `types.py:379` | Extend `has_own_modifier()` for generic containers |
| `docs/design.md` | Fix RC/ownership claim |

## Exit Criteria

- [ ] Complex expression moves tracked (chained calls, nested calls)
- [ ] Nested field moves tracked with partial-move semantics
- [ ] Return-position moves consume local variables
- [ ] Discarded owned return values produce errors (E-level, not warnings)
- [ ] `List<T:[Own]>` and `Option<T:[Own]>` propagate ownership
- [ ] Tests: unit tests for each move tracking scenario
- [ ] Doc fix: `design.md` RC description matches implementation
