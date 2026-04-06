---
title: UI, Terminal & Graphic - Prove Standard Library
description: UI base types, Terminal TUI primitives, and Graphic GUI widgets for building interactive applications in Prove.
keywords: Prove UI, Terminal, Graphic, TUI, GUI, ANSI, SDL2, Nuklear, renders verb, listens verb, AppEvent, Key, Color
---

# UI, Terminal & Graphic

## UI

The `UI` module provides base types shared by all UI backends (Terminal and Graphic).

Two backends extend `AppEvent`:

- **Terminal** — TUI via ANSI escape codes. Zero external dependencies.
- **Graphic** — GUI via SDL2 + Nuklear. **Requires [SDL2](#graphic)**. Resolved automatically via `pkg-config`.

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

#### `TextStyle:[Lookup]`

Bidirectional text style mapping. Resolve by variant (`TextStyle:Bold`), by name (`TextStyle:"bold"`), or by ANSI SGR code (`TextStyle:1`).

Variants: `Reset`, `Bold`, `Dim`, `Italic`, `Underline`, `Inverse`, `Strikethrough`.

#### `Position`

Screen position struct with `x` (column) and `y` (row) fields.

---

## The `renders` and `listens` Verbs

`renders` and `listens` are language-level async verbs for building event-driven UI applications.

### `renders` — event loop with state

Owns the event loop, manages mutable state, dispatches events to match arms.

```prove
renders app(listeners List<Listens>)
  event_type MyEvent
  state_init MyState(initial_value)
from
    Draw(state) => // render UI
    Exit(state) => Unit
```

**Annotations:**

- `event_type` — algebraic event type (must extend `TerminalAppEvent` or `GraphicAppEvent`)
- `state_init` — initial state value (type inferred)

**Rules:**

- First parameter must be `List<Listens>` (registered event translators)
- Body must be a single match expression with an `Exit` arm
- No return type — `renders` always returns `Unit`
- Backend auto-detected: `TerminalAppEvent` chain = TUI, `GraphicAppEvent` chain = GUI

**Self-dispatch:** Calling a variant name inside a match arm (e.g. `Draw(state)`) re-enqueues that event. This is how state mutations trigger redraws.

### `listens` — event translator

Translates raw platform events (e.g. `KeyDown`) into app-specific events. Called inline by `renders` when a matching raw event arrives.

```prove
listens on_key(attached_verbs List<Attached>) MyEvent
  event_type KeyDown
  state_type MyState
from
    Key:Escape => Exit(state)
    Key:"k" => Draw(state)
    _ => Tick(state)
```

**Annotations:**

- `event_type` — which raw event type this listener handles (e.g. `KeyDown`)
- `state_type` — type of the renders state (gives read/write access to `state`)

**Rules:**

- Return type is the app event type (what gets dispatched in `renders`)
- Match arms use `LookupPattern` for key matching: `Key:Escape`, `Key:"k"`, `Key:Space`
- State mutations in `listens` are propagated back to `renders`

---

## Terminal

TUI primitives via ANSI escape codes. Zero external dependencies.

### Types

#### `TerminalAppEvent`

Extends `AppEvent` for the terminal backend. Use as the base type for your app's event type:

```prove
type MyAppEvent is TerminalAppEvent
  | CustomEvent
```

### Functions

| Verb | Name | Signature | Description |
|------|------|-----------|-------------|
| `validates` | `terminal` | `()` | Check if stdout is an interactive terminal |
| `outputs` | `raw` | `()` | Enable raw mode (disable echo, line buffering) |
| `outputs` | `cooked` | `()` | Restore normal terminal mode |
| `outputs` | `terminal` | `(text String)` | Write text at current cursor position |
| `outputs` | `terminal` | `(x Integer, y Integer, text String)` | Write text at screen position |
| `outputs` | `clear` | `()` | Clear screen and reset cursor to (0,0) |
| `outputs` | `cursor` | `(x Integer, y Integer)` | Move cursor to position |
| `derives` | `size` | `() Position` | Get terminal dimensions (cols, rows) |
| `derives` | `ansi` | `(name String) String` | Convert a Color or TextStyle name to ANSI escape sequence |

### Example: Terminal Todo List

A full interactive TUI application with keyboard navigation, state management, and event translation.

```prove
module TodoApp
  Terminal types TerminalAppEvent outputs terminal clear raw cooked
  Math derives max min
  UI types Key
  Sequence derives set remove

  type TodoItem is
    text String
    done Boolean
    pos Integer

  type TodoState is
    items List<TodoItem>
    selected Integer

  type TodoEvent is TerminalAppEvent
    | ToggleDone
    | AddItem
    | RemoveItem

transforms checkboxes(item TodoItem, state TodoState) String
  trusted: "For now"
from
    prefix as String = match item.pos == state.selected
        true => "> "
        false => "  "
    check as String = match item.done
        true => "[x]"
        false => "[ ]"
    f"{prefix}{check} {item.text}"

renders interface(registered_listens_verbs List<Listens>)
  event_type TodoEvent
  state_init TodoState([TodoItem("Learn Prove", false, 0),
          TodoItem("Build a TUI app", false, 1),
          TodoItem("Ship it", false, 2)], 0)
from
    Draw(state) =>
        clear()
        terminal(0, 0, "=== Todo List ===")
        terminal(0, 1, "j/k: navigate | space: toggle | d: delete | ESC: quit")
        terminal(0, 2, "")
        each(state.items, |item| terminal(0, item.pos + 3, checkboxes(item, state)))
    Tick(state) => Draw(state)
    ToggleDone =>
        item as TodoItem = state.items[state.selected]
        state.items = set(state.items, state.selected,
            TodoItem(item.text, !item.done, item.pos))
        Draw(state)
    RemoveItem =>
        state.items = remove(state.items, state.selected)
        state.selected = max(0, state.selected - 1)
        Draw(state)
    Exit(state) =>
        cooked()
        Unit
    _ => Unit

listens on_key(attached_verbs List<Attached>) TodoEvent
  event_type KeyDown
  state_type TodoState
from
    Key:Escape => Exit(state)
    Key:"k" =>
        state.selected = max(0, state.selected - 1)
        Draw(state)
    Key:"j" =>
        state.selected = min(state.items.length - 1, state.selected + 1)
        Draw(state)
    Key:Space => ToggleDone()
    Key:"d" => RemoveItem()
    _ => Tick(state)

main()
from
    raw()
    interface([on_key])&
```

```bash
proof build examples/terminal_todo/
./examples/terminal_todo/dist/terminal_todo
```

---

## Graphic

GUI primitives via SDL2 + Nuklear immediate-mode rendering. Continuous vsync-paced rendering at ~60fps.

**Prerequisites:** SDL2 must be installed. The compiler resolves paths via `pkg-config`.

```bash
# macOS
brew install sdl2

# Linux (Debian/Ubuntu)
apt install libsdl2-dev
```

### Types

#### `GraphicAppEvent`

Extends `AppEvent` with GUI-specific platform events:

```prove
type GraphicAppEvent is AppEvent
  Visible(state Value)
  | Hidden(state Value)
  | Focused(state Value)
```

### Functions

| Verb | Name | Signature | Description |
|------|------|-----------|-------------|
| `outputs` | `window` | `(title String, width Integer, height Integer)` | Create/begin a named window. Call once per frame before widgets |
| `outputs` | `button` | `(label String) Boolean` | Clickable button. Returns true on click frame |
| `outputs` | `label` | `(text String)` | Static text label |
| `outputs` | `text_input` | `(label String, value String) String` | Editable text field. Returns current contents |
| `outputs` | `checkbox` | `(label String, checked Boolean) Boolean` | Checkbox. Returns current state |
| `outputs` | `slider` | `(label String, min Float, max Float, value Float) Float` | Horizontal slider. Returns current value |
| `outputs` | `progress` | `(current Integer, max Integer)` | Progress bar |
| `outputs` | `quit` | `()` | Close window and exit render loop |

### Example: GUI Counter

A minimal GUI application with a button that increments a counter.

```prove
module Counter
  Graphic types GraphicAppEvent outputs window button label
  Types creates string

  type CounterState is
    count Integer

  type CounterApp is GraphicAppEvent

renders app(registered_attached_verbs List<Listens>)
  event_type CounterApp
  state_init CounterState(0)
from
    Draw(state) =>
        window("Counter", 400, 300)
        label(f"Count: {string(state.count)}")
        match button("Increment")
            true =>
                state.count += 1
                Draw(state)
            false => Draw(state)
    Tick(state) => Draw(state)
    Exit(state) => Unit

main()
from
    app([])&
```

```bash
proof build examples/gui_counter/
./examples/gui_counter/dist/gui_counter
```
