# `Scale:N` Modifier Enforcement

**Status:** Exploring
**Roadmap:** `docs/roadmap.md` → Exploring section

## Background

Static literal rejection for refinement types is implemented (E355).

One enforcement gap remains: `Decimal:[Scale:N]` is parsed and stored in the AST
but never enforced at compile time or runtime.

---

## Gap: `Scale:N` Modifier Enforcement

### Problem

```prove
price as Decimal:[Scale:2] = 3.14159    // should error — 5 decimal places > 2
tax   as Decimal:[Scale:2] = 0.1        // ok
total as Decimal:[Scale:2] = price + tax // result must also be Scale:2
```

`Scale:N` means "at most N decimal places". It is parsed as a modifier but the
compiler does not:
1. Verify that literal values respect the scale
2. Emit rounding code for arithmetic results
3. Check that two `Scale:N` values with different N are not mixed without conversion

### Design

**Compile-time (literals):** Check that a `Decimal` literal assigned to a
`Decimal:[Scale:N]` variable has at most N decimal places.

**Note:** `PrimitiveType.modifiers` currently stores only `m.value` (losing `m.name`).
For `Decimal:[Scale:2]`, modifiers = `("2",)` and the "Scale" name is lost. Before
implementing Scale:N checks, the type system needs to preserve modifier names.
Option: change `PrimitiveType.modifiers` to `tuple[tuple[str | None, str], ...]`
storing `(name, value)` pairs.

**Runtime (arithmetic):** Emit a C rounding call after each arithmetic expression
assigned to a `Scale:N` variable. Need to add `prove_decimal_round(val, n)` to
`prove_decimal.h/.c`.

**Type compatibility:** `Decimal:[Scale:M]` and `Decimal:[Scale:N]` with M ≠ N
are not directly compatible — explicit conversion required.

### Files to Touch

- `prove-py/src/prove/types.py` — preserve modifier names in `PrimitiveType`
- `prove-py/src/prove/checker.py` — update `_resolve_type_expr` for ModifiedType
- `prove-py/src/prove/_check_types.py` — Scale literal validation, Scale compatibility check
- `prove-py/src/prove/_emit_stmts.py` or `_emit_exprs.py` — emit rounding call for Scale assignments
- `prove-py/src/prove/errors.py` — register new error codes (E391/E392 are taken; use E407/E408)
- `prove-py/src/prove/runtime/prove_decimal.h/.c` — add `prove_decimal_round(val, scale)`
- `prove-py/tests/test_checker_types.py` — add Scale enforcement tests
- `docs/types.md` — remove *Upcoming* from Scale:N section
- `docs/diagnostics.md` — document new error codes

## After Implementation

- Delete this file
- Update `docs/roadmap.md` (remove from Exploring)
- Update `docs/types.md`: remove *Upcoming* from Scale:N
