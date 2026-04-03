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
- **Effects**: CamelCase — `IO`, `Fail`, `Async`

The compiler **enforces** casing. Wrong case is a compile error, not a warning. UPPER_SNAKE_CASE indicates a compile-time constant — no `const` keyword needed.

## Modules and Imports

Each file is a module. The filename (without extension) is the module name in CamelCase. The `module` block is mandatory and contains all declarations/metadata: narrative, imports, types, constants, and invariant networks. Functions remain top-level:

```prove
module InventoryService
  narrative: """Products are added to inventory..."""
  Text validates length
  Auth validates login transforms login
  Http inputs request session

  type Product is
    sku Sku
    name String

  MAX_CONNECTIONS as Integer = 1024

  invariant_network Accounting
    total >= 0
```

A verb applies to all space-separated names that follow it. Verb groups are separated by their leading verb keyword (commas between groups are accepted but not required). Multiple verbs for the same function name import each variant. The verb is part of the function's identity — see [Functions & Verbs](verbs.md#verb-dispatched-identity) for details.

### Local imports (`.ModuleName`)

Prefix an import with `.` to force resolution against local (sibling) modules only, bypassing the stdlib:

```prove
module Report
  .Format validates length transforms pad  // uses local Format.prv, not stdlib Format
  Text validates length
```

This is useful when you need a project-specific module that happens to share a name with a stdlib module. Without the `.` prefix, the compiler raises **E316** because the name is ambiguous — it refuses to silently pick one over the other.

> **Not recommended for stdlib names.** Overriding a stdlib module name makes the code harder to read and prevents future callers from importing the stdlib module under the same name in the same project. Prefer a distinct name for the local module when possible (e.g. `ReportFormat` instead of `Format`).

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

No curly braces. Indentation defines scope (like Python). No semicolons — newlines terminate statements. Newlines are suppressed after operators (including `=`, `:`, `|`, `.`, `..`), commas, opening brackets, `->`, `=>`.

## Primitive Types

Every type uses its full name. No abbreviations. Type modifiers use bracket syntax `Type:[Modifier ...]` for storage and representation concerns. Value constraints belong in [refinement types](types.md#refinement-types) (`where`), not modifiers.

See [Type System — Type Modifiers](types.md#type-modifiers) for the complete reference.

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
pattern as String = r"\d+"      // raw string / regex pattern (String-typed)
path as String = /users/alice/  // path literal (String-typed)
```

The **`f` suffix** on floating-point literals (like `9.8f`) creates a `Float` type, suitable for IEEE 754 operations like `Math.sqrt` and `Math.floor`. Without the suffix (like `3.14`), you get a `Decimal` type for exact decimal arithmetic.

### Extended Literal Syntax

**F-strings** interpolate expressions inside `{}`:

```prove
name as String = "world"
msg as String = f"Hello, {name}!"
total as String = f"sum = {a + b}"
```

**Triple-quoted strings** span multiple lines:

```prove
description as String = """
  This is a multi-line
  string literal.
"""
```

**Hex, binary, and octal literals**:

```prove
color as Integer = 0xFF
mask as Integer = 0b1010
perms as Integer = 0o77
```

**Number underscores** for readability:

```prove
population as Integer = 1_000_000
budget as Decimal = 9_999.99
```

**Escape sequences** in strings and characters: `\n` (newline), `\t` (tab), `\r` (carriage return), `\\` (backslash), `\"` (double quote), `\{` and `\}` (literal braces in f-strings), `\0` (null), `\e` (escape).

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

### Compound Assignment

Mutable variables support compound assignment operators:

```prove
counter as Integer:[Mutable] = 0
counter += 1
counter -= 1
counter *= 2
counter /= 2
```

### Operator Precedence

From highest to lowest:

| Precedence | Operators | Description |
|------------|-----------|-------------|
| 1 (highest) | `.` | Field access |
| 2 | `-` `!` | Unary negation, logical not |
| 3 | `*` `/` `%` | Multiplication, division, modulo |
| 4 | `+` `-` | Addition, subtraction |
| 5 | `==` `!=` `<` `>` `<=` `>=` | Comparison |
| 6 | `&&` | Logical AND |
| 7 | `\|\|` | Logical OR |
| 8 | `\|>` | Pipe |
| 9 (lowest) | `..` | Range |

## Type Inference with Formatter Enforcement

The compiler infers types when unambiguous, but **`prove format` always inserts explicit type annotations**. This means you can write clean code during development, and the formatter makes it explicit before commit.

```prove
// What you write:
port as = 8080
server as = new_server()
users as = query(db, "SELECT * FROM users")!

// What `prove format` produces:
port as Integer = 8080
server as Server = new_server()
users as List<User> = query(db, "SELECT * FROM users")!
```

The LSP shows inferred types on hover, so you always know what the compiler deduced. Function signatures are always explicit — inference only applies to local variables.

**The language encourages explicit types** — the formatter enforces them. But you're never blocked from writing code because you can't remember whether it's `List<Map<String, User>>` or `Map<String, List<User>>`.

## Keywords

Every keyword in Prove has exactly one purpose. No keyword is overloaded across different contexts. This makes the language predictable and parseable by humans without memorizing context-dependent rules.

For a complete keyword reference with links to detailed documentation, see the [Keyword Reference](types.md#keyword-reference) in the Type System document.

The `comptime` keyword marks compile-time computation — see [Compiler](compiler.md#comptime-compile-time-computation) for details.
