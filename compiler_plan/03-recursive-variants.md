# Phase 3: Recursive Variant Types

## Goal

Enable algebraic types to reference themselves (direct recursion) and each
other (mutual recursion within the same module) in variant fields. This is an
independent compiler feature that benefits the whole language — trees,
expression types, linked lists, mutually recursive AST nodes, etc.

**Not a prerequisite for Phase 4** (the Prove stdlib uses opaque binary types),
but a valuable language feature in its own right and a prerequisite for
expressing AST types as native Prove variants in the future.

## Example

```
type Expr is
    Literal(value Integer)
  | Add(left Expr, right Expr)
  | Negate(inner Expr)
```

Today this fails with "undefined type 'Expr'" because the checker resolves
variant fields before registering the type name.

Mutual recursion example:

```
type Stmt is
    ExprStmt(expr Expr)
  | Block(stmts List<Stmt>)

type Expr is
    Literal(value Integer)
  | Lambda(body Stmt)
```

Both types reference each other. Today both fail — `Stmt` can't see `Expr`
(defined later), and `Expr` can't see `Stmt` (not yet registered when `Expr`
fields are resolved).

## Current Blockers (5 compiler layers)

### 1. Checker: no forward-reference

`checker.py:_register_type()` resolves variant fields via `_resolve_type_expr()`
**before** calling `define_type()`. Self-references fail with "undefined type".

### 2. C Emitter: value-type structs can't self-contain

`_emit_types.py:_emit_algebraic_struct()` emits inline `struct` members.
A struct cannot contain itself by value in C (incomplete type error).

### 3. Constructors: value assignment

`_emit_types.py:_emit_variant_constructors()` assigns fields by value.
Recursive fields need pointer parameters and region allocation.

### 4. Match emission: value access

Match arm field bindings assume value-type access. Recursive pointer fields
need `->` dereference.

### 5. Optimizer: escape analysis

Recursive fields are always heap-allocated, affecting copy elision and
escape analysis passes.

## Implementation Steps

### 3.1 Type system utility

**File:** `prove-py/src/prove/types.py`

```python
def find_recursive_fields(
    ty: AlgebraicType | RecordType,
    recursive_group: set[str] | None = None,
) -> set[tuple[str, str]]:
    """Return {(variant_name, field_name)} for recursive fields.

    If recursive_group is provided, also matches fields referencing
    any type in the group (for mutual recursion).
    """
```

Walks each variant's fields, checks if any field type is (or contains) the
same type or any type in the mutual recursion group. Must handle:
- **Direct self-reference:** `left Expr` where field type IS the enclosing type
- **Wrapped in generic:** `children List<Expr>` — `List<Expr>` is
  `Prove_List*` (already a pointer to boxed values), so the list itself is
  fine, but each element needs to be heap-allocated when inserted. This
  affects call emission (3.5), not struct layout.
- **Wrapped in Option:** `parent Option<Expr>` — `Prove_Option` contains a
  `Prove_Value*` (already boxed), so no struct layout change needed. Similar
  to List.

The function should distinguish:
- **Direct recursive fields** (need pointer in struct): field type == enclosing type
- **Indirect recursive fields** (wrapped in List/Option): struct layout
  unchanged, but constructor call sites need boxing

```python
@dataclass
class RecursiveFieldInfo:
    variant_name: str
    field_name: str
    direct: bool  # True = needs pointer in struct; False = wrapped in generic
```

**Test:** `find_recursive_fields(Expr)` returns direct entries for
`("Add", "left")`, `("Add", "right")`, `("Negate", "inner")`.

### 3.2 Checker two-pass type registration (enables mutual recursion)

**File:** `prove-py/src/prove/checker.py` — `_register_type()` and `check()`

Change type registration from single-pass to two-pass:

**Pass 1 — Forward-declare all types in the module:**

Before resolving any type bodies, iterate all `TypeDef` nodes and register
placeholders:

```python
# In check(), before the main declaration loop:
for decl in module.declarations:
    if isinstance(decl, TypeDef):
        if isinstance(decl.body, AlgebraicTypeDef):
            placeholder = AlgebraicType(decl.name, [], tuple(decl.type_params))
            self.symbols.define_type(decl.name, placeholder)
        elif isinstance(decl.body, RecordTypeDef):
            placeholder = RecordType(decl.name, {}, tuple(decl.type_params))
            self.symbols.define_type(decl.name, placeholder)
```

**Pass 2 — Resolve fields (existing `_register_type()`):**

Now when `_resolve_type_expr` encounters `Expr` or `Stmt`, the placeholder
already exists in the symbol table. Both self-references and cross-references
between types in the same module resolve correctly.

