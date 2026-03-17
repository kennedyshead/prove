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

## Current State (as of 2026-03-18)

**What already exists:**

- `LambdaExpr` AST node (`ast_nodes.py:204`): `params: list[str]`, `body: Expr`,
  `span: Span` — no `captures` field yet.
- `_emit_hof_lambda` (`_emit_calls.py:754`): fully functional for sequential HOFs
  (map, filter, reduce, each) — emits hoisted `static` C functions. No ctx struct.
- `_infer_lambda` (`_check_types.py:373`): infers `FunctionType` for lambdas;
  calls `_check_lambda_captures` which currently **raises E364** for any captured
  variable ("closures not supported").
- `prove_par_map.c/.h` (`runtime/prove_par_map.c`): full pthreads implementation
  with sequential fallback. `Prove_MapFn = void *(*)(void *)`. Already used by the
  builder (`-lpthread`). **Not yet registered in `stdlib_loader.py`** — there is no
  Prove-language entry point for `par_map`.
- No `par_filter`, `par_reduce`, `par_each` in C runtime yet.

**Blocking issue:** `_check_lambda_captures` turns any variable capture into E364,
so `|x| => x * factor` fails if `factor` is a local. Sequential HOFs already emit
correctly when the lambda body only references its own params.

---

## Why Parallel Closures Are Harder

Sequential HOF lambdas (non-parallel) are simpler — no heap allocation needed, can
use stack-allocated closure structs. Parallel HOFs pass callbacks to pthreads workers —
the closure struct must be:

1. **Heap-allocated** (not stack) — the calling thread may have exited by the time
   a worker reads the captured values
2. **Read-only** — workers cannot safely mutate captured bindings; the compiler must
   verify no captured variable is written in the closure body
3. **Freed after all workers complete** — the thread pool join point is the safe
   deallocation site

---

## Design

### Phase 1: Sequential Lambda Closures

Replace E364 rejection with actual capture collection. Emit a stack-allocated ctx
struct for sequential HOFs (map, filter, reduce, each). No heap allocation, no
purity constraint beyond what the HOF verb already requires.

```c
// Generated for: par_map(xs, |x| => x * factor)  [sequential HOF]
struct _ctx_1 { int64_t factor; };
static void *_lambda_1(void *_arg, void *_ctx) {
    int64_t x = (int64_t)(intptr_t)_arg;
    struct _ctx_1 *c = (struct _ctx_1 *)_ctx;
    return (void *)(intptr_t)(x * c->factor);
}
// at call site:
struct _ctx_1 _c = { .factor = factor };
prove_list_map(xs, _lambda_1, &_c);
```

**Note:** The existing HOF C functions (`prove_list_map`, `prove_list_filter`,
`prove_list_each`, `prove_list_reduce`) accept `Prove_MapFn = void *(*)(void *)` —
a single-argument signature with no ctx pointer. These must be **extended** with a
`void *ctx` parameter before capture structs can be passed through. See Step 2 below.

### Phase 2: Parallel Lambda Closures + par_map Language Binding

Same struct layout as Phase 1, but:
- Struct allocated in the region (`prove_region_alloc`) — not stack
- Compiler verifies all captured variables are immutable in the lambda body (E396)
- `prove_par_map` call signature updated to thread through `ctx`

Register `par_map` (and new `par_filter`, `par_reduce`, `par_each`) in stdlib,
dispatch from `_emit_calls.py`.

---

## Implementation Plan

### Step 1 — Add `captures` to `LambdaExpr` (`ast_nodes.py`)

```python
@dataclass(frozen=True)
class LambdaExpr:
    params: list[str]
    body: Expr
    span: Span
    captures: list[str] = field(default_factory=list)  # filled by checker
```

`LambdaExpr` is frozen, so the checker cannot mutate it in place. The checker must
produce a **new** `LambdaExpr` with `captures` populated, or store captures out-of-band
in a `dict[int, list[str]]` keyed on `id(expr)` on the checker itself. Out-of-band
is simpler (no AST surgery): add `self._lambda_captures: dict[int, list[str]] = {}`
on `Checker.__init__`, and expose it so the emitter can read it.

