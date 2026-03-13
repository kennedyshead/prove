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

## Emitter: Untested End-to-End

The emitter changes (12d) generate C code for the event dispatcher pattern (worker spawning, event queue, receive loop), but no e2e test exercises the full compilation pipeline yet. The async_demo type-checks but hasn't been built. This should be validated with a real e2e build test once the full async pipeline is stable.

## `Attached` Type Semantics

`Attached` is currently a bare `PrimitiveType` that maps to `Prove_CoroFn` (a function pointer). It doesn't carry type information about the attached function's parameters or return type. This means `List<Attached>` is untyped — any attached function fits. A future enhancement could make `Attached<Event>` generic to enforce that all workers in a list produce variants of the same event type at compile time.
