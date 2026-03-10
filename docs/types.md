---
title: Type System - Prove Programming Language
description: Learn about Prove's type system including type modifiers, refinement types, Option, Result, and pattern matching.
keywords: Prove types, refinement types, type modifiers, Option, Result, pattern matching
---

# Type System

## Always-Available Types

Certain types are built into the language and available without explicit import:

| Category | Types | Description |
|----------|-------|-------------|
| **Primitives** | `Integer`, `Decimal`, `Float`, `Boolean`, `String`, `Character`, `Byte`, `Unit` | Core types with optional modifiers |
| **Containers** | `List<Value>`, `Option<Value>`, `Result<Value, Error>`, `Table<Value>` | Generic collection types |
| **Special** | `Value`, `Error`, `Source` | Used by stdlib for dynamic values, errors, and sources |

These are implicitly available in every module. No import statement needed.

## Type Modifiers

Type modifiers describe **how** a value is stored and represented — size, signedness, encoding, precision. They use bracket syntax after the type name: `Type:[Modifier ...]`. Value constraints (what values are valid) belong in refinement types with `where`, not modifiers.

```prove
// Modifier: how it's stored (16-bit, unsigned)
raw_port as Integer:[16 Unsigned] = 8080

// Refinement: what values are valid
type Port is Integer where 1..65535

// Combined: storage + value constraint
type Port is Integer:[16 Unsigned] where 1..65535
```

### Modifier Axes

Each modifier occupies a **distinct axis** (size, signedness, encoding, etc.). Rules:

- **Order-independent** — `Integer:[Signed 64]` and `Integer:[64 Signed]` are identical. The compiler normalizes internally.
- **One per axis** — two modifiers on the same axis is a compile error: `Integer:[32 64]` → conflicting size modifiers.
- **Positional** when the kind is unambiguous. **Named** (`Key:Value`) when a bare value could be confused: `Decimal:[128 Scale:2]`.
- **Bare type uses defaults** — `Integer` means `Integer:[64 Signed]`, `String` means `String:[UTF8]`, `Decimal` means `Decimal:[64]`.

### Primitive Type Modifiers

| Type | Modifier Axes | Default | Examples |
|------|---------------|---------|----------|
| `Integer` | size (8/16/32/64/128), signedness (Signed/Unsigned) | `Integer:[64 Signed]` | `Integer:[32 Unsigned]`, `Integer:[8]` |
| `Decimal` | precision (32/64/128), scale (Scale:N) | `Decimal:[64]` | `Decimal:[128 Scale:2]` |
| `Float` | precision (32/64) | `Float:[64]` | `Float:[32]` |
| `String` | encoding (UTF8/ASCII/UTF16), max length | `String:[UTF8]` | `String:[UTF8 15]`, `String:[ASCII 255]` |
| `Character` | encoding (UTF8/UTF16/ASCII) | `Character:[UTF8]` | `Character:[ASCII]` |
| `Boolean` | — | — | — |
| `Byte` | — | — | — |

`Float` is **opt-in** — `Decimal` is the default for fractional numbers. `Float:[64]` uses IEEE 754 hardware floats for performance-critical domains (scientific computing, graphics, signal processing) where speed matters more than exact precision. Mixing `Float` and `Decimal` requires explicit conversion.

**Decimal precision mappings:** `Decimal:[32]` compiles to C `float`, `Decimal:[64]` (default) compiles to `double`, and `Decimal:[128]` compiles to `long double`. The `Scale:N` modifier is parsed but not yet enforced at runtime.

```prove
count as Integer = 42                          // Integer:[64 Signed]
flags as Integer:[8 Unsigned] = 0xFF
price as Decimal:[128 Scale:2] = 19.99         // financial precision
gravity as Float = 9.8f                        // Float (IEEE 754, note 'f' suffix)
name as String = "Alice"                        // String:[UTF8]
code as String:[ASCII 4] = "US01"              // ASCII, max 4 characters
letter as Character = 'A'                       // Character:[UTF8]
```