The emitter accesses it as `self._lambda_captures.get(id(expr), [])`.

---

### Step 2 — Rework HOF C runtime signatures for ctx pass-through

Current `Prove_MapFn = void *(*)(void *)` (one arg). With captures, all HOF callback
types need a ctx pointer:

```c
// prove_hof.h  (or update each affected header)
typedef void *(*Prove_MapFn)(void *elem, void *ctx);
typedef bool  (*Prove_FilterFn)(void *elem, void *ctx);
typedef void *(*Prove_ReduceFn)(void *accum, void *elem, void *ctx);
typedef void  (*Prove_EachFn)(void *elem, void *ctx);
```

Update `prove_list_map`, `prove_list_filter`, `prove_list_reduce`, `prove_list_each`
in their `.c/.h` files to pass `ctx` through to every callback invocation.

Update `prove_par_map.c` identically — its `_par_map_worker` must carry and forward ctx.

Existing callers that use named-function (no capture) callbacks: the emitter currently
generates `static void *_lambda_N(void *_arg)` — update all generated lambdas to
accept and ignore `ctx` when there are no captures:

```c
static void *_lambda_1(void *_arg, void *ctx) {
    (void)ctx;
    int64_t x = (int64_t)(intptr_t)_arg;
    return (void *)(intptr_t)(x * 2);
}
```

**Files:** `runtime/prove_hof.h/.c` (or inline headers), `runtime/prove_par_map.h/.c`,
`runtime/prove_list.h` if MapFn is defined there.

---

### Step 3 — Checker: replace E364 with capture collection (`_check_types.py`)

Replace `_check_lambda_captures` (currently raises E364 for any captured local):

```python
def _collect_lambda_captures(
    self,
    expr: Expr,
    param_names: set[str],
    captures: list[str],
) -> None:
    """Walk lambda body; collect names of captured enclosing-scope locals."""
    if isinstance(expr, IdentifierExpr):
        if expr.name not in param_names and expr.name not in captures:
            sym = self.symbols.lookup(expr.name)
            if sym is not None and sym.kind == SymbolKind.VARIABLE:
                captures.append(expr.name)
    elif isinstance(expr, BinaryExpr):
        self._collect_lambda_captures(expr.left, param_names, captures)
        self._collect_lambda_captures(expr.right, param_names, captures)
    elif isinstance(expr, UnaryExpr):
        self._collect_lambda_captures(expr.operand, param_names, captures)
    elif isinstance(expr, CallExpr):
        for arg in expr.args:
            self._collect_lambda_captures(arg, param_names, captures)
    # extend for MatchExpr, FieldExpr, IndexExpr as needed
```

In `_infer_lambda`:

```python
def _infer_lambda(self, expr: LambdaExpr) -> Type:
    self.symbols.push_scope("lambda")
    param_types: list[Type] = []
    param_names = set(expr.params)
    for pname in expr.params:
        pt = TypeVariable(pname)
        param_types.append(pt)
        self.symbols.define(Symbol(
            name=pname, kind=SymbolKind.PARAMETER,
            resolved_type=pt, span=expr.span,
        ))

    captures: list[str] = []
    self._collect_lambda_captures(expr.body, param_names, captures)
    self._lambda_captures[id(expr)] = captures   # store for emitter

    body_type = self._infer_expr(expr.body)
    self.symbols.pop_scope()
    return FunctionType(param_types, body_type)
```

Initialize `self._lambda_captures: dict[int, list[str]] = {}` in `Checker.__init__`.
The emitter accesses it via `self._lambda_captures` (already shared through the mixin
chain).

---

### Step 4 — E396: mutable capture in parallel HOF (`_check_calls.py`)

