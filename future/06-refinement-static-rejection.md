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

### Root Cause: Modifier Names Are Dropped at Resolution Time

`TypeModifier` in `ast_nodes.py:27` carries both `name: str | None` and `value: str`.
For `Decimal:[Scale:2]` the modifier is `TypeModifier(name="Scale", value="2")`.

But every site that converts `ModifiedType → PrimitiveType` discards `.name`:

| File | Line | Code |
|------|------|------|
| `_check_types.py` | 736 | `mods = tuple(m.value for m in type_expr.modifiers)` |
| `checker.py` | 2474 | same |
| `module_resolver.py` | 222 | same |
| `stdlib_loader.py` | 588 | same |

So `Decimal:[Scale:2]` resolves to `PrimitiveType("Decimal", ("2",))`. The `"Scale"`
name is lost; the `"2"` is an opaque positional string.

`types_compatible` (`types.py:314-318`) strips modifiers entirely when comparing
`PrimitiveType` values with modifiers against record/algebraic types, and
`expected == actual` at line 348 means two `Decimal:[Scale:N]` with different N
are currently treated as equal types.

---

## Implementation Plan

### Step 1 — Preserve modifier names in `PrimitiveType` (`types.py`)

Change `modifiers` from `tuple[str, ...]` to `tuple[tuple[str | None, str], ...]`,
storing `(name, value)` pairs.

```python
# Before
@dataclass(frozen=True)
class PrimitiveType:
    name: str
    modifiers: tuple[str, ...] = ()

# After
@dataclass(frozen=True)
class PrimitiveType:
    name: str
    modifiers: tuple[tuple[str | None, str], ...] = ()
```

Update `type_name()` at `types.py:192`:

```python
if ty.modifiers:
    parts = []
    for (mname, mval) in ty.modifiers:
        parts.append(f"{mname}:{mval}" if mname else mval)
    return f"{ty.name}:[{' '.join(parts)}]"
```

Update `has_own_modifier` (`types.py:403`), `has_mutable_modifier` (`types.py:410`),
and `get_ownership_kind` (`types.py:417`) to unpack the pair:

```python
# was: return "Own" in ty.modifiers
return any(v == "Own" for (_, v) in ty.modifiers)
```

#### Propagation: fix all `m.value` call sites

Every resolution site that does `tuple(m.value for m in type_expr.modifiers)` must
become `tuple((m.name, m.value) for m in type_expr.modifiers)`:

- `prove-py/src/prove/_check_types.py:736`
- `prove-py/src/prove/checker.py:2474`
- `prove-py/src/prove/module_resolver.py:222`
- `prove-py/src/prove/stdlib_loader.py:588`, `574`

Also update `type_name()` caller in the formatter at `formatter.py:747` — but that
reads from the AST `ModifiedType.modifiers`, not `PrimitiveType.modifiers`, so it
is unaffected at that call site. Verify no other display code reads `.modifiers`
directly by grepping for `\.modifiers`.

---

### Step 2 — Helper: extract `Scale` value from a `PrimitiveType`

Add to `types.py`:

```python
def get_scale(ty: Type) -> int | None:
    """Return the Scale:N value for Decimal:[Scale:N], or None."""
    if isinstance(ty, PrimitiveType) and ty.name == "Decimal":
        for (mname, mval) in ty.modifiers:
            if mname == "Scale":
                try:
                    return int(mval)
                except ValueError:
                    return None
    return None
```

---

### Step 3 — Compile-time literal check (`_check_types.py`) — **E407**

In `_check_types.py`, inside `_infer_expr` (or whichever method handles `VarDecl`
/ assignment type checking), after resolving the declared type to a `PrimitiveType`,
call `get_scale()`. If non-None and the RHS is a `DecimalLit` (or `IntLit` used
as Decimal), count the decimal places in the literal string and reject if
`decimal_places > scale`.

Emit **E407**: `Scale:{N} requires at most {N} decimal places, but literal has {k}`

