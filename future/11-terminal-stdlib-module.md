# Terminal Stdlib Module

Add a `Terminal` stdlib module providing TUI (terminal user interface) primitives via ANSI escape codes. Zero external dependencies — just `termios.h` + ANSI sequences.

Terminal extends the `UI` base module (see section below) which provides shared types. The `renders` verb is a language-level verb (like `listens`/`streams`), not defined in any stdlib.

## Motivation

Prove targets CLI tools. A Terminal module lets users build interactive terminal applications (menus, dashboards, editors) using Prove's `renders` verb for frame dispatch and `attached` callbacks for event handling.

## Design

### Three-module UI architecture

UI capabilities are split across three stdlib modules:

1. **`UI`** (base) — `AppEvent` base event type (not directly usable as algebraic), `Key:[Lookup]`, `Color:[Lookup]`, `Position`, and shared events (`Draw`, `Tick`, `KeyDown`, `KeyUp`, `MouseDown`, `MouseUp`, `Scroll`, `MousePos`, `Resize`, `Exit`)
2. **`Terminal`** — extends `AppEvent` with `TerminalAppEvent`, adds TUI-specific primitives: raw/cooked mode, cursor control, ANSI output, terminal size
3. **`Graphic`** (see `future/12-gui-stdlib-module.md`) — extends `AppEvent` with `GraphicAppEvent`, adds GUI-specific primitives and events (`Visible`, `Hidden`, `Focused`)

### `renders` verb

`renders` is a **language-level verb** (like `listens`, `streams`, `attached`) — not a stdlib function. It follows the same pattern as `listens`:

- Takes `List<Attached>` as first parameter
- `event_type` annotation declares the event variant type
- `state_init` annotation creates the state singleton (type inferred from value)
- `attached` callbacks declare their own `event_type` (which events they handle) and `state_type` (to access the parent state)
- `state` is implicitly available where `state_init` or `state_type` is declared
- `!&` — failable and async (events received asynchronously from runtime)
- Runtime manages frame pacing based on the `event_type`'s base type

### Backend selection via type hierarchy

No `UiLib` type needed. The `event_type` annotation tells the compiler which backend to use:

```
AppEvent (UI base — abstract, not directly usable)
├── TerminalAppEvent (Terminal — TUI backend)
│   └── type MyApp is TerminalAppEvent   (user code)
└── GraphicAppEvent (Graphic — GUI backend)
    └── type MyApp is GraphicAppEvent    (user code)
```

The compiler resolves the backend from the type chain. `type MyApp is TerminalAppEvent` → TUI. `type MyApp is GraphicAppEvent` → GUI.