When dispatching a `par_map`/`par_filter`/`par_reduce`/`par_each` call, after the
lambda is inferred, read its captures and verify none are assigned in the lambda body.
A conservative approximation: reject any capture that appears on the LHS of an
assignment within the lambda body. For the initial implementation, simply reject any
captured name whose symbol was declared `mut` (or, since Prove doesn't have explicit
mut, apply the rule that all captures are read-only in parallel lambdas — the compiler
enforces this structurally).

```python
# In _check_calls.py, parallel HOF dispatch
captures = self._lambda_captures.get(id(lam_expr), [])
for cap in captures:
    sym = self.symbols.lookup(cap)
    # Parallel lambdas: captures must be immutable (no reassignment in body)
    if self._lambda_assigns_name(lam_expr.body, cap):
        self._error(
            "E396",
            f"lambda captures '{cap}' and assigns it — "
            f"parallel HOFs require immutable captures",
            lam_expr.span,
        )
```

Register **E396** in `errors.py`.

---

### Step 5 — Emitter: emit ctx structs in `_emit_hof_lambda` (`_emit_calls.py`)

Extend `_emit_hof_lambda` to read `self._lambda_captures.get(id(expr), [])` and
emit a ctx struct when the capture list is non-empty:

```python
captures = self._lambda_captures.get(id(expr), [])
has_ctx = bool(captures)

if has_ctx:
    struct_name = f"_ctx_{name}"
    # Emit struct definition (hoisted before the lambda function)
    struct_fields = "\n".join(
        f"    {map_type(self._locals[c]).decl} {c};"
        for c in captures
    )
    struct_def = f"struct {struct_name} {{\n{struct_fields}\n}};\n"
    self._lambdas.append(struct_def)

# Generate the static callback, now with (void *_arg, void *_ctx) signature:
if kind == "map":
    param = expr.params[0] if expr.params else "_x"
    saved_locals = dict(self._locals)
    self._locals[param] = elem_type
    body_code = self._emit_expr(expr.body)
    body_type = self._infer_expr_type(expr.body)
    self._locals = saved_locals
    body_ct = map_type(body_type)
    wrap = "(void*)" if body_ct.is_pointer else "(void*)(intptr_t)"
    ctx_unpack = ""
    if has_ctx:
        ctx_unpack = (
            f"    struct {struct_name} *_c = (struct {struct_name} *)_ctx;\n"
            + "".join(
                f"    {map_type(self._locals.get(c, INTEGER)).decl} {c} = _c->{c};\n"
                for c in captures
            )
        )
    lam = (
        f"static void *{name}(void *_arg, void *_ctx) {{\n"
        f"    (void)_ctx;\n"   # removed if has_ctx
        f"    {elem_ct.decl} {param} = {elem_unwrap}_arg;\n"
        f"{ctx_unpack}"
        f"    return {wrap}({body_code});\n"
        f"}}\n"
    )
    # ... similar for filter/reduce/each
```

**Parallel HOF ctx allocation** (Step 5b): for `par_map`, the ctx struct must be
heap-allocated. Emit region allocation at the call site:

```c
// Sequential (map/filter/reduce/each):
struct _ctx_1 _c1 = { .factor = factor };
prove_list_map(xs, _lambda_1, &_c1);

// Parallel (par_map):
struct _ctx_1 *_c1 = prove_region_alloc(sizeof(struct _ctx_1));
_c1->factor = factor;
prove_par_map(xs, _lambda_1, _c1, nworkers);
```

The emitter already has `self._needed_headers` — add `"prove_par_map.h"` for parallel
HOFs.

---

### Step 6 — stdlib_loader: register par_map (and par_filter, par_reduce, par_each)

In `stdlib_loader.py`, inside `_register_module("List")` (or wherever sequential HOFs
are registered), add:

```python
# Parallel HOFs — require pure (transforms/validates/reads/creates/matches) callbacks
_reg("par_map",    [LIST_VALUE, FUNC_TYPE], LIST_VALUE, module="List", pure=True)
_reg("par_filter", [LIST_VALUE, FUNC_TYPE], LIST_VALUE, module="List", pure=True)
_reg("par_reduce", [LIST_VALUE, VALUE_TYPE, FUNC_TYPE], VALUE_TYPE, module="List", pure=True)
_reg("par_each",   [LIST_VALUE, FUNC_TYPE], UNIT,       module="List", pure=False)
```

