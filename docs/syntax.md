---
title: Syntax Reference - Prove Programming Language
description: Core syntax reference for the Prove programming language including naming conventions, modules, types, and variable declarations.
keywords: Prove syntax, programming language syntax, Prove language reference
---

# Syntax Reference

## Naming

- **Types, modules, and classes**: CamelCase — `Shape`, `Port`, `UserAuth`, `NonEmpty`, `HttpServer`
- **Variables and parameters**: snake_case — `port`, `user_list`, `max_retries`, `db_connection`
- **Functions**: snake_case — `area`, `binary_search`, `get_users`
- **Constants**: UPPER_SNAKE_CASE — `MAX_CONNECTIONS`, `LOOKUP_TABLE`, `DEFAULT_PORT`
- **Effects**: CamelCase — `IO`, `Fail`, `Async` *(upcoming: effect type annotations and propagation checking)*

The compiler **enforces** casing. Wrong case is a compile error, not a warning. UPPER_SNAKE_CASE indicates a compile-time constant — no `const` keyword needed.

## Modules and Imports

Each file is a module. The filename (without extension) is the module name in CamelCase. The `module` block is mandatory and contains all declarations/metadata: narrative, imports, types, constants, and invariant networks. Functions remain top-level:

```prove
module InventoryService
  narrative: """Products are added to inventory..."""
  String contains length
  Auth validates login, transforms login
  Http inputs request session

  type Product is
    sku Sku
    name String

  MAX_CONNECTIONS as Integer = 1024

  invariant_network Accounting
    total >= 0
```

A verb applies to all space-separated names that follow it. Commas separate verb groups. Multiple verbs for the same function name import each variant. The verb is part of the function's identity — see [Functions & Verbs](functions.md#verb-dispatched-identity) for details.

## Foreign Blocks (C FFI)

Modules can declare `foreign` blocks to bind C functions. Each block names a C library and lists the functions it provides with their parameter types and return types:

```prove
module PyEmbed
  narrative: """Embed a Python interpreter for scripting support."""

  foreign "libpython3"
    py_initialize() Unit
    py_finalize() Unit
    py_run_string(code String) Integer
```

Foreign block names must be snake_case — Prove's naming rules apply even to C bindings. Libraries whose C API uses other conventions (like `libpython3`'s `Py_Initialize`) need thin C wrapper functions that follow snake_case naming before they can be declared in a `foreign` block.

Foreign functions are raw C bindings — wrap them in a Prove function with a verb to provide type safety and contracts:

```prove
outputs run(code String)!
from
    py_initialize()
    result as Integer = py_run_string(code)
    py_finalize()
    match result
        0 => Unit
        _ => console("script exited with non-zero status")
```

The string after `foreign` is the library name passed to the linker (`"libm"` links `-lm`). Known libraries get automatic `#include` headers:

| Library | Header | Link flags |
|---------|--------|------------|
| `libm` | `math.h` | `-lm` |
| `libpthread` | `pthread.h` | `-lpthread` |
| `libdl` | `dlfcn.h` | `-ldl` |
| `librt` | `time.h` | `-lrt` |
| `libpython3` | `Python.h` | env / `pkg-config python3-embed` |
| `libjvm` | `jni.h` | env / `pkg-config jni` |

For `libpython3` and `libjvm`, the compiler resolves include paths and linker flags in this order:

1. **Environment variables** — `PROVE_PYTHON_CFLAGS` / `PROVE_PYTHON_LDFLAGS` (or `PROVE_JVM_CFLAGS` / `PROVE_JVM_LDFLAGS`)
2. **`pkg-config`** — queries `python3-embed` or `jni`
3. **Fallback** — plain `-lpython3` or `-ljvm`

Environment variables are the recommended approach for platform-specific paths (Homebrew, Frameworks, custom installs) since they keep `prove.toml` portable:

```bash
# macOS Homebrew example
export PROVE_PYTHON_CFLAGS="-I/opt/homebrew/opt/python@3.13/Frameworks/Python.framework/Versions/3.13/include/python3.13"
export PROVE_PYTHON_LDFLAGS="-L/opt/homebrew/opt/python@3.13/Frameworks/Python.framework/Versions/3.13/lib/python3.13/config-3.13-darwin -L/opt/homebrew/lib -lpython3.13 -lintl -ldl -framework CoreFoundation"
```