Type checking: `AppEvent != TerminalAppEvent` (can't use base directly), but `TerminalAppEvent == AppEvent` (subtype — anywhere `AppEvent` is accepted, `TerminalAppEvent` is valid).

### Events vs State — separated

Events and state are distinct:

- **Events** (`event_type`) — algebraic variants driving the render loop: `Draw`, `Tick`, `KeyDown`, `Exit`, plus user custom events
- **State** (`state_init` on `renders`) — user's data struct, created once and mutated in place across frames
- `state_type` on `attached` — declares which state type to access (must match parent `renders`)

State only exists where declared:

- **`renders`** — `state_init` creates the state singleton and infers the type. `state` is available in the `from` body as a root-scope context variable.
- **`attached`** — `state_type` declares which state type to access. `state` is available in the `from` body. No `state_init` — the state already exists from the parent `renders`.
- **No `state_init` / `state_type`** = no `state` variable in scope.

**State singleton is mutable.** Unlike general Prove values, the `renders` state is mutable by nature — it acts as a system context that persists across frames. Field assignment (`state.count = state.count + 1`) and shorthand (`Draw(state.count + 1)`) are both valid. This mutability is **exclusive to `renders` state singletons** and does not apply to Prove values in general.

### Key and Color are Lookup types with named columns

Both `Key` and `Color` are defined as `:[Lookup]` types with **named columns** for self-documenting bidirectional mapping:

```prove
type Color:[Lookup] is name:String | ansi:Integer | hex:String where
    Red | "red" | 31 | "#FF0000"
```

- `Color:Red` gives the variant
- `Color:"red"` resolves by name column
- `Color:31` resolves by ansi column
- `Color:"#FF0000"` resolves by hex column

Each backend's C runtime maps the logical values to native encoding.

Keyboard events are handled entirely through the `renders`/`attached` event system — no `inputs keyboard` verb needed.

The `Log` module currently defines ANSI color constants (`RED`, `GREEN`, etc.) as raw escape strings — these should migrate to use UI's `Color` lookup type in a future cleanup.

### Key modifiers (Phase 2)

Phase 1 ships bare keys only. Phase 2 adds modifier support — likely via `KeyDown(key Key, modifiers Modifiers)` where `Modifiers` is a struct with `ctrl`, `alt`, `shift` Boolean fields. This enables `Ctrl+C`, `Shift+Arrow`, `Alt+F4`, etc.

### Why ANSI over ncurses

- Zero dependencies — every modern terminal emulator supports ANSI
- The C runtime file is self-contained
- ncurses would still need a C shim layer, negating the benefit

### Module name: `Terminal`

Matches the concrete capability and Prove's naming convention (System, Network, Path, Store).

## Usage Example

```prove
module MyTUIApp
  Terminal outputs terminal clear cursor raw cooked reads size types TerminalAppEvent

  type MyAppEvent is TerminalAppEvent
    CustomEvent(data String)

  type MyState is
    count Integer

  renders interface(registered_attached_verbs List<Attached>)!&
    event_type MyAppEvent
    state_init MyState(0)
  from
      Draw(state) =>
          clear()
          terminal(0, 0, f"Count: {state.count}")
          terminal(0, 1, "Press +/- or ESC to quit")
      Tick(state) => Draw(state)
      Exit(state) => Unit

  attached on_key() MyAppEvent
    event_type KeyDown
    state_type MyState
  from
      match event
          Key:Escape => Exit
          Key:43 => Draw(state.count + 1)
          Key:45 => Draw(state.count - 1)
          _ => Tick(state)

  main()
  from
      registered_attached_verbs = [on_key]
      interface(registered_attached_verbs)!&
```

## Stdlib Declarations

### UI Base Module (`ui.prv`)

```prove
module UI
  narrative: """Base UI module providing shared types for Terminal and Graphic backends.
    The renders verb is a language-level verb, not defined here.
    Extend TerminalAppEvent or GraphicAppEvent for your app's event type."""

  /// Bidirectional keyboard mapping with named columns.
  /// Resolve by variant (Key:Escape), by name (Key:"escape"),
  /// or by keycode (Key:27). Keycodes above 1000 are virtual codes
  /// for non-printable keys; printable characters use ASCII directly.
  type Key:[Lookup] is name:String | code:Integer where
      /// Escape key — commonly used to exit or cancel
      Escape | "escape" | 27
      /// Enter/Return key — confirm or submit
      Enter | "enter" | 13
      /// Tab key — cycle focus between elements
      Tab | "tab" | 9
      /// Backspace key — delete character before cursor
      Backspace | "backspace" | 8
      /// Space bar — toggle or activate
      Space | "space" | 32
      /// Arrow up — navigate up in lists or menus
      ArrowUp | "up" | 1001
      /// Arrow down — navigate down in lists or menus
      ArrowDown | "down" | 1002
      /// Arrow left — move cursor left or navigate back
      ArrowLeft | "left" | 1003
      /// Arrow right — move cursor right or navigate forward
      ArrowRight | "right" | 1004
      /// Home key — jump to beginning of line or list
      Home | "home" | 1010
      /// End key — jump to end of line or list
      End | "end" | 1011
      /// Page Up — scroll up one page
      PageUp | "pageup" | 1012
      /// Page Down — scroll down one page
      PageDown | "pagedown" | 1013
      /// Delete key — delete character after cursor
      Delete | "delete" | 1014
      /// Insert key — toggle insert/overwrite mode
      Insert | "insert" | 1015
      /// Function key F1 — typically help
      F1 | "f1" | 1101
      /// Function key F2
      F2 | "f2" | 1102
      /// Function key F3
      F3 | "f3" | 1103
      /// Function key F4
      F4 | "f4" | 1104
      /// Function key F5
      F5 | "f5" | 1105
      /// Function key F6
      F6 | "f6" | 1106
      /// Function key F7
      F7 | "f7" | 1107
      /// Function key F8
      F8 | "f8" | 1108
      /// Function key F9
      F9 | "f9" | 1109
      /// Function key F10
      F10 | "f10" | 1110
      /// Function key F11 — typically fullscreen toggle
      F11 | "f11" | 1111
      /// Function key F12
      F12 | "f12" | 1112

  /// Bidirectional color mapping with named columns.
  /// Resolve by variant (Color:Red), by name (Color:"red"),
  /// by ANSI SGR code (Color:31), or by hex (Color:"#FF0000").
  /// Each backend maps to native encoding automatically.
  type Color:[Lookup] is name:String | ansi:Integer | hex:String where
      /// Reset to terminal/system default color
      Default | "default" | 0 | "#000000"
      /// Black
      Black | "black" | 30 | "#000000"
      /// Red — errors, warnings, destructive actions
      Red | "red" | 31 | "#FF0000"
      /// Green — success, confirmation, healthy status
      Green | "green" | 32 | "#00FF00"
      /// Yellow — caution, pending, in-progress
      Yellow | "yellow" | 33 | "#FFFF00"
      /// Blue — information, links, navigation
      Blue | "blue" | 34 | "#0000FF"
      /// Magenta — special, highlighted, debug
      Magenta | "magenta" | 35 | "#FF00FF"
      /// Cyan — secondary information, timestamps
      Cyan | "cyan" | 36 | "#00FFFF"
      /// White — primary text on dark backgrounds
      White | "white" | 37 | "#FFFFFF"

  /// Base UI event type. Abstract — not directly usable as algebraic type.
  /// Extend via TerminalAppEvent or GraphicAppEvent to select a backend,
  /// then extend further with your own custom events.
  ///
  /// requires: event_type extends TerminalAppEvent or GraphicAppEvent
  type AppEvent is
    /// Render frame — user code draws the UI in this arm.
    /// state is implicitly available via state_init.
    Draw(state Value)
    /// Runtime heartbeat — fired at backend-native rate.
    /// Default handler should trigger Draw(state).
    | Tick(state Value)
    /// Key pressed — carries the Key lookup value.
    /// Handle in attached callbacks or directly in renders match.
    | KeyDown(key Key)
    /// Key released — carries the Key lookup value.
    /// Useful for detecting key-hold vs key-tap.
    | KeyUp(key Key)
    /// Mouse button pressed — carries button id and position.
    | MouseDown(button Integer, x Integer, y Integer)
    /// Mouse button released — carries button id and position.
    | MouseUp(button Integer, x Integer, y Integer)
    /// Scroll wheel — carries delta (positive = up/right, negative = down/left).
    | Scroll(dx Integer, dy Integer)
    /// Mouse moved — carries screen coordinates.
    /// Coordinates are character cells (TUI) or pixels (GUI).
    | MousePos(x Integer, y Integer)
    /// Terminal or window resized — carries new dimensions.
    /// Width and height in character cells (TUI) or pixels (GUI).
    | Resize(width Integer, height Integer)
    /// Exit requested — cleanup and terminate the render loop.
    /// Carries final state for any shutdown logic.
    | Exit(state Value)

  /// Screen position in the UI coordinate space.
  /// Character cells for TUI, pixels for GUI.
  type Position is
    /// Horizontal position (0 = left edge)
    x Integer
    /// Vertical position (0 = top edge)
    y Integer
```

**LSP autocomplete note:** All struct fields and algebraic variants have `///` docstrings. The LSP must index these so that:
- Typing `Key:` suggests all variants with their docstrings (e.g. `Escape — commonly used to exit or cancel`)
- Typing `Color:` suggests all color variants with usage hints, including named column access (`Color.hex:Red` → `"#FF0000"`)
- Matching on `AppEvent` suggests `Draw`, `Tick`, `KeyDown`, `MouseDown`, `Scroll`, etc. with descriptions
- Struct field access (e.g. `position.`) suggests `x` and `y` with docstrings

### Terminal Module (`terminal.prv`)

```prove
module Terminal
  narrative: """TUI primitives via ANSI escape codes. Extends UI base module.
    Import TerminalAppEvent and extend it for your app's event type.
    Frame pacing is event-driven: redraws only when state changes."""

  /// TUI event type — extends AppEvent for terminal backend.
  /// Selecting this as your base type tells the compiler to use
  /// the terminal backend with event-driven frame pacing
  /// (no continuous rendering — redraws only on state change).
  type TerminalAppEvent is AppEvent

  /// Check if stdout is connected to an interactive terminal.
  /// Returns false when output is piped or redirected to a file.
  /// Use to decide whether to enter raw mode or fall back to plain output.
  validates terminal() Boolean

  /// Enable raw mode: disables line buffering, echo, and signal processing.
  /// Input is delivered character-by-character via KeyDown events.
  /// Must be paired with cooked() — see atexit safety note.
  outputs raw()

  /// Restore cooked mode: re-enables line buffering, echo, and signals.
  /// Always call before exit to leave the terminal in a usable state.
  outputs cooked()

  /// Write text at the current cursor position.
  /// Does not move the cursor afterward — subsequent writes append.
  outputs terminal(text String)

  /// Write text at a specific screen position (column x, row y).
  /// Top-left corner is (0, 0). Coordinates are in character cells.
  outputs terminal(x Integer, y Integer, text String)

  /// Clear the entire screen and reset cursor to (0, 0).
  outputs clear()

  /// Move the cursor to screen position (column x, row y).
  /// Does not clear or write — just repositions for the next output.
  outputs cursor(x Integer, y Integer)

  /// Get the current terminal dimensions in character cells.
  /// Returns a Position where x = columns (width) and y = rows (height).
  /// Updates automatically on Resize events.
  reads size() Position
```

### Graphic Module (`graphic.prv`)

See `future/12-gui-stdlib-module.md` for the full declaration. Summary:

```prove
module Graphic
  narrative: """GUI primitives via Nuklear immediate-mode library. Extends UI base module."""

  /// GUI event type — extends AppEvent with window-level events
  /// vsync-paced continuous rendering (~60fps)
  type GraphicAppEvent is AppEvent
    Visible(state Value)
    | Hidden(state Value)
    | Focused(state Value)

  // ... widget functions use `outputs` verb (window, button, label, etc.)
```

### The `renders` verb (language-level)

`renders` is implemented in the compiler (lexer, parser, checker, emitter) following the `listens` pattern:

**Annotations on `renders`:**
- `event_type` — the algebraic event type (must extend `TerminalAppEvent` or `GraphicAppEvent`)
- `state_init` — initial state value; type is inferred from the value (e.g. `state_init MyState(0)` → state type is `MyState`)

**Annotations on `attached`:**
- `event_type` — which event this callback handles (e.g. `KeyDown`)
- `state_type` — the state type to access (must match the parent `renders` state; no init — state already exists)

**Implicit bindings:**
- `state` — current application state, available in both `renders` and `attached` bodies
- `event` — the received event, available in `attached` bodies

**Signature:**
- `renders` always returns `Unit` — no explicit return type in the signature
- `!` — failable, the render loop can fail (e.g. terminal init error, SDL failure)
- `&` — async, events are received asynchronously from the runtime

**Runtime behavior:**
- Compiler resolves backend from `event_type` type chain
- `Tick(state)` is the runtime heartbeat — default handler triggers `Draw(state)`
- `Draw(state)` is the render event — user code describes the frame here. Arms that don't return an event implicitly wait for the next event.
- Runtime manages frame pacing based on the resolved backend
- `state` is a singleton created once by `state_init` — mutable, fields updated in place (exclusive to renders state)
- `Exit` terminates the loop and returns `Unit`

**Contracts (compile-time enforced):**
- `requires: event_type extends TerminalAppEvent or GraphicAppEvent` — AppEvent is abstract
- `requires: attached state_type == type(renders state_init)` — attached state type must match the type inferred from renders state_init

## Terminal Module — Phases

### Phase 1: Terminal Primitives (foundation)

Everything in `terminal.prv` above, plus:

**C runtime** (`prove_terminal.c/.h`):
- `termios` raw/cooked mode toggle
- ANSI escape sequence output (cursor, clear, colors)
- Key read with escape sequence parsing (arrow keys, function keys, Ctrl combos) feeding `KeyDown`/`KeyUp` events
- `SIGWINCH` handler for `Resize` events queued to the event system
- `ioctl(TIOCGWINSZ)` for terminal size
- `atexit` handler to restore cooked mode on crash/exit
- Handle `EINTR` from `SIGWINCH` interrupting blocking `read()` — retry after queuing resize event

### Phase 2: Modifiers, Mouse, Screen Buffer & Style

**Key modifiers:**

```prove
/// Keyboard modifier state — available on KeyDown/KeyUp events
type Modifiers is
  /// Ctrl key held
  ctrl Boolean
  /// Alt/Option key held
  alt Boolean
  /// Shift key held
  shift Boolean
```

`KeyDown` and `KeyUp` gain a `modifiers Modifiers` field, enabling `Ctrl+C`, `Shift+Arrow`, `Alt+F4`, etc.

**Mouse events:** `MouseDown`, `MouseUp`, `Scroll` implemented via xterm mouse reporting (SGR 1006 mode).

**Screen buffer — double-buffered rendering:**

```prove
/// Text styling for screen buffer cells
type Style is
  /// Foreground text color
  fg Color
  /// Background color
  bg Color
  /// Bold weight
  bold Boolean
  /// Underline decoration
  underline Boolean
```

**Functions:**

- `creates screen() Screen` — allocate screen buffer
- `outputs cell(screen Screen, x Integer, y Integer, char Character, style Style)` — set cell
- `outputs render(screen Screen)` — flush buffer to terminal (diff-based for efficiency)
- `outputs fill(screen Screen, char Character)` — fill screen
- `outputs terminal(x Integer, y Integer, text String, style Style)` — styled text output

This phase also introduces a style markup approach for rich text rendering.

### Phase 3: Widgets (pure Prove)

Simple composable widgets built in `.prv` (not C):
- Text display region
- Scrollable list
- Input field with cursor
- Border/box drawing (Unicode box-drawing characters)

These would live in `stdlib/` as pure Prove code using Phase 1 + 2 primitives.

## Example: Terminal Todo App

A complete example to move to `examples/terminal_todo/` when implemented.

```prove
module TodoApp
  narrative: """Interactive terminal todo list with keyboard navigation."""
  Terminal outputs terminal clear cursor raw cooked reads size types TerminalAppEvent

  type TodoItem is
    text String
    done Boolean

  type TodoState is
    items List<TodoItem>
    selected Integer

  type TodoEvent is TerminalAppEvent
    ToggleDone
    | AddItem
    | RemoveItem

  renders interface(registered_attached_verbs List<Attached>)!&
    event_type TodoEvent
    state_init TodoState(
        [TodoItem("Learn Prove", false), TodoItem("Build a TUI app", false), TodoItem("Ship it", false)],
        0)
  from
      Draw(state) =>
          clear()
          terminal(0, 0, "=== Todo List ===")
          terminal(0, 1, "j/k: navigate | space: toggle | a: add | d: delete | ESC: quit")
          terminal(0, 2, "")
          pos as Integer = 3
          each item, index in state.items
              prefix as String = match index == state.selected
                  true => "> "
                  false => "  "
              check as String = match item.done
                  true => "[x]"
                  false => "[ ]"
              terminal(0, pos, f"{prefix}{check} {item.text}")
              pos = pos + 1
      Tick(state) => Draw(state)
      ToggleDone =>
          item as TodoItem = state.items[state.selected]
          state.items = state.items.set(state.selected, TodoItem(item.text, !item.done))
          Draw(state)
      RemoveItem =>
          state.items = state.items.remove(state.selected)
          state.selected = Math.max(0, state.selected - 1)
          Draw(state)
      Exit(state) =>
          cooked()
          Unit

  attached on_key() TodoEvent
    event_type KeyDown
    state_type TodoState
  from
      match event
          Key:Escape => Exit
          Key:"k" =>
              state.selected = Math.max(0, state.selected - 1)
              Draw(state)
          Key:"j" =>
              state.selected = Math.min(state.items.length - 1, state.selected + 1)
              Draw(state)
          Key:Space => ToggleDone
          Key:"a" => AddItem
          Key:"d" => RemoveItem
          _ => Tick(state)

  main()
  from
      raw()
      interface([on_key])!&
```

## Implementation Checklist

### Compiler & stdlib
1. Create `ui.prv` in `prove-py/src/prove/stdlib/` with `AppEvent`, `Key:[Lookup]`, `Color:[Lookup]`, `Position`
2. Implement `renders` verb in lexer, parser, checker, and emitter (follows `listens` pattern, adds `state_type`/`state_init`/`event_type` annotations)
3. Create `prove_terminal.c` and `prove_terminal.h` in `prove-py/src/prove/runtime/`
4. Create `terminal.prv` in `prove-py/src/prove/stdlib/`
5. Register both modules in `stdlib_loader.py` with c_map entries
6. Add runtime lib entries to `STDLIB_RUNTIME_LIBS` and `_RUNTIME_FUNCTIONS` in `c_runtime.py`

### Lexer grammars
7. Add `renders` verb and new keywords (`event_type`, `state_type`, `state_init`) to **all three lexer grammars**:
   - `tree-sitter-prove/` — Tree-sitter grammar (Neovim, etc.)
   - `pygments-prove/` — Pygments lexer (MkDocs, docs site)
   - `chroma-lexer-prove/` — Chroma lexer (Hugo, CLI tools)

### Documentation
8. Update `docs/` — MkDocs site must document the `renders` verb, `UI`/`Terminal`/`Graphic` modules, `AppEvent`, `Key:[Lookup]`, `Color:[Lookup]`, all new types and functions. Run `mkdocs build --strict` to verify.
9. Update `CLAUDE.md` — add `renders` to the verb lists, add UI/Terminal/Graphic to stdlib module list, update compiler architecture section if needed.

### Tests & examples
10. Write tests: checker tests for `.prv` signatures, C runtime tests for terminal functions
11. Create example project (`examples/terminal_todo/`)
12. E2e test coverage

### Cleanup
13. Plan Log module migration to use UI's Color lookup type

## Key Architectural Notes

- **`renders` is a language verb** — like `listens`/`streams`, implemented in the compiler. Not a stdlib function.
- **Events and state are separate** — `event_type` is the algebraic event type, `state_init` on `renders` creates the state singleton (type inferred), `state_type` on `attached` declares which state to access. `state` is implicitly available where declared.
- **Backend selection via type hierarchy** — the `event_type` resolves the backend: `TerminalAppEvent` → TUI, `GraphicAppEvent` → GUI. The compiler walks the type chain.
- **Contracts enforce correctness** — `event_type` must extend a concrete backend type (not bare `AppEvent`). `attached` `state_type` must match the type inferred from `renders` `state_init`. All compile-time, no runtime checks.
- **`Draw` vs `Tick`** — `Tick(state)` is the runtime heartbeat fired at backend-native rate. `Draw(state)` is the render event. Default: `Tick` triggers `Draw`. User code puts rendering logic in the `Draw` arm.
- **`TerminalAppEvent is AppEvent`** — valid marker type with no new variants. Enables type checking: `AppEvent != TerminalAppEvent` (can't use base directly), but `TerminalAppEvent == AppEvent` (subtype relationship).
- **`atexit` handler is critical** — if a program crashes in raw mode without restoring cooked mode, the user's terminal is left in a broken state. The C runtime must register an atexit handler and also handle it in the signal handler.
- **Key and Color as Lookup types with named columns** — `name:String | code:Integer` for Key, `name:String | ansi:Integer | hex:String` for Color. Bidirectional resolution by any column. Each backend maps to native encoding.
- **Key modifiers deferred to Phase 2** — Phase 1 ships bare keys. Phase 2 adds `Modifiers` struct with `ctrl`/`alt`/`shift` fields on `KeyDown`/`KeyUp`.
- **Mouse events in base AppEvent** — `MouseDown`, `MouseUp`, `Scroll`, `MousePos` are all in the base type. TUI implements via xterm mouse reporting in Phase 2. GUI implements via SDL events in Phase 1.
- **No `inputs keyboard` verb** — keyboard events are delivered through the `renders`/`attached` event system as `KeyDown(key)` / `KeyUp(key)` events. No polling needed.
- **Raw mode lifecycle** — explicit `raw()` / `cooked()` verbs, not implicit. The user controls when raw mode is entered/exited.
- **Color type ownership** — UI base module owns the `Color:[Lookup]` type. Log's existing ANSI constants should eventually be replaced with UI Color references.
- **`main()` has no return type** — `main()` never returns. Errors from `!` are printed automatically; `main` is always the entry point with no result handler above it.
- **State singleton mutability** — `renders` state is the only mutable singleton in Prove. Field assignment and Draw shorthand both work. This is exclusive to `renders` — general Prove values remain immutable.
