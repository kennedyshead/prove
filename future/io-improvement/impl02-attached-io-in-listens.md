# Attached IO in `listens` — Enabling IO via Coroutine Delegation

## Problem

`listens` bodies currently cannot perform IO. The checker rejects blocking
`inputs`/`outputs` calls with E371. This is correct — blocking IO inside a
cooperative loop would stall the yield cycle and freeze all coroutines sharing
the scheduler.

However, real event loops need IO: logging events, writing state, reading
configuration. The `detached` verb can already do IO freely (it runs
independently), but the results can't be collected — it's fire-and-forget.

## Solution: `attached` as IO Bridge

Allow `listens` arms to call `attached` functions via `&`. The `attached`
function spawns its own coroutine, does the IO there, and yields cooperatively
until done. The `listens` loop resumes only after the `attached` call completes.

This is safe because:
1. The blocking IO happens in the `attached` coroutine's own stack
2. The `listens` loop yields while waiting (cooperative, not blocked)
3. No shared mutable state (Prove's purity guarantees)

### Syntax

```prove
type Command is
    Process(path String)
  | Exit

/// Read a file — attached does the IO, listens awaits the result.
attached load(path String) String
from
    content as String = file(path)!
    content

/// Process commands — listens loop with IO via attached.
listens processor(cmd Command)
from
    Exit          => cmd
    Process(path) => load(path)&
```

### New Error: E377 — `attached` called outside async body

Currently `attached` can be called from any async body. With this change,
add a stricter rule:

| Code | Trigger | Severity |
|------|---------|----------|
| E377 | `attached` function with IO called outside a `listens` or `attached` body | Error |

The rationale: `attached` functions that contain blocking IO are only safe
when called from a context that cooperatively yields (i.e., another `attached`
or a `listens` loop). Calling an IO-bearing `attached` from `main` or a pure
function would block without cooperative yielding.

**Note:** `attached` functions that do NOT contain IO (pure computation offloaded
to a coroutine) remain callable from any async body. The error only triggers
when the `attached` body contains `inputs`/`outputs` calls.

## Implementation

### Phase 1: Lift E371 for `attached` bodies

Currently `checker.py:1567`:
```python
if sig.verb in _BLOCKING_VERBS and fd.verb != "detached":
```

Change to:
```python
if sig.verb in _BLOCKING_VERBS and fd.verb not in ("detached", "attached"):
```

This allows `attached` bodies to call `inputs`/`outputs`. The safety is
provided by the coroutine model — `attached` has its own stack and yields
cooperatively to its caller.

### Phase 2: Validate `attached` with IO is only called from async context

Add a new check: when an `attached` function contains IO calls, it must only
be called (via `&`) from a `listens` or another `attached` body.

In `_check_async_expr`, after resolving the callee:
```python
if isinstance(expr, AsyncCallExpr):
    callee_sig = self.symbols.resolve_function_any(callee_name)
    if callee_sig and callee_sig.verb == "attached":
        if self._attached_has_io(callee_sig):
            if fd.verb not in ("listens", "attached"):
                self._error("E377", ...)
```

### Phase 3: Emitter changes

The emitter already handles `attached` → `_coro` threading correctly.
The `listens` body emits a cooperative loop where `&` calls pass `_coro`.
An `attached` function called from a `listens` arm already:
1. Spawns a child coroutine
2. Yields the parent's `_coro` while the child runs
3. Resumes the parent when the child completes

No emitter changes needed — the existing `attached` codegen handles this.

### Phase 4: Tests

- Checker test: `attached` with IO passes when called from `listens` via `&`
- Checker test: `attached` with IO errors (E377) when called from `main`
- E2e test: `listens` loop that reads a file via `attached` and processes content
- E2e test: nested `attached` (attached calling attached with IO)

## Exit Criteria

- [ ] `attached` bodies can call `inputs`/`outputs` (E371 lifted)
- [ ] E377 emitted when IO-bearing `attached` called outside async body
- [ ] `listens` can call `attached` with IO via `&`
- [ ] E2e test: event loop reads file, processes content, exits
- [ ] Docs updated: syntax.md, types.md, diagnostics.md
