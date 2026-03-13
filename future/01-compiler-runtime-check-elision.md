# Compiler-Runtime Check Coordination

**Status:** Planned
**Depends on:** Nothing (each item is independent)
**Relates to:** `runtime-bug-fixes.md` (complements it; does not overlap)

## Context

`runtime-bug-fixes.md` establishes the principle: the compiler is the primary safety
mechanism; the runtime only guards things the compiler cannot enforce. This document
covers four gaps where the current code does the *wrong* side of that split — either
the runtime does work the compiler already guaranteed isn't needed, or the compiler
silently skips checks that it is uniquely positioned to enforce.

---

## Item 1 — Dead Null Guards in Runtime Functions

**Category:** Performance / dead code elimination
**Files:** `prove_text.c`, `prove_list_ops.c`, `prove_table.c`, `prove_pattern.c`

### Problem

Every public runtime function defensively null-checks its primary argument:

```c
// prove_text.c
int64_t prove_text_length(Prove_String *s) {
    return s ? s->length : 0;   // String is NEVER null in Prove
}

Prove_String *prove_text_slice(Prove_String *s, int64_t start, int64_t end) {
    if (!s) return prove_string_new("", 0);  // dead branch
    ...
}

// prove_list_ops.c — every single function
bool prove_list_ops_empty(Prove_List *list) {
    return !list || list->length == 0;  // !list is dead
}

// prove_text.c — Builder functions
Prove_Builder *prove_text_write(Prove_Builder *b, Prove_String *s) {
    if (!b) prove_panic("Builder.write: null builder");  // dead panic
```

Prove's type system guarantees these are never null:
- `String` — value type, always allocated
- `List<T>` — always returned from `creates`/stdlib, never nullable
- `StringBuilder` — returned from `creates builder()`
- `Table<T>` — always non-null in scope
- `Match` — only appears as return of successful pattern match

The checks are waste code that runs in hot loops (text processing, list iteration,
sieve-style algorithms).

### Fix

Remove all defensive `!ptr` null guards for these types from runtime functions. If
the compiler ever emits a null pointer for these types, that is a compiler bug — the
runtime is not the right place to catch it.

Specific functions to clean up:

| File | Guards to remove |
|------|-----------------|
| `prove_text.c` | `!s`, `!prefix`, `!suffix`, `!sub`, `!sep`, `!old_s`, `!new_s` in all functions |
| `prove_list_ops.c` | `!list` in all 12 functions |
| `prove_text.c` (Builder) | `if (!b) prove_panic(...)` in `write`, `write_char`, `write_cstr` |
| `prove_table.c:68-69` | `if (!table)`, `if (!key)` in `prove_table_add` |
| `prove_pattern.c:227-237` | `if (!m) prove_panic(...)` in `text`, `start`, `end` |

Keep `!ptr` guards only where a NULL is a valid sentinel at the C level (e.g.
`prove_list_ops_value` returning NULL for index-not-found, though that also has a
type mismatch issue noted below).

### Bonus: `prove_list_ops_value` type mismatch

`prove_list_ops_value` returns `Prove_Value *` (non-null in the Prove type) but
returns `NULL` silently on OOB instead of panicking. This mismatches its declared
type. Either it should panic (if the compiler guarantees in-bounds access) or the
signature should be `Option<Value>`. Align with whatever the checker enforces at
call sites.

---

## Item 2 — Region Scope Elision for Non-Allocating Functions

**Category:** Performance — biggest per-call overhead for pure numeric code
**Files:** `c_emitter.py:666`, `prove_region.c`

### Problem

Every compiled function unconditionally gets:

```c
prove_region_enter(prove_global_region());   // malloc(4096 bytes!)
// ... function body ...
prove_region_exit(prove_global_region());    // free chain walk
```

`prove_region_enter` always allocates a 4096-byte `ProveRegionFrame` via `malloc`.
For functions that allocate nothing — pure math, boolean tests, TCO'd numeric
loops — this malloc/free pair is the dominant runtime cost.

Examples where this is pure overhead:
- `count_primes(arr, i, limit, acc)` — TCO loop over array, zero allocation
- `sieve_pass(arr, p, limit)` — same
- Any `transforms` function operating only on `Integer`, `Boolean`, `Decimal`

### Fix

Add `_needs_region_scope(fd: FuncDef) -> bool` in `c_emitter.py`. Algorithm:

1. Walk the function body's AST.
2. If any call resolves to a function in the "allocating" set, return `True`.
3. Otherwise return `False` — skip `prove_region_enter/exit` emission.