The naming convention is `PROVE_<LIB>_CFLAGS` / `PROVE_<LIB>_LDFLAGS`, where `<LIB>` is the library name with the `lib` prefix and trailing version digits stripped (`libpython3` → `PYTHON`, `libjvm` → `JVM`).

For non-foreign flags (custom include paths, extra libraries), use `c_flags` and `link_flags` in [`prove.toml`](compiler.md#provetoml-configuration):

```toml
[build]
c_flags = ["-I/usr/local/include"]
link_flags = ["-L/usr/local/lib", "-lm"]
```

## Blocks and Indentation

No curly braces. Indentation defines scope (like Python). No semicolons — newlines terminate statements. Newlines are suppressed after operators, commas, opening brackets, `->`, `=>`.

## Primitive Types — Full Names, No Shorthands

Every type uses its full name. No abbreviations. Type modifiers use bracket syntax `Type:[Modifier ...]` for storage and representation concerns. Value constraints belong in [refinement types](types.md#refinement-types) (`where`), not modifiers. See [Type System — Type Modifiers](types.md#type-modifiers) for the full reference.

| Type | Modifier Axes | Default | Examples |
|------|---------------|---------|----------|
| `Integer` | size (8/16/32/64/128), signedness (Signed/Unsigned) | `Integer:[64 Signed]` | `Integer:[32 Unsigned]`, `Integer:[8]` |
| `Decimal` | precision (32/64/128), scale (Scale:N) | `Decimal:[64]` | `Decimal:[128 Scale:2]` |
| `Float` | precision (32/64) | `Float:[64]` | `Float:[32]` |
| `Boolean` | — | — | — |
| `String` | encoding (UTF8/ASCII/UTF16), max length | `String:[UTF8]` | `String:[UTF8 15]`, `String:[ASCII 255]` |
| `Byte` | — | — | Distinct type for binary data |
| `Character` | encoding (UTF8/UTF16/ASCII) | `Character:[UTF8]` | `Character:[ASCII]` |

**Modifier rules:**
- Modifiers are **order-independent** — `Integer:[Signed 64]` and `Integer:[64 Signed]` are identical. The compiler normalizes internally.
- Each modifier occupies a **distinct axis**. Two modifiers on the same axis is a compile error: `Integer:[32 64]` → ERROR: conflicting size modifiers.
- **Positional modifiers** when unambiguous by kind. **Named modifiers** (`Key:Value`) when a bare value could be confused: `Decimal:[128 Scale:2]`.
- Bare type name uses sensible defaults: `Integer` means `Integer:[64 Signed]`, `String` means `String:[UTF8]`, `Decimal` means `Decimal:[64]`.
- **`Float` is opt-in** — `Decimal` is the default for fractional numbers. `Float:[64]` uses IEEE 754 hardware floats for performance-critical domains (scientific computing, graphics, signal processing) where speed matters more than exact precision. Mixing `Float` and `Decimal` requires explicit conversion.

**Separation of concerns** — modifiers describe *storage*, refinements describe *values*:

```prove
// Modifier: how it's stored
raw_port as Integer:[16 Unsigned] = 8080

// Refinement: what values are valid
type Port is Integer where 1..65535

// Combined: storage + value constraint
type Port is Integer:[16 Unsigned] where 1..65535
```

## Type Definitions

Types live inside the `module` block, defined with `type Name is`:

```prove
module Main
  type Shape is
    Circle(radius Decimal)
    | Rect(w Decimal, h Decimal)

  type Port is Integer:[16 Unsigned] where 1 .. 65535

  type Result<Value, Error> is Ok(Value) | Err(Error)

  type User is
    id Integer
    name String
    email String
```

## Literals

Prove has several literal syntaxes for different types:

```prove
count as Integer = 42           // Integer literal
precision as Decimal = 3.14    // Decimal literal (arbitrary precision)
speed as Float = 9.8f          // Float literal (IEEE 754, requires 'f' suffix)
flag as Boolean = true
greeting as String = "Hello"
char as Character = 'x'
pattern as Regex = r"\d+"
path as Path = /users/alice/
```

The **`f` suffix** on floating-point literals (like `9.8f`) creates a `Float` type, suitable for IEEE 754 operations like `Math.sqrt` and `Math.floor`. Without the suffix (like `3.14`), you get a `Decimal` type for exact decimal arithmetic.

## Variable Declarations

Variables use `name as Type = value`. The `as` keyword reads naturally: *"port, as a Port, equals 8080"*.

```prove
port as Port = 8080
server as Server = new_server()
config as Config = load("app.yaml")!
user_list as List<User> = users()!
```

Variables are **immutable by default**. Mutability is a [type modifier](types.md#storage-modifiers) — it's a storage concern, like size and signedness:

```prove
counter as Integer:[Mutable] = 0
counter = counter + 1
```

## Type Inference with Formatter Enforcement

The compiler infers types when unambiguous, but **`prove format` always inserts explicit type annotations**. This means you can write clean code during development, and the formatter makes it explicit before commit.

```prove
// What you write:
port = 8080
server = new_server()
users = query(db, "SELECT * FROM users")!

// What `prove format` produces:
port as Integer = 8080
server as Server = new_server()
users as List<User> = query(db, "SELECT * FROM users")!
```

The LSP shows inferred types inline as you type, so you always know what the compiler deduced. Function signatures are always explicit — inference only applies to local variables.

**The language encourages explicit types** — the formatter enforces them. But you're never blocked from writing code because you can't remember whether it's `List<Map<String, User>>` or `Map<String, List<User>>`.

## Keyword Exclusivity

Every keyword in Prove has exactly one purpose. No keyword is overloaded across different contexts. This makes the language predictable and parseable by humans without memorizing context-dependent rules.

**Core keywords:**

| Keyword | What it does |
|---------|-------------|
| `transforms` | Declares a pure function — no side effects. See [Functions & Verbs](functions.md#intent-verbs) |
| `validates` | Declares a function that returns true or false. See [Functions & Verbs](functions.md#intent-verbs) |
| `reads` | Declares a pure function that extracts or queries data. See [Functions & Verbs](functions.md#intent-verbs) |
| `creates` | Declares a pure function that constructs a new value. See [Functions & Verbs](functions.md#intent-verbs) |
| `inputs` | Declares a function that reads from the outside world. See [Functions & Verbs](functions.md#intent-verbs) |
| `outputs` | Declares a function that writes to the outside world. See [Functions & Verbs](functions.md#intent-verbs) |
| `streams` | Declares a blocking IO loop over a source. See [Functions & Verbs](functions.md#streams-blocking-io-loop) |
| `detached` | Declares a fire-and-forget async function. See [Functions & Verbs](functions.md#async-verbs) |
| `attached` | Declares an awaited async function. See [Functions & Verbs](functions.md#async-verbs) |
| `listens` | Declares an event dispatcher. See [Functions & Verbs](functions.md#async-verbs) |
| `matches` | Declares a pure match dispatch on algebraic type. See [Functions & Verbs](functions.md#intent-verbs) |
| `main` | The program's entry point — can freely mix reading and writing |
| `from` | Marks where the function body starts. See [Functions & Verbs](functions.md#body-marker-from) |
| `where` | Adds a value constraint to a type. See [Type System](types.md#refinement-types) |
| `as` / `is` | `as` declares a variable — `port as Port = 8080`. `is` defines a type — `type Port is Integer` |
| `type` | Starts a type definition — `type Port is Integer where 1..65535` |
| `match` | Branches on a value. See [Type System](types.md#pattern-matching) |
| `ensures` | States what a function guarantees about its result. See [Contracts](contracts.md#requires-and-ensures) |
| `requires` | States what must be true before calling a function. See [Contracts](contracts.md#requires-and-ensures) |
| `explain` | Documents `from` block steps using controlled natural language. See [Contracts](contracts.md#explain) |
| `terminates` | Required for recursive functions. See [Contracts](contracts.md#terminates) |
| `trusted` | Marks a function as unverified. See [Contracts](contracts.md#trusted) |
| `valid` | References a `validates` function as a predicate |
| `comptime` | Marks code for compile-time evaluation. See [Compiler](compiler.md#comptime-compile-time-computation) |
| `event_type` | Declares the algebraic type for a `listens` dispatcher. See [Functions & Verbs](functions.md#async-verbs) |
| `foreign` | Declares a C FFI block inside a module |
