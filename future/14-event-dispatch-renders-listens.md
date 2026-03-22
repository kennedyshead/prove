# Event Dispatch: renders/listens Pipeline

## Status: In Progress

## Problem

The terminal_todo example compiles and starts but freezes — no output, no key handling, Ctrl+C doesn't work. The event dispatch pipeline between `renders`, `listens`, and the terminal backend is not wired up.

## Current State (what works)

- **Checker**: Fully supports `renders`/`listens` verbs, inherited algebraic types, `LookupPattern` (`Key:Escape`), `Listens` type, `trusted:` annotation
- **Tree-sitter**: Grammar and highlights updated for all new syntax
- **C emitter**: Builds successfully — struct-in-list heap allocation, terminal overload dispatch, state variable initialization, inherited variant structs/constructors
- **Terminal backend**: `prove_terminal_init(_eq)` spawns an input thread (POSIX) that reads keys and sends `KeyDown` events to the queue
- **Renders loop**: Receives events from queue, dispatches via switch on event tags, sends initial Draw event

## What's Missing

The `listens` function is supposed to sit between the terminal backend and the renders loop, translating raw `KeyDown` events into app-specific `TodoEvent` variants. Currently:

1. The renders loop directly receives raw terminal events (KeyDown tag=2) but only handles TodoEvent-specific tags (Draw, ToggleDone, etc.)
2. The listens coroutine body is emitted as an empty loop over `attached_verbs` (which is empty)
3. KeyDown events from the terminal input thread go into `_eq` but nobody translates them

## Intended Event Flow

```
Terminal Input Thread (pthread)
    ↓ prove_terminal_read_key() blocks
    ↓ prove_event_queue_send(_eq, TAG_KEYDOWN, key_payload)
    ↓
Renders Event Loop (while(1))
    ↓ prove_event_queue_recv(_eq, NULL)
    ↓
    ├── TAG_DRAW → render state to terminal
    ├── TAG_TICK → re-render (same as Draw)
    ├── TAG_TOGGLEDONE → mutate state, send Draw
    ├── TAG_REMOVEITEM → mutate state, send Draw
    ├── TAG_EXIT → cleanup, break loop
    └── TAG_KEYDOWN → dispatch to listens worker
            ↓
        Listens on_key (coroutine or inline)
            ↓ match key value
            ├── Key:Escape → send Exit event
            ├── Key:"k" → mutate state.selected, send Draw
            ├── Key:"j" → mutate state.selected, send Draw
            ├── Key:Space → send ToggleDone
            ├── Key:"a" → send AddItem
            ├── Key:"d" → send RemoveItem
            └── _ → send Tick (re-render)
```

## Implementation Plan

### Coroutine-based listens

Keep listens as a coroutine that receives events from a sub-queue and yields translated events back. More complex but matches the language model.

## Files to Modify

| File | Change |
|------|--------|
| `prove-py/src/prove/c_emitter.py` | `_emit_renders_function`: add KeyDown dispatch arm that inlines listens body |
| `prove-py/src/prove/_emit_stmts.py` | Handle `LookupPattern` in match emission — emit key comparisons |
| `prove-py/src/prove/_emit_exprs.py` | Remove `_emit_listens_call` worker coro creation for listens verbs in renders context |
| `prove-py/src/prove/runtime/prove_terminal.c` | Verify key code mapping matches Key enum |
| `prove-py/src/prove/runtime/prove_event.h` | May need payload type for KeyDown events |

## Key Mapping Issue

The UI module's `Key` lookup type defines:
```
Escape | 27 | "escape"
Enter | 13 | "enter"
Space | 32 | "space"
ArrowUp | 1001 | "up"
...
```

The integer column values match what `prove_terminal_read_key()` returns (27 for Escape, etc.). So the comparison should be against the lookup table's integer values, not the enum index.

For `Key:Escape =>`: emit `_key == 27` (the integer value from Key lookup table)
For `Key:"k" =>`: emit `_key == (int64_t)'k'` (ASCII 107)
For `Key:Space =>`: emit `_key == 32`

The emitter needs access to the Key lookup table at emit time to resolve variant names to integer values.

## Verification

```bash
# Build
python -m prove build examples/terminal_todo/

# Run — should show todo list, respond to j/k/space/a/d/ESC
./examples/terminal_todo/dist/terminal_todo

# Tests
python -m pytest tests/ -q --ignore=tests/test_testing.py
```

## Dependencies

- Inherited algebraic types: DONE
- LookupPattern parser/checker: DONE
- Terminal overload dispatch: DONE
- State variable in renders: DONE
- List set/remove operations: DONE
- Self-dispatch events in renders: DONE
