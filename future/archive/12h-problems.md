# 12h — Problems Discovered During Implementation

**Parent:** [`12-listens-event-dispatcher.md`](12-listens-event-dispatcher.md)
**Status:** Post-implementation issues

## Error Code Conflicts

The 12c plan specified E399-E404 for the new listens errors, but E399 ("ambiguous column type in lookup") and E400 ("match arm returns Unit") were already taken. Renumbered:

- E399 (event_type on non-listens) → **E405**
- E400 (listens missing event_type) → **E406**
- E401-E404 retained as planned

## Variant Names as Return Types

The plan assumed attached functions would declare the parent algebraic type as their return type (e.g., `attached double(x Integer) Event`). The user's intended syntax uses the variant name with a type parameter: `attached double(x Integer) Data<Integer>`.

**Fix applied:** The checker now resolves variant names as types by looking up variant constructors. If a name isn't found as a type but matches a variant constructor of an algebraic type, it resolves to the parent algebraic type. This works for both `SimpleType` and `GenericType` forms.

**Remaining concern:** This resolution is broad — it applies to ALL type positions, not just attached return types. This could have unexpected effects if a user accidentally uses a variant name where they meant a type name. Consider restricting this to return type positions or adding a warning.

## E372 Suppression Flag Ordering

The initial implementation checked `_inside_async_call` before `_in_listens_worker_list` in the E372 check. This caused `double(2)` inside `[double(2)]` to consume the `_inside_async_call` flag meant for the outer `handler()&` call, resulting in a false E372 on handler.

**Fix applied:** Reordered checks so `_in_listens_worker_list` is checked first, returning `ATTACHED` without consuming `_inside_async_call`.

## I376 on Attached Workers

The async_demo shows `I376: attached body has no & calls; consider using inputs instead` on `attached double(x Integer) Data<Integer>`. This is technically correct (the double function body has no `&` calls), but the info is misleading for worker functions that are meant to be simple computation factories for a listens dispatcher. Consider suppressing I376 for attached functions whose return type is a variant of a known event_type.

## Emitter: Untested End-to-End — RESOLVED

The emitter changes (12d) generated C code for the event dispatcher pattern, but the async_demo failed to compile. Multiple issues were discovered and fixed:

### Optimizer DCE Removes Async Functions

`AsyncCallExpr` (the `&` operator) was not handled in the optimizer's dead code elimination pass (`_find_called_in_expr`). Functions called only via `fire("hello")&` or `handler([double(2)])&` were treated as unreachable and removed. Fixed by adding `AsyncCallExpr` handling to five optimizer methods: `_find_called_in_expr`, `_expr_calls`, `_count_uses_in_expr`, `_inline_in_expr`, and `_expr_has_side_effects`.

### `Prove_Event` Name Collision

The runtime's `prove_event.h` defined `Prove_Event` (queue node struct) which collided with user-defined algebraic types named `Event` (emitted as `Prove_Event`). Fixed by renaming the runtime type to `Prove_EventNode` and the queue to `Prove_EventNodeQueue`.

### Event Queue Architecture Replaced with Direct Worker Polling

The original emitter design used a `Prove_EventNodeQueue` as an intermediary between attached workers and the listens dispatcher. This caused multiple issues: brace mismatches in the generated C, incorrect match dispatch (queue nodes vs algebraic types), and unnecessary complexity. Replaced with a direct worker polling model:

- Workers are pre-started coroutines stored in a `Prove_List`
- Listens body iterates the list, resumes each worker to completion, extracts result
- Match dispatches directly on the algebraic event type
- No event queue needed at runtime

### Attached Result Passing via Heap Allocation

Attached functions returning algebraic types (structs in C) cannot pass results through `_coro->result` (which is `void*`) by value. Fixed by heap-allocating the result struct in the attached body (`malloc + store pointer in _coro->result`) and dereferencing in the caller (`*(Type*)_c->result` + `free`).

### Listens Entry Point Signature

The listens entry function initially took a `Prove_Coro *_coro` parameter, which was unnecessary since listens creates its own internal coroutine. Removed from both the entry point and forward declaration.

### Worker List Emission

`[double(2)]` in a listens call was being emitted as a direct function call list. Fixed with `_emit_listens_call` in `_emit_exprs.py` which properly creates args structs, allocates coroutines, starts them, and pushes coro pointers to the list.

### W501 False Positives for Async Verbs

`_PROSE_STEMS` in `_nl_intent.py` had no patterns for `detached`, `attached`, or `streams` verbs. Added stem patterns so narrative coherence checking recognizes these verbs from prose.

## `Attached` Type Semantics

`Attached` is currently a bare `PrimitiveType` that maps to `Prove_CoroFn` (a function pointer). It doesn't carry type information about the attached function's parameters or return type. This means `List<Attached>` is untyped — any attached function fits. A future enhancement could make `Attached<Event>` generic to enforce that all workers in a list produce variants of the same event type at compile time.

## Remove I376 

It forces you to always call a new Coro and always end with an atached which makes it a bad practise.
