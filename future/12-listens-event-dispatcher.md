# Listens Event Dispatcher Rework

**Status:** Planned
**Depends on:** Nothing (self-contained rework of existing `listens` verb)
**Relates to:** `docs/functions.md`, `docs/contracts.md`, `docs/syntax.md`

## Summary

Rework the `listens` verb from a simple cooperative loop into a full **event dispatcher**. The listener takes an explicit list of `attached` verb functions and an algebraic type annotation (`event_type`) that defines the message protocol. Registered attached functions are coroutine producers — when they return a variant of the event type, the dispatcher routes it to the matching match arm.

### Before (current)

```prove
listens handler(event Event)
from
    Exit        => event
    Data(text)  => fire(text)&
```

The parameter `event Event` is ambiguous — it's both the type declaration and an implicit value that doesn't come from anywhere concrete.

### After (new design)

```prove
listens handler(workers List<Attached>)
    event_type Event
from
    Exit           => handler
    Data(payload)  => fire(payload)&

main() Unit
from
    handler([function1, function2])&
```

- First parameter: `List<Attached>` — explicit list of attached verb functions that produce events
- `event_type Event` — block-level annotation declaring the algebraic type for dispatch
- Match arms exhaust the `event_type` variants
- Runtime: event queue per listener, attached functions push variants, dispatcher receives and routes

## Sub-Plans

The implementation is split across these files:

| # | File | What it covers |
|---|------|---------------|
| 1 | [`12a-ast-parser.md`](12a-ast-parser.md) | AST node changes (`event_type` field) + parser support |
| 2 | [`12b-attached-type.md`](12b-attached-type.md) | New `Attached` builtin type in type system |
| 3 | [`12c-checker.md`](12c-checker.md) | All checker enforcement rules |
| 4 | [`12d-emitter.md`](12d-emitter.md) | C emitter changes for the new dispatch model |
| 5 | [`12e-runtime.md`](12e-runtime.md) | C runtime: event queue, send/receive primitives |
| 6 | [`12f-tests.md`](12f-tests.md) | Unit tests, e2e tests, checker tests |
| 7 | [`12g-docs.md`](12g-docs.md) | Documentation updates (functions.md, contracts.md, syntax.md, AGENTS.md) |

## Implementation Order

```
12a (AST/parser) ──┐
12b (Attached type) ├──▶ 12c (checker) ──▶ 12d (emitter) ──▶ 12e (runtime) ──▶ 12f (tests)
                    │                                                              │
                    └──────────────────────────────────────────────────────────────▶ 12g (docs)
```

- **12a** and **12b** can be done in parallel — no dependencies between them
- **12c** depends on both 12a and 12b (needs `event_type` in AST + `Attached` type)
- **12d** depends on 12c (emitter reads checker-validated structures)
- **12e** depends on 12d (runtime primitives must match what the emitter emits)
- **12f** runs after 12e (integration tests need the full pipeline)
- **12g** can start after 12c (checker rules are the primary doc content) but should be finalized after 12f

## Design Decisions

### Why `event_type` as a block-level annotation (not a parameter)

The algebraic type is metadata about the dispatch protocol, not a runtime value passed to the function. Placing it alongside `ensures`/`requires` keeps the parameter list clean and makes the intent explicit: "this listener dispatches on `Event` variants."

### Why `Attached` as a dedicated type (not `Verb`)

`Verb` is too broad — it could reference any verb family. `Attached` constrains to async-capable functions that produce values (have return types). The checker validates:
- Each function in the list is actually an `attached` verb
- Each function's return type is a variant of the `event_type`

### Why an explicit worker list (not implicit discovery)

Explicit registration makes the data flow visible at the call site. The caller sees exactly which attached functions feed into the listener. No magic, no implicit coupling.

### Exit arm semantics

The `Exit` arm terminates the dispatcher loop. It must be present (E151, already enforced). The exit arm expression is the loop's termination value (though `listens` has no return type, so this is `Unit`).
