# Event Dispatch: renders/listens Pipeline

## Status: In Progress

**Implementation plan:** `.claude/plans/precious-chasing-fountain.md`

## Problem

The terminal_todo example compiles and starts but freezes — no output, no key handling, Ctrl+C doesn't work. The event dispatch pipeline between `renders`, `listens`, and the terminal backend is not wired up.

## Root Causes

1. **listens emitted as coroutine worker-iterator** — iterates pre-started workers in the `List<Attached>` param, but should be an inline event translator that receives raw KeyDown events and returns app-specific TodoEvent variants
2. **LookupPattern not emitted in match arms** — `Key:Escape`, `Key:"k"` etc. are parsed and checked but silently dropped during C emission (only `VariantPattern` and `WildcardPattern` handled)
3. **renders doesn't invoke listens translators** — raw KeyDown events (tag=2) hit the renders match body which only handles TodoEvent variant tags (Draw, ToggleDone, etc.)
4. **`prove_event_queue_recv(_eq, NULL)` crashes** — renders passes NULL coro, causing NULL deref in `prove_coro_cancelled(coro)`
5. **Event queue not thread-safe** — terminal input thread writes from pthread without mutex

## Architecture: Inline Event Translation

```
Terminal input thread → KeyDown(key_code) → event queue
                                                ↓
renders event loop receives raw event → calls listens(key_code, &state)
                                                ↓
                                        returns TodoEvent variant
                                                ↓
renders dispatches TodoEvent via match body
```

The `listens` verb in terminal context is emitted as a **synchronous C function** (not a coroutine). It takes the raw event payload and a mutable state pointer, matches on key codes via LookupPattern, and returns a translated event variant.

## Implementation Steps

1. **Thread-safe event queue** — add `pthread_mutex_t` to `prove_event.h/c`
2. **Fix recv for NULL coro** — busy-wait with `usleep` when no coroutine
3. **LookupPattern emission** — `_emit_stmts.py`: `Key:Escape` → `case 27:`, `Key:"k"` → `case 'k':`
4. **Rewrite listens emission** — `c_emitter.py`: regular C function, not coroutine
5. **Wire listens into renders** — `c_emitter.py`: dispatch raw events to listeners before match
6. **Forward declarations** — emit listens function signature before renders

## Key Mapping

The UI module's `Key` lookup table maps variant names to integer codes matching `prove_terminal_read_key()` output:

| Pattern | Emitted C | Source |
|---------|-----------|--------|
| `Key:Escape` | `case 27:` | Key lookup table integer column |
| `Key:"k"` | `case (int64_t)'k':` | ASCII value of string literal |
| `Key:Space` | `case 32:` | Key lookup table integer column |
| `Key:ArrowUp` | `case 1001:` | Key lookup table integer column |

## Verification

```bash
# Build
python -m prove build examples/terminal_todo/

# Run — should show todo list, respond to j/k/space/a/d/ESC
./examples/terminal_todo/dist/terminal_todo

# Tests
python -m pytest tests/ -q --ignore=tests/test_testing.py
```

## Dependencies (all DONE)

- Inherited algebraic types
- LookupPattern parser/checker
- Terminal overload dispatch
- State variable in renders
- List set/remove operations
- Self-dispatch events in renders
