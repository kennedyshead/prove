# 12c — Checker Enforcement Rules

**Parent:** [`12-listens-event-dispatcher.md`](12-listens-event-dispatcher.md)
**Status:** Planned
**Depends on:** 12a (AST `event_type` field), 12b (`Attached` builtin type)
**Files:** `src/prove/checker.py`, `src/prove/_check_calls.py`, `src/prove/_check_types.py`

## Context

The reworked `listens` verb uses:
- `List<Attached>` as its first parameter (registered worker functions)
- `event_type AlgebraicType` as a block-level annotation (the message protocol)
- Match arms that exhaust the algebraic type's variants

**New syntax:**
```prove
type Event is Data(payload String) | Exit

attached producer() Event
from
    Data("hello")

listens handler(workers List<Attached>)
    event_type Event
from
    Exit           => handler
    Data(payload)  => fire(payload)&

main() Unit
from
    handler([producer])&
```

**Existing async verb checks in checker.py:**
- Line 125: `_ASYNC_VERBS = frozenset({"detached", "attached", "listens"})`
- Line 1591: E374 check — `listens`/`detached` cannot have return types
- Line 1606–1607: `listens`/`streams` exempt from I367 match restriction
- Line 2273–2290: E398/I377 — IO-bearing attached call-site checks
- Line 2375: Implicit match subject resolution for `matches`/`listens`/`streams`

## Overview

The checker enforces all semantic rules for the new `listens` event dispatcher pattern. This is the core enforcement layer — every rule here prevents invalid programs from reaching the emitter.

## New Error Codes

| Code | Severity | Message | Trigger |
|------|----------|---------|---------|
| E399 | Error | `event_type` annotation is only valid on `listens` verb | `event_type` on transforms/validates/etc. |
| E400 | Error | `listens` verb requires an `event_type` annotation | `listens` function missing `event_type` |
| E401 | Error | `event_type` must reference an algebraic type | `event_type Integer` (primitive) or record type |
| E402 | Error | `listens` first parameter must be `List<Attached>` | Wrong parameter type |
| E403 | Error | registered function `X` is not an `attached` verb | Non-attached function in the `List<Attached>` literal |
| E404 | Error | return type of `X` does not match a variant of event type `Y` | Attached function returns wrong type |

## Enforcement Rules

### Rule 1: `event_type` only on `listens` (E399)

In `_check_function_def()`, after parsing annotations:

```python
if fd.event_type is not None and fd.verb != "listens":
    self._error("E399", "`event_type` annotation is only valid on `listens` verb", fd.span)
```

### Rule 2: `listens` requires `event_type` (E400)

In the existing `listens` validation block (where E374 is checked):

```python
if fd.verb == "listens" and fd.event_type is None:
    self._error("E400", "`listens` verb requires an `event_type` annotation", fd.span)
```

### Rule 3: `event_type` must be algebraic (E401)

Resolve the type referenced by `event_type` and verify it's an algebraic type (has variants):

```python
if fd.event_type is not None:
    resolved = self._resolve_type(fd.event_type)
    if resolved is not None and not isinstance(resolved, AlgebraicType):
        self._error("E401", "`event_type` must reference an algebraic type", fd.event_type.span)
```

### Rule 4: First parameter must be `List<Attached>` (E402)

In `_check_function_def()` for `listens` verb:

```python
if fd.verb == "listens":
    if not fd.params:
        self._error("E402", "`listens` first parameter must be `List<Attached>`", fd.span)
    else:
        first_type = self._resolve_type(fd.params[0].type_expr)
        # Check it's List<Attached>
        if not self._is_list_of_attached(first_type):
            self._error("E402", "`listens` first parameter must be `List<Attached>`", fd.params[0].span)
```

Implement `_is_list_of_attached()` helper that checks the resolved type is `List` parameterized with `Attached`.

### Rule 5: Registered functions must be `attached` (E403)

This is a **call-site check**. When the checker sees a `listens` function being called, it inspects the first argument (the list literal) and verifies each element resolves to an `attached` verb function.

In `_check_calls.py`, when inferring a call to a `listens` function:

```python
# If callee is listens and first arg is a list literal:
for elem in list_literal.elements:
    sig = self._symbols.resolve_function_any(elem.name)
    if sig is None or sig.verb != "attached":
        self._error("E403", f"registered function '{elem.name}' is not an `attached` verb", elem.span)
```

### Rule 6: Attached return types must map to event type variants (E404)

At the same call site, verify each registered attached function's return type is a variant of the `event_type` algebraic:

```python
for elem in list_literal.elements:
    sig = self._symbols.resolve_function_any(elem.name)
    if sig and sig.verb == "attached":
        event_type = callee_sig.event_type  # resolved algebraic
        if not self._return_type_matches_variant(sig.return_type, event_type):
            self._error(
                "E404",
                f"return type of '{elem.name}' does not match a variant of "
                f"event type '{event_type.name}'",
                elem.span,
            )
```

Implement `_return_type_matches_variant()` — checks if the return type is one of the algebraic's variant payload types (or the variant itself for unit variants).

### Rule 7: Match arms must exhaust `event_type` variants

The existing exhaustiveness checking for `matches`/`listens` already enforces this against the first parameter's type. With the rework, the match subject becomes the `event_type` rather than the first parameter. Update the implicit match subject resolution:

In `checker.py` around line 2375, where implicit match subjects are resolved for `listens`:

```python
# Old: use first parameter type
# New: use event_type annotation
if fd.verb == "listens" and fd.event_type is not None:
    subject_type = self._resolve_type(fd.event_type)
```

### Rule 8: E151 still enforced (Exit arm required)

No change needed — the existing E151 check looks for an `Exit` arm in `listens`/`streams` bodies. It continues to work against the `event_type` variants.

## Existing Rules — Updates

### E374 (no return type on listens) — unchanged

Already enforced. No changes.

### E371 (no blocking IO in listens body) — unchanged

Already enforced. `listens` bodies still cannot call `inputs`/`outputs`/`streams` directly.

### E398 (IO-bearing attached outside async context) — unchanged

Already enforced. IO-bearing attached functions called via `&` must be from `listens` or `attached` body.

### I377 (attached& outside listens) — unchanged

Already works. Info diagnostic when `attached&` is used outside `listens`.

## Migration: Implicit match subject

The key change is how the implicit match subject is resolved for `listens`:

| | Old | New |
|---|-----|-----|
| Match subject source | First parameter type | `event_type` annotation |
| First parameter purpose | The event value (algebraic) | Worker list (`List<Attached>`) |
| Match dispatches on | Parameter value | Events received from queue |

The emitter-side changes are in [12d](12d-emitter.md). The checker only needs to update type resolution for exhaustiveness.

## Checklist

- [ ] Add error codes E399–E404 to diagnostic registry
- [ ] Implement E399: `event_type` only on `listens`
- [ ] Implement E400: `listens` requires `event_type`
- [ ] Implement E401: `event_type` must be algebraic
- [ ] Implement E402: first param must be `List<Attached>`
- [ ] Implement E403: call-site check — registered functions are `attached`
- [ ] Implement E404: call-site check — return types match event variants
- [ ] Update implicit match subject resolution for `listens` to use `event_type`
- [ ] Add E399–E404 to `docs/diagnostics.md`
- [ ] Update `docs/AGENTS.md` with new error codes
