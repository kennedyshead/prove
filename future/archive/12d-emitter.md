# 12d — C Emitter Changes

**Parent:** [`12-listens-event-dispatcher.md`](12-listens-event-dispatcher.md)
**Status:** Planned
**Depends on:** 12c (checker validates structure before emission)
**Files:** `c_emitter.py`, `_emit_stmts.py`, `_emit_exprs.py`, `_emit_calls.py`

## Overview

The emitter transforms the validated `listens` function into C code that implements an event dispatcher: a coroutine with an event queue, where registered attached functions produce events and the dispatcher loop receives and pattern-matches them.

## Context

The reworked `listens` verb uses:
- `List<Attached>` as its first parameter (registered worker functions)
- `event_type AlgebraicType` as a block-level annotation (the message protocol)
- Match arms that exhaust the algebraic type's variants
- A runtime event queue (`Prove_EventQueue` from `prove_event.h`) for communication

**New syntax:**
```prove
listens handler(workers List<Attached>)
    event_type Event
from
    Exit           => handler
    Data(payload)  => fire(payload)&
```

## Current Emission (to be replaced)

The current code lives in `c_emitter.py`:
- `_emit_async_function` (line 868): dispatches to detached/attached/listens emission
- `_emit_listens_body` (line 1042): emits `while(1)` + yield + cancel checks + match body
- Forward declarations (line 725): emits signatures for async functions
- Implicit match subject (lines 507 in `_emit_exprs.py`, 1015 in `_emit_stmts.py`): resolves first parameter as match subject for `listens`

**Current `_emit_listens_body`:**
```python
def _emit_listens_body(self, fd: FunctionDef, param_types: list) -> None:
    self._line("while (1) {")
    self._indent += 1
    self._line("if (prove_coro_cancelled(_coro)) break;")
    self._line("prove_coro_yield(_coro);")
    self._line("if (prove_coro_cancelled(_coro)) break;")
    for stmt in fd.body:
        self._emit_stmt(stmt)
    self._indent -= 1
    self._line("}")
```

**Current public entry point for listens (in `_emit_async_function`):**
```python
elif fd.verb == "listens":
    params_list = [f"{map_type(pt).decl} {p.name}" for p, pt in zip(fd.params, param_types)]
    params_str = ", ".join(["Prove_Coro *_coro"] + params_list) if params_list else "Prove_Coro *_coro"
    self._line(f"void {mangled}({params_str}) {{")
    # ... spawns coro, pumps to completion ...
```

The new emission must:
1. Accept a list of attached function references as the first parameter
2. Create an event queue
3. Spawn each registered attached function as a child coroutine
4. Run a dispatcher loop that receives events from the queue and dispatches to match arms

## New C Emission Structure

### Generated code for a `listens` function

Given:
```prove
listens handler(workers List<Attached>)
    event_type Event
from
    Exit           => handler
    Data(payload)  => fire(payload)&
```

The emitter produces:

#### 1. Event queue struct

```c
typedef struct {
    Prove_Event *head;
    Prove_Event *tail;
    int count;
} _listens_handler_queue;
```

Or reuse a generic `Prove_EventQueue` from the runtime (see [12e](12e-runtime.md)).

#### 2. Event wrapper

Events are tagged unions matching the algebraic type. The emitter already emits tagged union structs for algebraic types — the event queue stores pointers to these.

#### 3. Coroutine body function

```c
static void _listens_handler_body(Prove_Coro *_coro) {
    _listens_handler_args *_a = (_listens_handler_args *)_coro->arg;
    Prove_EventQueue *_queue = _a->_queue;

    // Spawn registered attached workers as child coroutines
    for (int _i = 0; _i < _a->workers->length; _i++) {
        Prove_CoroFn _fn = (Prove_CoroFn)prove_list_get(_a->workers, _i);
        Prove_Coro *_child = prove_coro_new(_fn, PROVE_CORO_STACK_DEFAULT);
        prove_coro_start(_child, _queue);  // workers send events to the queue
    }

    // Dispatcher loop
    while (1) {
        if (prove_coro_cancelled(_coro)) break;

        // Receive next event from queue (blocks/yields until available)
        Prove_Event *_ev = prove_event_queue_recv(_queue, _coro);
        if (!_ev) break;  // queue closed / cancelled

        // Match dispatch (same switch-case as current algebraic matching)
        switch (_ev->tag) {
            case Event_Exit:
                goto _listens_exit;
            case Event_Data: {
                Prove_String *payload = _ev->data.payload;
                // fire(payload)& — emit async call
                detached_fire(payload);
                break;
            }
        }
        prove_coro_yield(_coro);
    }
    _listens_exit:;
}
```

#### 4. Public entry point

```c
void listens_handler(Prove_Coro *_coro, Prove_List *workers) {
    Prove_EventQueue *_queue = prove_event_queue_new();
    _listens_handler_args *_a = malloc(sizeof(_listens_handler_args));
    _a->workers = workers;
    _a->_queue = _queue;
    Prove_Coro *_c = prove_coro_new(_listens_handler_body, PROVE_CORO_STACK_DEFAULT);
    prove_coro_start(_c, _a);
    while (!prove_coro_done(_c)) prove_coro_resume(_c);
    prove_event_queue_free(_queue);
    prove_coro_free(_c);
}
```

## Key Changes to `_emit_async_function`

### Args struct

Add `Prove_EventQueue *_queue` to the args struct for `listens`:

```python
if fd.verb == "listens":
    self._line(f"Prove_EventQueue *_queue;")
```

### Body function

Replace `_emit_listens_body()` entirely:

1. **Worker spawning** — iterate the `List<Attached>` parameter and spawn each as a child coro, passing the queue as their arg
2. **Receive loop** — `prove_event_queue_recv()` blocks (yields) until an event is available
3. **Match dispatch** — same switch-case emission as existing algebraic matching, but the subject is the received event, not a parameter

### Public entry point

- Create the event queue before spawning the coro
- Pass queue pointer via args struct
- Free the queue after the coro completes

### Forward declarations

Update the forward declaration emission (around line 725) to use the new signature: `void mangled(Prove_Coro *_coro, Prove_List *workers)` instead of the old parameter-based signature.

## Implicit match subject

Update both `_emit_match_expr` (line 507) and `_emit_match_stmt` (line 1015):

For `listens` verb, the match subject is no longer the first parameter — it's `_ev` (the received event from the queue). Change the implicit subject injection:

```python
if self._current_func.verb == "listens":
    # Subject is the received event, not a parameter
    subject_name = "_ev"
```

## Attached function call-site changes

When an attached function is called from within a `listens` body, it currently passes `_coro` as the first arg. With the event dispatcher model, attached functions that are **registered workers** communicate via the event queue, not direct coro yield. However, `attached` functions called via `&` within match arms (like `fire(payload)&`) still work the same — they're ad-hoc async calls, not registered workers.

The distinction:
- **Registered workers** (in the `List<Attached>`) — spawned at loop start, push events to queue
- **Arm-local async calls** (called with `&` inside match arms) — same as current attached/detached calls

## Checklist

- [ ] Rework `_emit_async_function` for `listens` verb: args struct with queue
- [ ] Rewrite `_emit_listens_body` for event queue receive loop
- [ ] Add worker spawning logic (iterate List<Attached>, spawn child coros)
- [ ] Update implicit match subject to `_ev` for listens
- [ ] Update forward declarations for new listens signature
- [ ] Update public entry point to create/free event queue
- [ ] Ensure arm-local `&` calls still work (detached/attached within arms)
- [ ] Update `docs/AGENTS.md` with emitter architecture changes