After resolving, mutate the placeholder in-place (update its `variants` or
`fields`) so that any earlier references to it also see the full definition.

**Why two-pass works for mutual recursion:** All type names are visible before
any field types are resolved. `Stmt` can reference `Expr` (registered in
pass 1), and `Expr` can reference `Stmt` (also registered in pass 1). The
order of type definitions in the source file doesn't matter.

**Constraint:** Mutual recursion is limited to types **within the same module**.
Cross-module mutual recursion would require cross-module forward-declaration
which is out of scope.

**Test — direct recursion:**
`type Expr is Literal(value Integer) | Add(left Expr, right Expr)` passes.

**Test — mutual recursion:**
`type Stmt is ExprStmt(expr Expr) | Block(stmts List<Stmt>)` +
`type Expr is Literal(value Integer) | Lambda(body Stmt)` passes regardless
of definition order.

### 3.3 Checker base-case validation

**File:** `prove-py/src/prove/checker.py`

After registering all types (pass 2 complete), validate each recursive type:

- **E423: no base case** — at least one variant must NOT reference the type
  (directly or indirectly). `type Bad is A(x Bad) | B(y Bad)` is an error.
- Unit variants count as base cases:
  `type Good is Leaf | Branch(left Good, right Good)` passes.
- Variants with only non-recursive fields also count:
  `type Good is Literal(value Integer) | Add(left Good, right Good)` passes.

**Mutual recursion base-case:** For mutually recursive types, the check must
consider the entire cycle. `type A is X(b B)` + `type B is Y(a A)` is invalid
(no base case in either). But `type A is Leaf | X(b B)` + `type B is Y(a A)`
is valid — `A` has a base case (`Leaf`), and `B` can terminate through `A.Leaf`.

Implementation: build a dependency graph of recursive type references. For
each strongly connected component, verify at least one type in the component
has a non-recursive variant.

**Test — direct:** `type Bad is A(x Bad)` → E423.
**Test — direct ok:** `type Good is Leaf | Branch(...)` → ok.
**Test — mutual bad:** `type A is X(b B)` + `type B is Y(a A)` → E423.
**Test — mutual ok:** `type A is Leaf | X(b B)` + `type B is Y(a A)` → ok.

### 3.4 C Emitter: forward-declare + pointer fields

**File:** `prove-py/src/prove/_emit_types.py` — `_emit_algebraic_struct()`

For types involved in recursion (self or mutual), `find_recursive_fields()`
returns direct entries. Changes:

1. **Forward-declare all types in a recursive cycle** before emitting any
   struct body. For mutual recursion, both types need forward declarations:
   ```c
   typedef struct Prove_Stmt Prove_Stmt;
   typedef struct Prove_Expr Prove_Expr;
   ```

2. Emit `Prove_Expr *field` (pointer) for direct recursive fields —
   including cross-type references in mutual recursion
3. Non-recursive fields remain by-value
4. `List<Expr>` and `Option<Expr>` fields keep their normal emission
   (`Prove_List*`, `Prove_Option`) — they're already pointer/boxed types

Generated C (direct recursion):
```c
typedef struct Prove_Expr Prove_Expr;

enum { Prove_Expr_TAG_LITERAL = 0, Prove_Expr_TAG_ADD = 1, Prove_Expr_TAG_NEGATE = 2 };

struct Prove_Expr {
    uint8_t tag;
    union {
        struct { int64_t value; } Literal;
        struct { Prove_Expr *left; Prove_Expr *right; } Add;
        struct { Prove_Expr *inner; } Negate;
    };
};
```

Generated C (mutual recursion):
```c
typedef struct Prove_Stmt Prove_Stmt;
typedef struct Prove_Expr Prove_Expr;

enum { Prove_Stmt_TAG_EXPRSTMT = 0, Prove_Stmt_TAG_BLOCK = 1 };
struct Prove_Stmt {
    uint8_t tag;
    union {
        struct { Prove_Expr *expr; } ExprStmt;
        struct { Prove_List *stmts; } Block;
    };
};

enum { Prove_Expr_TAG_LITERAL = 0, Prove_Expr_TAG_LAMBDA = 1 };
struct Prove_Expr {
    uint8_t tag;
    union {
        struct { int64_t value; } Literal;
        struct { Prove_Stmt *body; } Lambda;
    };
};
```

**Implementation:** Before emitting type definitions, compute the recursive
type dependency graph. Emit all forward declarations for any type in a
recursive cycle, then emit the struct bodies. Non-recursive types are emitted
as before (no forward-declare, no pointers).

