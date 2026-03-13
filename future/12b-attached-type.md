# 12b — Attached Builtin Type

**Parent:** [`12-listens-event-dispatcher.md`](12-listens-event-dispatcher.md)
**Status:** Planned
**Files:** `src/prove/types.py`, `src/prove/checker.py`, `src/prove/c_types.py`, `src/prove/c_runtime.py`, `src/prove/runtime/prove_coro.h`

## Context

The reworked `listens` verb takes `List<Attached>` as its first parameter — a list of registered `attached` verb functions that produce events for the dispatcher. `Attached` is a new builtin type that restricts function references to only `attached` verbs.

**How it's used in Prove code:**
```prove
listens handler(workers List<Attached>)
    event_type Event
from
    Exit           => handler
    Data(payload)  => fire(payload)&

main() Unit
from
    handler([producer1, producer2])&
```

The checker validates that every function in the list literal is an `attached` verb and that its return type maps to a variant of the `event_type` algebraic. This plan only covers the type definition and registration — checker enforcement is in 12c.

## Overview

Introduce `Attached` as a new builtin type representing a typed reference to an `attached` verb function. This is the async-specific counterpart to `Verb` — it constrains function references to only `attached` verbs and carries the return type for checker validation.

## Type System: `types.py`

### Define `Attached` type

`Attached` is a builtin type (like `Verb`). It does not need to be generic — the return type validation is done by the checker against the `event_type` annotation, not by the type system itself.

```python
# In types.py — add alongside existing builtin definitions
ATTACHED = PrimitiveType("Attached")
```

The type `List<Attached>` is how it appears in function signatures. At the C level, this maps to a list of function pointers (or coro-spawning thunks).

## Checker Registration: `checker.py`

### Register as builtin type

Add `Attached` to the builtin type registration in `_register_builtins()`:

```python
self.symbols.define_type("Attached", PrimitiveType("Attached"))
```

Also add `"Attached"` to `_BUILTIN_TYPE_NAMES` set (around line 175 in checker.py, alongside `Value`, `Source`, `Verb`, etc.) so it doesn't require an import. The current set is:

```python
_BUILTIN_TYPE_NAMES = frozenset(
    {
        "Value",
        "Source",
        "Verb",
    }
)
```

## C Type Mapping: `c_types.py`

### Map `Attached` to C representation

`Attached` maps to a function pointer type in C. Since attached functions have the signature `RetType mangled_name(Prove_Coro *_caller, ...)`, the C representation for a generic `Attached` reference is a void function pointer:

```c
typedef void (*Prove_Attached)(Prove_Coro *);
```

Or more precisely, since the dispatcher needs to spawn them as coroutines, the reference should be a `Prove_CoroFn` (pointer to the body function):

```c
typedef void (*Prove_CoroFn)(Prove_Coro *);
```

Add to `map_type()` in `c_types.py`:

```python
if isinstance(t, PrimitiveType) and t.name == "Attached":
    return CType("Prove_CoroFn", "Prove_CoroFn")
```

`List<Attached>` then becomes `Prove_List *` containing `Prove_CoroFn` entries — the same list infrastructure used for `List<Value>`.

## Runtime Metadata: `c_runtime.py`

No new runtime functions needed for the type itself. The coro body function pointer exists in `prove_coro.h` (line 46) as an anonymous type inside the struct:

```c
typedef struct Prove_Coro {
    // ...
    void (*fn)(struct Prove_Coro *);  /* body function (sequential mode) */
} Prove_Coro;
```

Extract this into a named typedef so the emitter can reference it:

```c
typedef void (*Prove_CoroFn)(Prove_Coro *);
```

Place this typedef after the `Prove_Coro` struct definition in `prove_coro.h`. The struct's `fn` field can then use it too: `Prove_CoroFn fn;`.

## Checklist

- [ ] Add `ATTACHED = PrimitiveType("Attached")` to `types.py`
- [ ] Register `Attached` in `_register_builtins()` in `checker.py`
- [ ] Add `"Attached"` to `_BUILTIN_TYPE_NAMES`
- [ ] Add `Attached` → `Prove_CoroFn` mapping in `c_types.py` `map_type()`
- [ ] Add `Prove_CoroFn` typedef to `prove_coro.h` if not present
- [ ] Update `docs/AGENTS.md` with the new builtin type