```python
# In _check_types.py (TypeCheckMixin._check_assignment or _infer_var_decl)
from prove.types import get_scale

declared_scale = get_scale(declared_ty)
if declared_scale is not None and isinstance(rhs, DecimalLit):
    places = _count_decimal_places(rhs.value)  # helper, see below
    if places > declared_scale:
        self._error(
            "E407",
            f"Scale:{declared_scale} requires at most {declared_scale} decimal "
            f"place{'s' if declared_scale != 1 else ''}, "
            f"but literal '{rhs.value}' has {places}",
            rhs.span,
        )
```

Helper (private, same file):

```python
def _count_decimal_places(literal: str) -> int:
    """Count decimal places in a numeric literal string like '3.14159'."""
    if "." in literal:
        return len(literal.split(".")[1].rstrip("0") or "0")
    return 0
```

Note: `"0".rstrip("0")` gives `""` so the `or "0"` ensures at least 0 → 0 places.
A trailing-zero rule: `3.10` is 1 place (trailing zeros stripped), matching
standard decimal semantics. If the project wants to keep trailing zeros as
meaningful (they usually are in financial contexts), drop the `.rstrip("0")` and
document the choice.

**Where to add the check in the checker:**

The best entry point is in `_check_types.py` inside `_infer_var_decl_type()` (or
whatever method handles `VarDecl` after resolving the annotation). Search for the
section that already calls `types_compatible(declared, inferred)` to find the exact
spot. The Scale check must run *before* the compatibility check so that the error
message names the specific violation rather than just "type mismatch".

---

### Step 4 — Scale compatibility in `types_compatible` (`types.py`) — **E408**

Two `Decimal:[Scale:M]` and `Decimal:[Scale:N]` with M ≠ N are not directly
compatible. Add to `types_compatible`:

```python
# After the BorrowType unwrapping, before the final `expected == actual`:
if isinstance(expected, PrimitiveType) and isinstance(actual, PrimitiveType):
    if expected.name == actual.name == "Decimal":
        es = get_scale(expected)
        as_ = get_scale(actual)
        if es is not None and as_ is not None and es != as_:
            return False
```

This makes `types_compatible` return `False` for mismatched scales. The existing
type-mismatch error machinery in the checker will then fire. If a more precise
message is desired, add a dedicated **E408** check in `_check_types.py` that detects
this case before calling `types_compatible` and emits:

```
E408  Cannot assign Decimal:[Scale:3] to Decimal:[Scale:2] without explicit rounding
```

---

### Step 5 — Runtime rounding after arithmetic (`_emit_stmts.py` / `_emit_exprs.py`)

For assignments where the LHS is `Decimal:[Scale:N]` and the RHS is a non-literal
expression (e.g. `price + tax`, a function call, or a variable), emit a C rounding
call that rounds to N places.

**New C function: `prove_decimal_round`**

Add to `prove-py/src/prove/runtime/prove_math.h` (or a new
`runtime/prove_decimal.h`):

```c
/* Round `val` to `scale` decimal places using round-half-up. */
static inline double prove_decimal_round(double val, int scale) {
    double factor = pow(10.0, (double)scale);
    return round(val * factor) / factor;
}
```

(Use `<math.h>` `round()` — already available in the runtime. If a separate
`prove_decimal.h/.c` is created, add it to `_CORE_FILES` in `c_runtime.py`.)

**Emission in `_emit_stmts.py`:**

In `_emit_var_decl`, after resolving `target_ty`, check if it has a Scale modifier.
If the RHS is not a `DecimalLit` (which was already validated in Step 3), wrap the
emitted value expression:

```python
from prove.types import get_scale

scale = get_scale(target_ty)
if scale is not None:
    # RHS is a runtime expression — emit rounding
    raw_val = self._emit_expr(vd.value)
    self._emit(f"double {vd.name} = prove_decimal_round({raw_val}, {scale});")
    return   # skip normal emission path
```

The same wrapping applies to `_emit_assignment` for re-assignments to a
`Decimal:[Scale:N]` variable. The `target_ty` is already inferred there; use
`get_scale` identically.

**Include guard:** only emit the rounding call when the inferred RHS type is
`Decimal` (or `Float`). Do not wrap integer arithmetic that is being implicitly
coerced — the compiler should have already emitted an E408 for that.

---

### Step 6 — Error code registration (`errors.py`)

The range E395–E409 is currently unregistered (E391–394 are explain-verification,
E410–422 are comptime). Register two new codes:

