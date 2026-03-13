# 12f — Tests

**Parent:** [`12-listens-event-dispatcher.md`](12-listens-event-dispatcher.md)
**Status:** Planned
**Depends on:** 12a–12e (full pipeline must work)
**Files:** `tests/test_checker_verbs.py`, `tests/test_parser.py`, `tests/test_c_emitter.py`, `tests/test_event_runtime_c.py` (new), e2e tests in `examples/`

## Context

The reworked `listens` verb changes from:
```prove
// OLD
listens handler(event Event)
from
    Exit => event
    Data(payload) => fire(payload)&
```
to:
```prove
// NEW
listens handler(workers List<Attached>)
    event_type Event
from
    Exit           => handler
    Data(payload)  => fire(payload)&
```

**Test infrastructure:**
- Checker tests use `check()`, `check_fails()`, `check_warns()`, `check_info()` from `tests/helpers.py`
- Runtime C tests use `compile_and_run()` from `tests/runtime_helpers.py`
- E2e tests are `.prv` files in `examples/` run by `scripts/test_e2e.py`
- All Python tests: `python -m pytest tests/ -v`

## Overview

Comprehensive test coverage for the `listens` event dispatcher rework. Tests span all layers: parser, checker, emitter, runtime, and end-to-end.

## Parser Tests (`test_parser.py`)

### New tests

- **Parse `event_type` annotation** — verify `FunctionDef.event_type` is populated with the correct `TypeExpr`
- **Parse `event_type` with other annotations** — `event_type` alongside `ensures`, `requires`, etc.
- **Duplicate `event_type`** — parser error on `event_type Event` appearing twice
- **`event_type` position** — accepted in any annotation position (parser accepts, checker validates)

## Checker Tests (`test_checker_verbs.py`)

### Update existing tests

The existing `TestAsyncVerbs` class (in `tests/test_checker_verbs.py`) has tests for `listens` that use the old parameter-based syntax. All must be updated to new syntax:

- `test_attached_with_io_from_listens_ok` (line 259) — currently uses `listens loop(cmd Cmd)`, update to `listens loop(workers List<Attached>)\n    event_type Cmd`
- `test_listens_with_return_type_error` (line 320) — currently uses `listens loop(src Integer) Integer`, update syntax but same E374 behavior
- `test_attached_with_ampersand_in_listens_ok` (line 384) — currently uses `listens handler(ev Event)`, update to new syntax
- `test_attached_with_ampersand_in_streams_info` (line 402) — references listens in docstring, verify it still makes sense

**Example old test code (line 268):**
```python
"listens loop(cmd Cmd)\n"
"    from\n"
"        Exit  => cmd\n"
"        Go    => _ as String = reader()&\n"
```

**Updated:**
```python
"listens loop(workers List<Attached>)\n"
"    event_type Cmd\n"
"    from\n"
"        Exit  => loop\n"
"        Go    => _ as String = reader()&\n"
```

### New checker tests

| Test | Error code | What it checks |
|------|-----------|---------------|
| `test_event_type_on_non_listens_error` | E399 | `event_type` on `transforms` function → error |
| `test_event_type_on_outputs_error` | E399 | `event_type` on `outputs` function → error |
| `test_listens_missing_event_type_error` | E400 | `listens` without `event_type` → error |
| `test_event_type_non_algebraic_error` | E401 | `event_type Integer` → error |
| `test_event_type_record_error` | E401 | `event_type User` (record type) → error |
| `test_listens_wrong_first_param_error` | E402 | `listens f(x Integer)` → error |
| `test_listens_no_params_error` | E402 | `listens f()` → error |
| `test_registered_non_attached_error` | E403 | `[transforms_fn]` in list → error |
| `test_registered_detached_error` | E403 | `[detached_fn]` in list → error |
| `test_attached_return_type_mismatch_error` | E404 | Attached returns `String` but event has `Integer` payload |
| `test_listens_valid_full_pattern` | — | Happy path: `List<Attached>` + `event_type` + complete match arms |
| `test_listens_exhaustiveness` | — | Missing variant in match arms → existing exhaustiveness error |

## Emitter Tests (`test_c_emitter.py`)

### New tests

- **Event queue creation** — verify `prove_event_queue_new()` appears in emitted C
- **Worker spawning** — verify registered attached functions are spawned as child coros
- **Receive loop** — verify `prove_event_queue_recv()` in the dispatcher body
- **Match dispatch on received event** — verify switch-case uses `_ev->tag`
- **Queue cleanup** — verify `prove_event_queue_free()` in entry point

## Runtime Tests (`test_event_runtime_c.py` — new file)

### C runtime unit tests for event queue

Follow the existing pattern in `test_*_runtime_c.py` files using `compile_and_run()`:

| Test | What it verifies |
|------|-----------------|
| `test_event_queue_create_free` | Create queue, free immediately, no leaks |
| `test_event_queue_send_recv` | Send 3 events, recv 3 events in FIFO order |
| `test_event_queue_recv_empty_closed` | Recv on empty closed queue returns NULL |
| `test_event_queue_send_after_close` | Behavior when sending after close (should still accept? or panic?) |
| `test_event_queue_fifo_order` | Tags come back in send order |
| `test_event_queue_with_payload` | Payloads are preserved correctly |

## E2E Tests

### Update existing e2e test

The `examples/async_demo/src/main.prv` must be updated to use the new syntax:

```prove
module Main
  narrative: """
  Demonstrates async verb family: detached, attached, listens.

  fire a detached console output
  """
  System outputs console

  type Event is Data(payload String)
    | Exit

/// Fire and forget — logs a message without waiting.
detached fire(msg String)
from
    console(msg)

/// Spawn and await — doubles an integer.
attached double(x Integer) Integer
from
    x * 2

/// Cooperative loop — processes events until Exit.
listens handler(workers List<Attached>)
    event_type Event
from
    Exit           => handler
    Data(payload)  => fire(payload)&

main() Unit
from
    fire("hello from detached")&
    handler([double])&
```

### New e2e tests

| Test | What it covers |
|------|---------------|
| `listens_single_worker` | One attached worker producing events |
| `listens_multiple_workers` | Multiple attached workers producing different event variants |
| `listens_exit_terminates` | Worker sends Exit, loop terminates |
| `listens_with_attached_io` | Worker does IO (inputs/outputs) inside its body |
| `listens_empty_worker_list` | Edge case: empty list, should exit immediately (or via Exit event) |

### E2e expected failures

If any test is known to fail during incremental implementation, declare in `narrative:` with `Expected to fail: check, build.`

## Checklist

- [ ] Update all existing `listens` tests in `test_checker_verbs.py` to new syntax
- [ ] Add E399–E404 checker tests
- [ ] Add happy-path checker tests
- [ ] Add emitter tests for new C output
- [ ] Create `test_event_runtime_c.py` with queue unit tests
- [ ] Update `examples/async_demo/src/main.prv` to new syntax
- [ ] Add new e2e test files
- [ ] Verify all existing e2e tests still pass (no regressions)
- [ ] Update `docs/AGENTS.md` with test file locations