The `pure=True` flag is used by the checker's verb-purity enforcement (E368 equivalent)
to ensure only pure verb functions are passed as callbacks.

---

### Step 7 — C runtime: add par_filter, par_reduce, par_each

Currently only `prove_par_map.c/.h` exists. Add:

- `runtime/prove_par_filter.c/.h` — parallel filter (collect results from workers,
  then compact; workers write to per-chunk output lists, main thread concatenates)
- `runtime/prove_par_reduce.c/.h` — parallel reduce (split, reduce per-chunk, then
  sequential final-reduce across chunk results)
- `runtime/prove_par_each.c/.h` — parallel each (same as par_map but void return;
  simpler since no output collection needed)

All follow the same pthreads pattern in `prove_par_map.c`. The new files must be added
to `_RUNTIME_FUNCTIONS` in `c_runtime.py` (dependency group `"prove_par_map"` or new
groups — add new groups if the symbols are only used by specific calls).

---

### Step 8 — Emitter dispatch: _emit_hof_par_map etc. (`_emit_calls.py`)

Add dispatch cases in `_emit_call` for `par_map`, `par_filter`, `par_reduce`, `par_each`
analogous to the existing `_emit_hof_map`, `_emit_hof_filter`, etc.

For `par_map`:

```python
def _emit_hof_par_map(self, expr: CallExpr) -> str:
    self._needed_headers.add("prove_par_map.h")
    list_arg = self._emit_expr(expr.args[0])
    list_type = self._infer_expr_type(expr.args[0])
    elem_type = list_type.element if isinstance(list_type, ListType) else INTEGER

    fn_name = self._emit_hof_lambda(expr.args[1], elem_type, "par_map")

    captures = self._lambda_captures.get(id(expr.args[1]), [])
    if captures:
        # Region-allocate ctx struct (emitted by _emit_hof_lambda Step 5)
        ctx_var = self._tmp()
        struct_nm = f"_ctx_{fn_name}"
        self._line(f"struct {struct_nm} *{ctx_var} = prove_region_alloc(sizeof(struct {struct_nm}));")
        for c in captures:
            self._line(f"{ctx_var}->{c} = {c};")
        return f"prove_par_map({list_arg}, {fn_name}, {ctx_var}, 0)"
    return f"prove_par_map({list_arg}, {fn_name}, NULL, 0)"
    # 0 = default worker count (runtime picks based on list length / CPU count)
```

`par_filter`, `par_reduce`, `par_each` follow the same pattern.

---

### Step 9 — Error registration (`errors.py`)

Register **E396**:

```python
# E396: mutable capture in parallel lambda
DIAGNOSTIC_DOCS["E396"] = f"{_DOCS_BASE}#E396"
```

---

### Step 10 — Tests

**Checker tests (`tests/test_checker_types.py`):**

```python
# Sequential lambda with capture — ok after this change
def test_sequential_lambda_capture():
    check("""
        transforms result(xs List<Value>, factor Integer) List<Value>
        from map(xs, |x| => x * factor)
    """)

# Parallel lambda with immutable capture — ok
def test_par_map_lambda_capture_immutable():
    check("""
        transforms result(xs List<Value>, factor Integer) List<Value>
        from par_map(xs, |x| => x * factor)
    """)

# Parallel lambda that tries to assign a capture — E396
def test_par_map_lambda_capture_mutable_e396():
    check_fails("""
        transforms result(xs List<Value>, factor Integer) List<Value>
        from par_map(xs, |x| => factor + x)   // factor is captured and... ok
    """, ...)  # actually need an assignment in body to trigger E396
    # Real E396 test requires a multi-stmt lambda body — defer until those are supported
```

**Runtime tests (`tests/test_par_map_runtime_c.py`):**
Extend with a ctx-passing test that verifies the new two-argument `Prove_MapFn`
signature works correctly.

