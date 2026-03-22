# Graphic Stdlib Module

Add a `Graphic` stdlib module providing native graphical user interfaces via [Nuklear](https://github.com/Immediate-Mode-UI/Nuklear) — a single-header, immediate-mode C GUI library with zero external dependencies.

Graphic extends the `UI` base module (implemented in `proof/src/stdlib/ui.prv`) which provides shared types. The `renders` verb is a language-level verb (like `listens`/`streams`), not defined in any stdlib.

## Motivation

Prove targets native binaries. A Graphic module lets users build desktop applications (forms, tools, dashboards) without leaving the language. Immediate-mode rendering maps naturally to Prove's `renders` verb — each frame is a pure function of state, no mutable widget trees.

## Design

### Three-module UI architecture

UI capabilities are split across three stdlib modules:

1. **`UI`** (base) — `AppEvent` base event type (not directly usable as algebraic), `Key:[Lookup]`, `Color:[Lookup]`, `Position`, and shared events (`Draw`, `Tick`, `KeyDown`, `KeyUp`, `MouseDown`, `MouseUp`, `Scroll`, `MousePos`, `Resize`, `Exit`)
2. **`Terminal`** (implemented in `proof/src/stdlib/terminal.prv`) — extends `AppEvent` with `TerminalAppEvent`, adds TUI-specific primitives
3. **`Graphic`** — extends `AppEvent` with `GraphicAppEvent`, adds GUI-specific primitives and events (`Visible`, `Hidden`, `Focused`)

### Backend selection via type hierarchy

No `UiLib` type needed. The `event_type` annotation tells the compiler which backend to use:

```
AppEvent (UI base — abstract, not directly usable)
├── TerminalAppEvent (Terminal — TUI backend)
│   └── type MyApp is TerminalAppEvent   (user code)
└── GraphicAppEvent (Graphic — GUI backend)
    └── type MyApp is GraphicAppEvent    (user code)
```

### Why Nuklear

- **Single header** — vendor `nuklear.h` directly into the runtime, no system deps
- **Pure C** — fits Prove's C runtime model perfectly
- **Immediate-mode** — each frame redraws from state, matching Prove's functional semantics
- **Backend-agnostic** — rendering via pluggable backends (SDL2/OpenGL, X11, GDI, Cocoa)
- **Battle-tested** — widely used, stable API, good documentation
- **Small API surface** — windows, layouts, buttons, labels, sliders, text input, trees, menus

### Why immediate-mode over retained-mode

Retained-mode (GTK, Qt) requires mutable widget state, callbacks, and event wiring — all at odds with Prove's declarative, verb-driven design. Immediate-mode lets the `renders` verb simply describe what the UI looks like right now, and the framework handles the rest.

### Backend strategy

The C runtime wraps Nuklear with a platform backend. Phase 1 uses **SDL2 + OpenGL** as the rendering backend because:

- SDL2 is available on all major platforms (Linux, macOS, Windows)
- SDL2 handles window creation, input events, and OpenGL context
- Nuklear ships example backends for SDL2+OpenGL
- SDL2 is a single runtime dependency (widely pre-installed or easily bundled)

Future phases can add native backends (Cocoa, Win32, X11) for zero-dependency builds on specific platforms.

### Module name: `Graphic`

Clear, distinguishes from Terminal. Follows Prove's naming convention (System, Network, Terminal).

## Stdlib Declaration (`graphic.prv`)

```prove
module Graphic
  narrative: """GUI primitives via Nuklear immediate-mode library. Extends UI base module.
    Import GraphicAppEvent and extend it for your app's event type.
    Frame pacing is vsync-driven: continuous rendering at ~60fps."""

  /// GUI event type — extends AppEvent with window-level platform events.
  /// Selecting this as your base type tells the compiler to use
  /// the graphical backend with vsync-paced continuous rendering (~60fps).
  type GraphicAppEvent is AppEvent
    /// Window became visible to the user (un-minimized, brought to front).
    /// Use to resume animations or refresh stale data.
    Visible(state Value)
    /// Window is hidden or minimized by the user or OS.
    /// Use to pause expensive rendering or background work.
    | Hidden(state Value)
    /// Window gained input focus — user is actively interacting.
    /// Use to enable keyboard shortcuts or highlight active elements.
    | Focused(state Value)

  /// Create or begin a named window with the given dimensions in pixels.
  /// Must be called once per frame in the Draw arm before any widget calls.
  /// Subsequent widget calls render inside this window.
  outputs window(title String, width Integer, height Integer)

  /// Render a clickable button with a text label.
  /// Returns true on the frame the button is clicked, false otherwise.
  /// Use in a match to branch on click.
  outputs button(label String) Boolean

  /// Render a static text label. Non-interactive, used for headings,
  /// descriptions, and status messages.
  outputs label(text String)

  /// Render an editable text field with a label and current value.
  /// Returns the current string contents (updated as user types).
  /// Pass the returned value back on the next frame to preserve input.
  outputs text_input(label String, value String) String

  /// Render a checkbox with a label and current checked state.
  /// Returns the current boolean state (toggled when user clicks).
  /// Pass the returned value back on the next frame to preserve state.
  outputs checkbox(label String, checked Boolean) Boolean

  /// Render a horizontal slider with a label, min/max range, and current value.
  /// Returns the current float value (updated as user drags).
  /// Pass the returned value back on the next frame to preserve position.
  outputs slider(label String, min Float, max Float, value Float) Float

  /// Render a progress bar showing current out of max.
  /// Non-interactive — use to display loading, upload, or task progress.
  outputs progress(current Integer, max Integer)

  /// Programmatically close the window and exit the render loop.
  /// Triggers the Exit event. Use for menu-driven quit or error shutdown.
  outputs quit()
```

**LSP autocomplete note:** All struct fields, algebraic variants, and function signatures have `///` docstrings. The LSP must index these so that:
- Typing `GraphicAppEvent.` suggests `Visible`, `Hidden`, `Focused` with descriptions
- Widget functions show parameter-level hints (e.g. `slider` shows min/max/value roles)
- Inherited `AppEvent` variants (`Draw`, `Tick`, `KeyDown`, etc.) appear alongside `GraphicAppEvent`-specific ones

See `proof/src/stdlib/ui.prv` for the full UI base module declaration with `Key`, `Color`, `AppEvent`, and `Position`.

## Usage Examples

### Counter

```prove
module Counter
  Graphic outputs window button label types GraphicAppEvent

  type CounterState is
    count Integer

  type CounterApp is GraphicAppEvent

  renders app(registered_attached_verbs List<Attached>)!&
    event_type CounterApp
    state_init CounterState(0)
  from
      Draw(state) =>
          window("Counter", 400, 300)
          label(f"Count: {state.count}")
          match button("Increment")
              when true -> Draw(state.count + 1)
              when false -> Draw(state)
      Tick(state) => Draw(state)
      Exit(state) => Unit

  main()
  from
      app([])!&
```

### Form with keyboard handling and custom events

```prove
module SignUp
  Graphic outputs window button label text_input checkbox types GraphicAppEvent

  type FormState is
    name String
    email String
    agreed Boolean
    submitted Boolean

  type FormApp is GraphicAppEvent
    Submit(state FormState)

  renders form(registered_attached_verbs List<Attached>)!&
    event_type FormApp
    state_init FormState("", "", false, false)
  from
      Draw(state) =>
          window("Sign Up", 350, 250)
          name = text_input("Name", state.name)
          email = text_input("Email", state.email)
          agreed = checkbox("I agree to the terms", state.agreed)
          match button("Submit")
              when true ->
                  state.agreed = agreed
                  state.submitted = true
                  Submit(state)
              when false ->
                  state.name = name
                  state.email = email
                  state.agreed = agreed
                  Draw(state)
      Submit(state) =>
          window("Sign Up", 350, 250)
          label(f"Welcome, {state.name}!")
      Tick(state) => Draw(state)
      Visible(state) => Draw(state)
      Hidden(state) => Draw(state)
      Exit(state) => Unit

  attached on_key() FormApp
    event_type KeyDown
    state_type FormState
  from
      match event
          Key:Escape => Exit
          Key:Enter => Submit(state)
          _ => Tick(state)

  main()
  from
      form([on_key])!&
```

## Example: GUI Todo App

A complete example to move to `examples/gui_todo/` when implemented.

```prove
module TodoApp
  narrative: """GUI todo list with add, toggle, and delete."""
  Graphic outputs window button label text_input checkbox types GraphicAppEvent

  type TodoItem is
    text String
    done Boolean

  type TodoState is
    items List<TodoItem>
    new_text String

  type TodoApp is GraphicAppEvent
    AddItem
    | RemoveItem(index Integer)

  renders interface(registered_attached_verbs List<Attached>)!&
    event_type TodoApp
    state_init TodoState([], "")
  from
      Draw(state) =>
          window("Todo List", 400, 500)
          new_text = text_input("New item", state.new_text)
          match button("Add")
              when true -> AddItem
              when false ->
                  each item, index in state.items
                      done = checkbox(item.text, item.done)
                      state.items = state.items.set(index, TodoItem(item.text, done))
                      match button(f"Delete##{index}")
                          when true -> RemoveItem(index)
                          when false -> Unit
                  state.new_text = new_text
                  Draw(state)
      AddItem =>
          match state.new_text.length > 0
              true =>
                  state.items = state.items.append(TodoItem(state.new_text, false))
                  state.new_text = ""
                  Draw(state)
              false => Draw(state)
      RemoveItem(index) =>
          state.items = state.items.remove(index)
          Draw(state)
      Tick(state) => Draw(state)
      Exit(state) => Unit

  attached on_key() TodoApp
    event_type KeyDown
    state_type TodoState
  from
      match event
          Key:Escape => Exit
          Key:Enter => AddItem
          _ => Tick(state)

  main()
  from
      interface([on_key])!&
```

## Phases

### Phase 1: Core Widgets (foundation)

Everything in `graphic.prv` above, plus:

**C runtime** (`prove_gui.c/.h`):
- Vendor `nuklear.h` (single header, ~18k LOC, MIT license)
- SDL2 + OpenGL backend init/teardown
- Window creation with title, size
- Main loop integration: poll SDL events → feed to Nuklear → render
- Widget wrappers: button, label, text input, checkbox, slider, progress
- `atexit` handler to clean up SDL/OpenGL context
- Thread-safe event queue for Prove's event system
- Frame pacing via vsync (runtime-managed, user code doesn't control refresh rate)

**Build integration:**
- `prove build` links `-lSDL2 -lGL` (Linux), `-lSDL2 -framework OpenGL` (macOS), `-lSDL2 -lopengl32` (Windows)
- SDL2 detected via `sdl2-config` or `pkg-config`
- Clear error message if SDL2 not found: "Graphic module requires SDL2. Install with: apt install libsdl2-dev / brew install sdl2"

### Phase 2: Layout & Styling

Layout primitives for composing widgets:

| Verb | Function | Signature | Description |
|------|----------|-----------|-------------|
| outputs | row | `(height Float, columns Integer)` | Begin a row layout |
| outputs | row_dynamic | `(height Float, columns Integer)` | Dynamic-width row |
| outputs | row_static | `(height Float, width Integer, columns Integer)` | Fixed-width row |
| outputs | group | `(title String)` | Scrollable group/panel |
| outputs | tree | `(title String) Boolean` | Collapsible tree node |
| outputs | spacing | `(columns Integer)` | Empty spacing |
| outputs | style_color | `(widget String, color Color)` | Set widget color |
| outputs | style_font_size | `(size Float)` | Set font size |

### Phase 3: Advanced Widgets

Richer widgets for real applications:

- `outputs image(path String)` — display image from file
- `outputs combo(label String, items List<String>, selected Integer) Integer` — dropdown
- `outputs menu(label String) Boolean` — menu bar items
- `outputs popup(title String) Boolean` — modal popup
- `outputs chart(values List<Float>, width Integer, height Integer)` — simple line/bar chart
- `outputs color_picker(color Color) Color` — color selection
- `outputs table(headers List<String>, rows List<List<String>>)` — data table

### Phase 4: Multi-window & Native Backends (optional)

- Multiple windows via separate SDL contexts
- Native backends: Cocoa (macOS), Win32 (Windows), X11/Wayland (Linux) for zero-SDL builds
- File dialogs via native OS APIs (`NSOpenPanel`, `GetOpenFileName`, `zenity`)

## Implementation Checklist

### Compiler & stdlib
1. ~~Ensure `UI` base module exists~~ ✅ Done (implemented with Terminal)
2. Vendor `nuklear.h` into `prove-py/src/prove/runtime/vendor/`
3. Create `prove_gui.c` and `prove_gui.h` in `prove-py/src/prove/runtime/`
4. Create `graphic.prv` in `prove-py/src/prove/stdlib/`
5. Register the module in `stdlib_loader.py` with `c_map` entries
6. Add `"graphic": {"prove_gui"}` to `STDLIB_RUNTIME_LIBS` in `c_runtime.py`
7. Add `prove_gui` entries to `_RUNTIME_FUNCTIONS` in `c_runtime.py`
8. Update `builder.py` to link SDL2/OpenGL when Graphic module is imported

### Lexer grammars
9. Ensure `renders` verb and annotations (`event_type`, `state_type`, `state_init`) are in all three lexer grammars (done in Terminal/future-11 implementation):
   - `tree-sitter-prove/` — Tree-sitter grammar
   - `pygments-prove/` — Pygments lexer
   - `chroma-lexer-prove/` — Chroma lexer

### Documentation
10. Update `docs/` — MkDocs site must document the `Graphic` module, `GraphicAppEvent`, all widget functions. Run `mkdocs build --strict` to verify.
11. Update `CLAUDE.md` — add Graphic to stdlib module list, document SDL2 dependency.

### Tests & examples
12. Write tests: checker tests for `.prv` signatures, C runtime tests for GUI functions
13. Create example projects (`examples/gui_counter/`, `examples/gui_todo/`)
14. E2e test coverage (headless via SDL2's `SDL_VIDEODRIVER=dummy`)

## Key Architectural Notes

- **`renders` is a language verb** — like `listens`/`streams`, implemented in the compiler. Not a stdlib function.
- **Events and state are separate** — `event_type` is the algebraic event type, `state_init` on `renders` creates the state singleton (type inferred), `state_type` on `attached` declares which state to access. `state` is implicitly available where declared.
- **Backend selection via type hierarchy** — the `event_type` resolves the backend: `TerminalAppEvent` → TUI, `GraphicAppEvent` → GUI. The compiler walks the type chain.
- **Contracts enforce correctness** — `event_type` must extend a concrete backend type (not bare `AppEvent`). `attached` `state_type` must match the type inferred from `renders` `state_init`. All compile-time, no runtime checks.
- **`Draw` vs `Tick`** — `Tick(state)` is the runtime heartbeat fired at vsync rate (~60fps). `Draw(state)` is the render event. Default: `Tick` triggers `Draw`. User code puts rendering logic in the `Draw` arm.
- **Widget functions use `outputs` verb** — `renders` is reserved for the main loop. Widget calls (`window`, `button`, `label`, etc.) use `outputs` since they produce side effects (drawing to screen).
- **Immediate-mode maps to `renders`** — each `Draw` arm describes the current frame. Nuklear handles the diff between frames internally.
- **State is the user's responsibility.** The Graphic module doesn't own state. State is created once via `state_init` on `renders` and mutated in place.
- **SDL2 is the only external dependency.** Nuklear itself is vendored. This is an acceptable trade-off for cross-platform window/input/GL support.
- **Headless testing via SDL dummy driver.** `SDL_VIDEODRIVER=dummy` allows CI to run Graphic tests without a display server.
- **`atexit` handler for cleanup.** The Graphic module must register an `atexit` handler to tear down SDL/OpenGL cleanly if the program exits unexpectedly.
- **Nuklear license compatibility.** Nuklear is MIT/Public Domain — compatible with both Prove Source License (language files) and Apache-2.0 (tooling).
