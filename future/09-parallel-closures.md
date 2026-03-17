# Closure Capture for Parallel HOF Callbacks

**Status:** Exploring
**Roadmap:** `docs/roadmap.md` → Exploring section

## Background

`par_map`, `par_filter`, `par_reduce`, and the planned `par_each` require named
function callbacks — lambdas with captured bindings are not supported. The same
restriction applies to sequential `each`. This is a fundamental limitation for
ergonomic use of higher-order functions.

```prove
// Current: must use a named function
transforms double(x Integer) Integer
from x * 2

transforms result(xs List<Value>) List<Value>
from par_map(xs, double)

// Desired: inline lambda with capture
transforms result(xs List<Value>, factor Integer) List<Value>
from par_map(xs, |x| => x * factor)   // captures `factor`
```

---

## Why It's Hard for Parallel HOFs

Sequential HOFs (future `each` lambda support) only need a closure struct on the
stack of the calling function. Parallel HOFs pass callbacks to pthreads workers —
the closure struct must be:

1. **Heap-allocated** (not stack) — the calling thread may have exited by the time
   a worker reads the captured values
2. **Read-only** — workers cannot safely mutate captured bindings; the compiler must
   verify no captured variable is written in the closure body
3. **Freed after all workers complete** — the thread pool join point is the safe
   deallocation site

Sequential HOF lambdas (non-parallel) are simpler — no heap allocation needed, can
use stack-allocated closure structs. Implement sequential lambdas first.

---

## Design

### Phase 1: Sequential Lambda Closures

Allow `|param| => expr` syntax in `each`, `map`, `filter`, `reduce`.
Closure struct emitted on the calling function's stack:

```c
struct _lambda_ctx_1 { int64_t factor; };
static Value _lambda_1(Value x, void *ctx) {
    struct _lambda_ctx_1 *c = ctx;
    return INT(x.i * c->factor);
}
// ...
struct _lambda_ctx_1 _ctx = { .factor = factor };
prove_list_map(xs, _lambda_1, &_ctx);
```

The existing `_emit_hof_lambda()` in `_emit_calls.py` already generates the
callback function wrapper — it needs to be extended to accept a capture list and
emit the struct.

### Phase 2: Parallel Lambda Closures

Same as Phase 1 but:
- Closure struct allocated in the region (`prove_region_alloc`) not on the stack
- Compiler verifies all captured variables are read-only within the lambda body (no assignment)
- Struct freed after `prove_par_map` / `prove_par_each` returns (join point)

Purity constraint for parallel HOFs: captured variables must be immutable. The
compiler already enforces that the callback verb is pure for `par_map`/`par_filter`/
`par_reduce` — extend this to reject lambdas that assign captured names.

---

## Implementation Plan

### 1. Lexer / Parser

Add `|param| => expr` and `|param| => from ...` lambda syntax to `lexer.py` and
`parser.py`. Produce a `LambdaExpr` AST node:

```python
@dataclass(frozen=True)
class LambdaExpr:
    params: list[Param]
    body: Expr | list[Stmt]
    span: Span
    captures: list[str] = field(default_factory=list)  # filled by checker
```

### 2. Checker (`checker.py` / `_check_calls.py`)

- Infer lambda type: `FunctionType(param_types, return_type)`
- Walk the lambda body and collect free variables → `captures`
- For parallel HOFs: verify all captured names are not written in the lambda body (E396)
- Purity enforcement for parallel HOF lambdas: same E368 check, applied to the lambda verb inferred from body

### 3. C Emitter (`_emit_calls.py` / `_emit_exprs.py`)

Extend `_emit_hof_lambda()`:
- If `captures` is empty: emit as before (no ctx struct)
- If sequential HOF: emit stack-allocated ctx struct
- If parallel HOF: emit region-allocated ctx struct

### 4. Errors

- **E396** — lambda captures a mutable variable in a parallel context

### Files to Touch

- `prove-py/src/prove/lexer.py` — add `|` and `=>` tokens (or reuse existing)
- `prove-py/src/prove/parser.py` — add lambda expression parsing
- `prove-py/src/prove/ast_nodes.py` — add `LambdaExpr`
- `prove-py/src/prove/checker.py` — lambda type inference, capture collection
- `prove-py/src/prove/_check_calls.py` — E396 parallel mutability check
- `prove-py/src/prove/_emit_calls.py` — extend `_emit_hof_lambda()` with capture structs
- `prove-py/src/prove/_emit_exprs.py` — emit `LambdaExpr` directly
- `prove-py/src/prove/errors.py` — register E396
- `prove-py/tests/test_checker_types.py` — lambda capture tests
- `docs/functions.md` — remove *Upcoming* from closures note
- `docs/diagnostics.md` — document E396

---

## Open Questions

1. Should Phase 1 (sequential) and Phase 2 (parallel) be shipped together or
   separately? Together.
2. Lambda syntax: `|x| => expr` vs `fn(x) => expr`? `|x|` is compact and familiar
   from Rust/Swift; `fn` clashes with Prove's verb-first philosophy. Prefer `|x|`.
3. Multi-statement lambda bodies: `|x| => from ...`? Useful but complex. Defer
   multi-statement lambdas until single-expression lambdas are stable.

## After Implementation

- Delete this file
- Update `docs/roadmap.md` (remove from Exploring)
- Update `docs/functions.md`: remove *Upcoming* from closures note for all HOFs