**E2E tests:** Add a `.prv` file in `examples/` that uses `par_map` with a capturing
lambda and verify it compiles and produces correct output via `python scripts/test_e2e.py`.

---

### Step 11 — Documentation

- `docs/functions.md` — remove *Upcoming* from closures note for sequential HOFs;
  add `par_map`/`par_filter`/`par_reduce`/`par_each` to the parallel section
- `docs/diagnostics.md` — document E396
- `docs/roadmap.md` — move from Exploring to In Progress

---

## Files to Touch (summary)

| File | Change |
|------|--------|
| `prove-py/src/prove/ast_nodes.py` | Add `captures: list[str]` field to `LambdaExpr` |
| `prove-py/src/prove/checker.py` | Add `self._lambda_captures: dict[int, list[str]]` |
| `prove-py/src/prove/_check_types.py` | Replace `_check_lambda_captures` (E364) with `_collect_lambda_captures`; populate `_lambda_captures` |
| `prove-py/src/prove/_check_calls.py` | Add E396 check for parallel HOF lambda captures |
| `prove-py/src/prove/_emit_calls.py` | Extend `_emit_hof_lambda` for ctx structs; add `_emit_hof_par_map` etc. |
| `prove-py/src/prove/stdlib_loader.py` | Register `par_map`, `par_filter`, `par_reduce`, `par_each` |
| `prove-py/src/prove/errors.py` | Register E396 |
| `prove-py/src/prove/c_runtime.py` | Add `prove_par_filter`, `prove_par_reduce`, `prove_par_each` to `_RUNTIME_FUNCTIONS` |
| `prove-py/src/prove/runtime/prove_par_map.h/.c` | Update `Prove_MapFn` signature to `(void *elem, void *ctx)` |
| `prove-py/src/prove/runtime/prove_hof.h/.c` (or equivalent) | Update all HOF callback types and list iteration functions for `ctx` pass-through |
| `prove-py/src/prove/runtime/prove_par_filter.c/.h` | New: parallel filter |
| `prove-py/src/prove/runtime/prove_par_reduce.c/.h` | New: parallel reduce |
| `prove-py/src/prove/runtime/prove_par_each.c/.h` | New: parallel each |
| `prove-py/tests/test_checker_types.py` | Add lambda capture tests |
| `prove-py/tests/test_par_map_runtime_c.py` | Extend for ctx-passing signature |
| `docs/functions.md` | Remove *Upcoming* from closures; add par HOF docs |
| `docs/diagnostics.md` | Document E396 |

---

## Open Questions

1. **ctx signature change is breaking.** Updating `Prove_MapFn` from `(void *)` to
   `(void *, void *)` is a C ABI break — all existing generated lambdas and runtime
   internals must be updated atomically. There is no incremental path. Do this in
   one commit.

2. **Multi-statement lambda bodies.** `|x| => from ...` is not in scope here. Deferred
   until single-expression lambdas with captures are stable.

3. **E396 trigger.** Assigning a captured variable in a single-expression lambda body
   is impossible in current Prove syntax (no `=` in expression position). E396 will
   become meaningful when multi-statement lambdas are added. Register the error now,
   but its checker check is a no-op until then. Document this in the error registration.

4. **Number of par_map workers.** The runtime `prove_par_map(list, fn, ctx, nworkers)`
   signature uses `0` to mean "auto". The Prove interface could expose the worker count
   as an optional third argument or always auto-select. Start with auto-only; add
   explicit count later if needed.

5. **Escape analysis interaction.** `_emit_hof_lambda` generates hoisted static
   functions. If the optimizer's escape analysis (`optimizer.py`) runs on the lambda
   body, it must be aware that captured variables are referenced by pointer in the ctx
   struct — they must not be eliminated. Verify after integration.

---

## After Implementation

- Delete this file
- Update `docs/roadmap.md` (remove from Exploring)
- Update `docs/functions.md`: remove *Upcoming* from closures note for all HOFs