```python
# Scale:N enforcement E407-E408
for _c in ("E407", "E408"):
    DIAGNOSTIC_DOCS[_c] = f"{_DOCS_BASE}#{_c}"
```

---

### Step 7 — Tests (`tests/test_checker_types.py`)

Add a new section `# Scale:N enforcement`:

```python
# Literal exceeds scale → E407
def test_scale_literal_too_many_places():
    check_fails("""
        reads demo() Unit
        from
            x as Decimal:[Scale:2] = 3.14159
    """, "E407")

# Literal within scale → ok
def test_scale_literal_ok():
    check("""
        reads demo() Unit
        from
            x as Decimal:[Scale:2] = 3.14
    """)

# Integer literal assigned to Scale:N → ok (0 places)
def test_scale_integer_literal_ok():
    check("""
        reads demo() Unit
        from
            x as Decimal:[Scale:2] = 3
    """)

# Mismatched scales → E408
def test_scale_mismatch_assignment():
    check_fails("""
        reads demo() Unit
        from
            a as Decimal:[Scale:3] = 1.123
            b as Decimal:[Scale:2] = a
    """, "E408")

# No Scale modifier → no check
def test_plain_decimal_no_scale_check():
    check("""
        reads demo() Unit
        from
            x as Decimal = 3.14159
    """)
```

Add a runtime test in `tests/test_math_runtime_c.py` (or a new
`tests/test_decimal_runtime_c.py`) that compiles and runs a snippet using
`Decimal:[Scale:2]` arithmetic and asserts the rounded result.

---

### Step 8 — Documentation

- `docs/types.md` — remove *Upcoming* annotation from `Scale:N` section; add
  examples showing the rounding behavior and the two error codes
- `docs/diagnostics.md` — add entries for E407 and E408

---

## Files to Touch (summary)

| File | Change |
|------|--------|
| `prove-py/src/prove/types.py` | `PrimitiveType.modifiers` → `tuple[tuple[str\|None, str], ...]`; update helpers; add `get_scale()` |
| `prove-py/src/prove/checker.py:2474` | `m.value` → `(m.name, m.value)` |
| `prove-py/src/prove/_check_types.py:736` | same; add E407 literal check; add E408 scale-mismatch check |
| `prove-py/src/prove/module_resolver.py:222` | `m.value` → `(m.name, m.value)` |
| `prove-py/src/prove/stdlib_loader.py:574,588` | same |
| `prove-py/src/prove/_emit_stmts.py` | wrap Scale:N assignments with `prove_decimal_round` |
| `prove-py/src/prove/errors.py` | register E407, E408 |
| `prove-py/src/prove/runtime/prove_math.h` (or new `prove_decimal.h`) | add `prove_decimal_round()` |
| `prove-py/tests/test_checker_types.py` | add Scale:N test cases |
| `docs/types.md` | remove *Upcoming* from Scale:N |
| `docs/diagnostics.md` | document E407, E408 |

---

## Open Questions

1. **Trailing zeros in literals:** should `3.10` count as 1 or 2 decimal places?
   Financial convention: 2. Strip-trailing-zeros convention: 1. Choose one and
   document it before implementing `_count_decimal_places`.

2. **Rounding mode:** `round()` in C uses "round half away from zero".
   Banker's rounding (`rint` with `FE_TONEAREST`) is more accurate for financial
   use. Decide before writing `prove_decimal_round`.

3. **Scale on function return types:** a function returning `Decimal:[Scale:2]`
   should also have its return value rounded. This is a separate concern from
   variable assignment; defer to a follow-up unless it is trivial to handle at the
   same time.

4. **`prove_decimal.h/.c` vs adding to `prove_math.h`:** `Decimal` maps to `double`
   in the C runtime. A standalone `prove_decimal.h` keeps the boundary clean but
   adds a new `_CORE_FILES` entry. Adding `prove_decimal_round` to `prove_math.h`
   is simpler. Prefer the simpler option unless other decimal-specific functions
   are anticipated soon.

---

## After Implementation

- Delete this file
- Update `docs/roadmap.md` (remove from Exploring)
- Update `docs/types.md`: remove *Upcoming* from Scale:N