**Test — direct:** emitter output for `type Expr` contains `Prove_Expr *left`.
**Test — mutual:** emitter output has forward declarations for both types and
cross-type pointer fields.

### 3.5 C Emitter: constructors with pointer params

**File:** `prove-py/src/prove/_emit_types.py` — `_emit_variant_constructors()`

Recursive-field constructors take pointer parameters:

```c
static inline Prove_Expr Add(Prove_Expr *left, Prove_Expr *right) {
    Prove_Expr _v;
    _v.tag = Prove_Expr_TAG_ADD;
    _v.Add.left = left;
    _v.Add.right = right;
    return _v;
}
```

At call sites, the emitter wraps value-producing expressions in region
allocation:

```c
Prove_Expr *_tmp1 = prove_region_alloc(sizeof(Prove_Expr));
*_tmp1 = Literal(42);
Prove_Expr *_tmp2 = prove_region_alloc(sizeof(Prove_Expr));
*_tmp2 = Literal(7);
Prove_Expr _result = Add(_tmp1, _tmp2);
```

**File also changed:** `prove-py/src/prove/_emit_calls.py` — constructor call
emission must detect recursive types and insert allocation.

**Retain/release:** The C runtime uses region-based memory management.
Recursive pointer fields are allocated in the current region and freed when
the region exits. No per-field retain/release needed — region cleanup handles
it. If a recursive value escapes the region (e.g., returned from a function),
the region's normal escape-to-parent logic applies.

### 3.6 C Emitter: match arm pointer dereference

**File:** `prove-py/src/prove/_emit_exprs.py`

Match field bindings for recursive variants use pointer type:

```c
case Prove_Expr_TAG_ADD: {
    Prove_Expr *left = _subject.Add.left;
    Prove_Expr *right = _subject.Add.right;
    // arm body
}
```

The binding's checker type is `Expr`, but the C type is `Prove_Expr*`.
The emitter checks `find_recursive_fields()` to decide.

When the bound variable is subsequently used in expressions (e.g., passed to
a function or matched again), the emitter must dereference: `*left` where a
value is expected, or pass `left` directly where a pointer is expected
(e.g., to another recursive constructor).

**Test:** nested match on `Expr` that destructures `Add(left, right)` then
matches `left` again.

### 3.7 Optimizer awareness

**File:** `prove-py/src/prove/optimizer.py`

- **Escape analysis:** direct recursive fields always escape (heap-allocated
  via region). Skip copy elision for them.
- **Dead code elimination:** recursive constructors should not be eliminated
  if any variant of the type is used.
- **TCO:** Recursive functions that build/consume recursive types may benefit
  from tail-call optimization, but this is not new — existing TCO logic
  applies.

Minor changes — most optimizer logic works at function-level AST.

## Non-Goals (v1)

- **Cross-module mutual recursion** — types in different modules referencing
  each other. Would require cross-module forward-declaration protocol. Defer.
- **Generic recursive types** (`type Tree<T>`) — generics + recursion
  interaction is complex. Defer.
- **TCO for recursive match traversal** — nice-to-have, not blocking.

## Test Plan

1. **Checker unit tests — direct recursion:** self-ref resolves; base-case
   E423 error fires; constructor sigs correct; `Option<Self>` and
   `List<Self>` fields pass
2. **Checker unit tests — mutual recursion:** two types referencing each
   other resolve; definition order doesn't matter; base-case validation
   works across the cycle; E423 fires for cycles with no base case
3. **Emitter unit tests:** forward-declare, pointer fields, pointer
   constructors in generated C output; mutual recursion forward-declares
   both types before either struct body
4. **E2e tests:** compile and run programs that construct, match, and
   recursively traverse algebraic trees; verify output correctness and no
   memory leaks (region cleanup)
5. **E2e mutual recursion:** compile program with mutually recursive types,
   construct values, match across both types
6. **Regression:** all existing algebraic type tests pass unchanged

## Files Changed

| File | Change |
|------|--------|
| `types.py` | `RecursiveFieldInfo`, `find_recursive_fields()` |
| `checker.py` | Two-pass registration in `check()`; E423 base-case validation |
| `_emit_types.py` | Forward-declare, pointer fields, pointer constructors |
| `_emit_exprs.py` | Pointer dereference in match bindings |
| `_emit_calls.py` | Region allocation at recursive constructor call sites |
| `optimizer.py` | Escape analysis for recursive fields |
| `tests/test_checker.py` | New recursive type tests |
| `tests/test_c_emitter.py` | Emitter output tests |
| `tests/test_types_runtime_c.py` | E2e: construct + match recursive types |