**Allocating set** (functions that call `prove_region_alloc` or `prove_alloc`):
- Any call to `console`, `file`, or other IO verbs
- Any call returning `String`, `List<T>`, `Table<T>`, `Builder`
- Any f-string interpolation (calls `prove_string_new`)
- Any call to `prove_string_*`, `prove_list_new`, `prove_table_*`

**Non-allocating** (safe to skip region scope):
- Functions whose body contains only: integer/boolean/float arithmetic, `Array<T>`
  get/set (which use `malloc` directly, not the region), and calls to other
  non-allocating functions.

For TCO-converted `while(1)` loops (the inlined forms), this matters most — the
region enter/exit wraps the entire loop, paying malloc on every outer invocation.

### Emitter change

In `c_emitter.py`, replace the unconditional emit at line 666 with:

```python
if self._needs_region_scope(fd):
    self._line("prove_region_enter(prove_global_region());")
    self._in_region_scope = True
else:
    self._in_region_scope = False
```

And correspondingly skip the `prove_region_exit` at the bottom of `_emit_func`.

---

## Item 3 — Division by Zero

**Category:** Safety — silent UB today
**Files:** `_emit_exprs.py` (binary op emission), `type_inference.py`

### Problem

Integer `/` and `%` emit directly as C operators. C integer division by zero is
undefined behavior. Currently:

- No compile-time check for constant zero divisors
- No runtime check for variable divisors
- No contract integration

### Fix — Three tiers

**Tier 1: Constant divisor (compile time)**

In the checker, when the right operand of `/` or `%` is a literal `0`, emit a
compile error (new diagnostic code, e.g. E370).

**Tier 2: `requires` contract present**

If the calling function has `requires: denominator != 0` (or equivalent), the
emitter already generates an `assume` guard at function entry. Trust it — emit no
additional check for the division.

**Tier 3: Unknown divisor (runtime)**

For all other cases, emit a guard before the division:

```c
// emitted by _emit_exprs.py for Integer / and %
if ((b) == 0) prove_panic("division by zero");
int64_t result = a / b;
```

This guard should be suppressible with a `--release` build flag (`-DPROVE_RELEASE`)
matching the same flag proposed for array bounds in `array-safe-access.md`.

---

## Item 4 — Refinement Type Enforcement at IO Boundaries

**Category:** Safety — currently unenforced for runtime values
**Files:** `_emit_stmts.py` (variable assignment emission), `checker.py`

### Problem

Refinement types (`type Port is Integer where 1..65535`) are checked at compile
time for literal values. But values arriving from IO — stdin, file, network,
`Parse.integer()` — are never validated against the constraint:

```prove
port as Port = Types.integer(raw_str)!   // constraint 1..65535 never checked
```

This means external input can silently violate invariants the type system is
supposed to guarantee.

### Fix

In `_emit_stmts.py`, at every `VarDecl` or `Assignment` where:
1. The declared type is a refinement type with a `where` clause, AND
2. The source expression is not a compile-time literal (i.e., the checker could not
   statically verify the constraint)

...emit a runtime guard using the constraint expression compiled to C:

```c
// type Port is Integer where 1..65535
int64_t _tmp = /* source expression */;
if (!(_tmp >= 1 && _tmp <= 65535))
    prove_panic("Port constraint violated: expected 1..65535");
int64_t port = _tmp;
```

The constraint-to-C translation is already partially present in the checker
(it evaluates `where` clauses for literal checking). Reuse that logic in the emitter.

### Special case: `Convert.character`

`prove_convert_character(n)` currently panics inside C if `n < 0 || n > 127`.
This should instead be:
1. Define `type AsciiCode is Integer where 0..127` in stdlib.
2. Change `Convert.character` to accept `AsciiCode` instead of `Integer`.
3. The runtime panic becomes a compiler-generated guard (per the above mechanism).
4. Remove the ad-hoc panic from `prove_convert.c`.

This makes the guarantee visible at the type level rather than buried in C.

---

## Implementation Order

| Item | Effort | Impact | When |
|------|--------|--------|------|
| 1 — Dead null guards | Low (search-and-delete in C) | Medium (cleaner hot paths) | Next runtime cleanup pass |
| 2 — Region scope elision | Medium (new emitter analysis pass) | **High** (eliminates malloc per pure function call) | High priority for numeric perf |
| 3 — Division by zero | Low (3 tiers, each small) | Medium (closes silent UB) | With next checker diagnostic pass |
| 4 — Refinement IO guards | Medium (emitter + constraint codegen) | High (makes refinement types actually safe) | After type system stabilizes |
