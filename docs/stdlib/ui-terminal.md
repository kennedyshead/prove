---
title: UI & Terminal - Prove Standard Library
description: UI base types and Terminal TUI primitives for building interactive terminal applications in Prove.
keywords: Prove UI, Terminal, TUI, ANSI, renders verb, AppEvent, Key, Color
---

# UI & Terminal

## UI

The `UI` module provides base types shared by all UI backends (Terminal and future Graphic).

### Types

#### `AppEvent`

Algebraic event type driving the `renders` loop. Abstract — extend via `TerminalAppEvent` or `GraphicAppEvent`.

```prove
type AppEvent is
  Draw(state Value)
  | Tick(state Value)
  | KeyDown(key Key)
  | KeyUp(key Key)
  | MouseDown(button Integer, x Integer, y Integer)
  | MouseUp(button Integer, x Integer, y Integer)
  | Scroll(dx Integer, dy Integer)
  | MousePos(x Integer, y Integer)
  | Resize(width Integer, height Integer)
  | Exit(state Value)
```

#### `Key:[Lookup]`

Bidirectional keyboard mapping. Resolve by variant (`Key:Escape`), by name (`Key:"escape"`), or by keycode (`Key:27`).

Keycodes above 1000 are virtual codes for non-printable keys; printable characters use ASCII directly.

#### `Color:[Lookup]`

Bidirectional color mapping. Resolve by variant (`Color:Red`), by name (`Color:"red"`), by ANSI SGR code (`Color:31`), or by hex (`Color:"#FF0000"`).

#### `Position`

Screen position struct with `x` (column) and `y` (row) fields.

---

## Terminal

TUI primitives via ANSI escape codes. Zero external dependencies.

### Types

#### `TerminalAppEvent`

Extends `AppEvent` for the terminal backend. Use as the base type for your app's event type:

```prove
type MyAppEvent is TerminalAppEvent
  CustomEvent(data String)
```

### Functions

| Verb | Name | Signature | Description |
|------|------|-----------|-------------|
| `validates` | `terminal` | `() Boolean` | Check if stdout is an interactive terminal |
| `outputs` | `raw` | `()` | Enable raw mode (disable echo, line buffering) |
| `outputs` | `cooked` | `()` | Restore normal terminal mode |
| `outputs` | `terminal` | `(text String)` | Write text at current cursor position |
| `outputs` | `terminal` | `(x Integer, y Integer, text String)` | Write text at screen position |
| `outputs` | `clear` | `()` | Clear screen and reset cursor to (0,0) |
| `outputs` | `cursor` | `(x Integer, y Integer)` | Move cursor to position |
| `reads` | `size` | `() Position` | Get terminal dimensions (cols, rows) |

### The `renders` Verb

`renders` is a language-level verb (like `listens`) for building event-driven UI applications.

```prove
renders interface(registered_attached_verbs List<Attached>)
  event_type MyAppEvent
  state_init MyState(0)
from
    Draw(state) =>
        clear()
        terminal(0, 0, f"Count: {state.count}")
    Exit(state) => Unit
```

**Annotations:**

- `event_type` — the algebraic event type (must extend `TerminalAppEvent`)
- `state_init` — initial state value (type inferred)
- `state_type` (on `attached`) — declares which state to access

**Implicit bindings:**

- `state` — mutable application state singleton
- `event` — the received event (in `attached` callbacks)

**Rules:**

- First parameter must be `List<Attached>`
- Body must be a single match expression with an `Exit` arm
- No return type — `renders` always returns `Unit`
- Backend resolved from `event_type` type chain

### Example

```prove
module Counter
  Terminal outputs terminal clear reads size types TerminalAppEvent

  type CounterEvent is TerminalAppEvent

  type CounterState is
    count Integer

  renders interface(registered_attached_verbs List<Attached>)
    event_type CounterEvent
    state_init CounterState(0)
  from
      Draw(state) =>
          clear()
          terminal(0, 0, f"Count: {state.count}")
          terminal(0, 1, "Press +/- or ESC to quit")
      Tick(state) => Draw(state)
      Exit(state) => Unit

  attached on_key() CounterEvent
    event_type KeyDown
    state_type CounterState
  from
      match event
          Key:Escape => Exit
          Key:43 => Draw(state.count + 1)
          Key:45 => Draw(state.count - 1)
          _ => Tick(state)

  main()
  from
      raw()
      interface([on_key])
```