### Storage Modifiers

Beyond representation, modifiers also express storage concerns like mutability and ownership. These use the same bracket syntax — storage is a property of the type, not a separate keyword.

**`Mutable`** — variables are immutable by default. `Mutable` enables reassignment:

```prove
counter as Integer:[Mutable] = 0
counter = counter + 1
```

**`Own`** — linear ownership. The value is consumed on use. See [Ownership Lite](#ownership-lite-linear-types-with-compiler-inferred-borrows) below.

```prove
inputs process(file File:[Own]) Data!
from
    content as String = read(file)
    close(file)
    // file consumed here
```

## Refinement Types

Types carry constraints, not just shapes. The compiler validates values against constraints — currently via runtime checks inserted at assignment boundaries, with static rejection of provably-invalid literals planned.

```prove
type Port is Integer:[16 Unsigned] where 1 .. 65535
type Email is String where r"^[^[:space:]@]+@[^[:space:]@]+\.[^[:space:]@]+$"
type NonEmpty<Value> is List<Value> where len > 0

transforms head(xs NonEmpty<Value>) Value    // no Option needed, emptiness is impossible
```

The compiler rejects `head([])` at the type level — `[]` is not a `NonEmpty`.

## Lookup Types (Bidirectional Maps)

A `[Lookup]` type is a bidirectional map combining an algebraic type with its value representations in a single declaration — normally you'd need three separate declarations (the type, variant→value map, and value→variant map).

### Single-Type Lookup

```prove
type TokenKind:[Lookup] is String where
    Main | "main"
    NotMain | "not_main"
    TrueLit | "true"
            | "false"
```

Access is bidirectional:

- **Reverse lookup** — `TokenKind:"main"` → returns the `TokenKind` variant (`Main`)
- **Forward lookup** — `TokenKind:Main` → returns the `String` value (`"main"`)

A variant can have multiple values (stacked entries like `TrueLit`), but reverse lookup on such variants is ambiguous and produces an error at compile time.

Lookup tables must be exhaustive — every variant needs at least one value, and all values must be unique across the table.

### Multi-Type Lookup

A lookup can map to multiple primitive types simultaneously:

```prove
type TokenKind:[Lookup] is String Integer where
    One | "one" | 1
    Two | "two" | 2
```

The lookup is contextual — the result type depends on the context it's used in:

```prove
var as String = TokenKind:One     // var is "one"
var as Integer = TokenKind:One    // var is 1
```

Rules:
- **No overlapping types** — each type can only appear once: `String | Integer | String` is invalid
- **Native types only** — only primitive types are supported (String, Integer, Boolean, Byte)
- **Compile-time only** — this is not a runtime type; the lookup type is resolved at compile time based on usage context

### Store-Backed Lookup (Runtime)

A `[Lookup]` type with `runtime` instead of `where` gets its data from a [Store](stdlib/table-list-store.md#store) at runtime instead of compiled-in entries. The type definition declares the column schema — pipe-separated types — and the data is populated dynamically.

```prove
type Color:[Lookup] is String | Integer
  runtime
```

The variable is typed as the lookup type, but backed by a `StoreTable` at the C level:

```prove
Store outputs store, inputs table, validates store table
    types Store StoreTable

db as Store = store("/tmp/my_store")!
colors as Color = table(db, "colors")!
```

Rows are constructed with the type name and added to the table:

```prove
row as Color = Color(Red, "red", 0xFF0000)
add(colors, row)
```

Runtime lookup uses `variable:"key"` syntax (lowercase variable, not uppercase type name):

```prove
color as Integer = colors:"red"    // returns 0xFF0000
```

The column indices are resolved at compile time from the schema. The lookup key column is determined by the operand type (`String` → column 0), and the value column is determined by the expected return type (`Integer` → column 1).

Rules:
- **Schema from type** — the pipe-separated types define column count and types
- **No `where` entries** — data is runtime-only, not compiled in
- **Variable lookup** — `variable:"key"` instead of `TypeName:"key"`
- **Type compatibility** — a store-backed lookup type is interchangeable with `StoreTable` in function arguments

## Option and Result

Prove has no null. Instead, two algebraic types handle absence and failure:

- **`Option<Value>`** — a value that might not exist: `Some(value)` or `None`
- **`Result<Value, Error>`** — a computation that might fail: `Ok(value)` or `Err(error)`

Both are always-available types (no import needed). Use [pattern matching](#pattern-matching) to extract values:

```prove
match Table.get("key", config)
    Some(value) => use(value)
    None => default_value()

match Parse.json(raw)
    Ok(data) => process(data)
    Err(msg) => report(msg)
```

The [Error](stdlib/error-log.md#error) stdlib module provides utilities like `unwrap_or` for common patterns.

## Algebraic Types with Exhaustive Matching

Compiler errors if you forget a variant.

```prove
type Result<Value, Error> is Ok(Value) | Err(Error)
type Shape is Circle(radius Decimal) | Rect(w Decimal, h Decimal)

// compiler error if you forget a variant
transforms area(s Shape) Decimal
from
    match s
        Circle(r) => pi * r * r
        Rect(w, h) => w * h
```

## Pattern Matching

Prove has no `if`/`else`. All branching is done through `match` — and good Prove code rarely matches on booleans at all.

```prove
match route
    Get("/health") => ok("healthy")
    Get("/users")  => users()!
    _              => not_found()

match discount
    FlatOff(off) => max(0, amount - off)
    PercentOff(rate) => amount * (1 - rate)

MAX_CONNECTIONS as Integer = comptime
    match cfg.target
        "embedded" => 16
        _ => 1024
```

This is not an omission. It is a deliberate design choice.

### Why No `if`

**1. Types replace booleans.**

When you reach for `if connected then send(data) else retry()`, the real question is: what *kind* of connection state are you in? Model it as a type and the branching becomes meaningful:

```prove
type Connection is Active(socket Socket) | Disconnected(reason String)

match connection
    Active(socket) => send(socket, data)
    Disconnected(reason) => retry(reason)
```

Each arm names what it handles. No `true`/`false` to mentally decode. The compiler enforces that every variant is covered — add a `Reconnecting` state later and the compiler tells you everywhere you need to handle it.

**2. `if` hides missing cases.**

An `if` without `else` silently does nothing on the false branch. The programmer may have forgotten it. With types, there's no such escape — every variant must be handled.

**3. One construct is simpler than two.**

`if`/`else` adds no expressive power over `match`. It only adds surface area to the language, the parser, the type checker, the emitter, and every tool that processes Prove code. One construct means less to learn and fewer ways to express the same thing.

**4. Contracts replace conditional logic.**

Where other languages use `if` to decide whether to run code, Prove uses validation. Consider:

```prove
transforms calculate_total(items List<OrderItem>, discount Discount, tax TaxRule) Price
  ensures result >= 0
  requires len(items) > 0
from
    sub as Price = subtotal(items)
    discounted as Price = apply_discount(discount, sub)
    apply_tax(tax, discounted)
```

There is no `if discount > 0 then apply_discount(...)`. The [`requires`](contracts.md#requires-and-ensures) clause on `apply_discount` ensures the compiler has already proven the discount is valid before the call happens. The "branching" lives in the type system and contracts, not in boolean conditions.

**5. Boolean matching is a code smell.**

`match x > 0 / true => ... / false => ...` is technically valid but signals that you should model your domain better. Instead of branching on `amount > 0`, define `type Positive is Integer where > 0` and let the type system handle it. The branching disappears into the type — where the compiler can prove things about it.

### The Rule

Branch on *what something is*, not on *whether something is true*. Types and contracts handle the rest — [`requires`](contracts.md#requires-and-ensures) guards preconditions, [`ensures`](contracts.md#requires-and-ensures) guarantees postconditions, and [`explain`](contracts.md#explain) documents the reasoning. No boolean branch needed.

## Error Propagation

`!` marks fallibility — on declarations it means "this function can fail", at call sites it propagates the error upward. Only IO verbs (`inputs`, `outputs`) and `main` can use `!`. Pure verbs cannot be failable ([E361](diagnostics.md#e361-pure-function-cannot-be-failable)). There is one `Error` type — errors are program-ending, not flow control. `!` errors propagate up the call chain until they reach `main`, which exits with an error message. There is no try/catch.

Pure functions that need to represent expected failure cases use `Result<Value, Error>` and handle them with `match` — these are values, not errors.

```prove
main()!
from
    config as Config = load("app.yaml")!
    db as Store = connect(config.db_url)!
    serve(config.port, db)!
```

See [Functions & Verbs — IO and Fallibility](functions.md#io-and-fallibility) for how `!` relates to verb families.

## Effect Types

Effects are encoded in the verb, not in type annotations. The compiler tracks three effect families:

| Family | Verbs | Effect |
|--------|-------|--------|
| **Pure** | `transforms`, `validates`, `reads`, `creates`, `matches` | No IO, no concurrency. Automatically memoizable and parallelizable |
| **IO** | `inputs`, `outputs` | Reads from or writes to the external world. `!` marks additional fallibility |
| **Async** | `detached`, `attached`, `listens` | Concurrent execution via cooperative coroutines (`prove_coro`). `detached` may call IO; `attached`/`listens` may not |

```prove
inputs read_config(path Path) String!               // IO inherent, ! = can fail

transforms parse(s String) Result<Config, Error>   // pure — failure in return type

transforms rewrite(c Config) Config                // pure, infallible, parallelizable

detached log(event Event)                          // async, fire-and-forget
from
    console(event.message)

attached fetch(url String) String                  // async, caller awaits result
from
    request(url)&

listens dispatcher(cmd Command)                    // async, cooperative loop
from
    Exit          => cmd
    Process(data) => handle(data)&
```

The compiler enforces effect boundaries:
- Pure verbs cannot call IO or async functions
- `attached` and `listens` cannot call blocking IO (`inputs`/`outputs`) — they run cooperatively and blocking would stall the yield cycle
- `detached` may call IO freely — it runs independently and blocking only affects its own coroutine, not the caller
- `listens` dispatches on the first parameter's algebraic type — the `from` block is an implicit match with a mandatory `Exit` arm
- The `&` marker at a call site signals async dispatch, analogous to `!` for error propagation

## Function Types (`Verb`)

`Verb<P1, P2, ..., R>` describes a function that takes parameters of types `P1, P2, ...` and returns `R`. The last type argument is always the return type; all preceding arguments are parameter types. `Verb<R>` with a single argument describes a zero-parameter function returning `R`.

This allows stdlib functions to accept callbacks without hardcoded special-casing:

```prove
// A function that takes a Conflict and returns a Resolution
resolver as Verb<Conflict, Resolution>

// Used as a parameter type in function signatures
transforms merge(base StoreTable, local TableDiff, remote TableDiff,
                 resolver Verb<Conflict, Resolution>) MergeResult

// Called with a lambda
Store.merge(base, local, remote, |c| KeepRemote)

// Or with a named function reference
Store.merge(base, local, remote, my_resolver)
```

Convention: `Verb` mirrors the language's verb-based function declarations. The type resolves internally to a C function pointer with the correct parameter and return types.

## Ownership Lite (Linear Types with Compiler-Inferred Borrows)

Linear types for resources, but without Rust's lifetime annotation burden. The compiler infers borrows or asks you. Ownership is a type modifier, consistent with mutability and other storage concerns.

```prove
inputs process(file File:[Own]) Data!
from
    content as String = read(file)
    close(file)
```

## No Null

No null — use `Option<Value>`, enforced by the compiler.
