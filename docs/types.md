# Type System

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

```prove
count as Integer = 42                          // Integer:[64 Signed]
flags as Integer:[8 Unsigned] = 0xFF
price as Decimal:[128 Scale:2] = 19.99         // financial precision
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
    close(file)                        // file consumed here
```

## Refinement Types

Types carry constraints, not just shapes. The compiler rejects invalid values statically — no unnecessary runtime checks, no `unwrap()`.

```prove
type Port is Integer:[16 Unsigned] where 1 .. 65535
type Email is String where r"^[^[:space:]@]+@[^[:space:]@]+\.[^[:space:]@]+$"
type NonEmpty<T> is List<T> where len > 0

transforms head(xs NonEmpty<T>) T    // no Option needed, emptiness is impossible
```

The compiler rejects `head([])` statically.

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

### CSV Declaration (Upcoming v1.X)

*CSV-based lookup declaration is planned for version 1.X and not yet implemented.*

For large lookup tables, data can be loaded from a CSV file at compile time instead of manual declaration:

```prove
type TokenKind:[Lookup] is String where @("tokens.csv")
```

The CSV must have columns matching the variant names and values.

Once the compiler is self-hosted (written in Prove), a compiled program can generate CSV files which then get embedded into a new binary at compile time. This creates a binary-table lookup system that could eventually form the foundation of a database built on binary lookup files.

### Multi-Type Lookup (Upcoming v1.X)

*Multi-type lookups are planned for version 1.X and not yet implemented.*

A lookup can map to multiple primitive types simultaneously:

```prove
type TokenKind:[Lookup] is String | Integer where
    One | "one" | 1
    Two | "two" | 2
```

The lookup is contextual — the result type depends on the context it's used in:

```prove
var as String = TokenKind:One     # var is "one"
var as Integer = TokenKind:One    # var is 1
```

Rules:
- **No overlapping types** — each type can only appear once: `String | Integer | String` is invalid
- **Native types only** — only primitive types are supported (String, Integer, Boolean, Byte)
- **Compile-time only** — this is not a runtime type; the lookup type is resolved at compile time based on usage context

## Algebraic Types with Exhaustive Matching

Like Rust/Haskell, but with row polymorphism. Compiler errors if you forget a variant.

```prove
type Result<T, E> is Ok(T) | Err(E)
type Shape is Circle(radius Decimal) | Rect(w Decimal, h Decimal)

# compiler error if you forget a variant
transforms area(s Shape) Decimal
from
    match s
        Circle(r) => pi * r * r
        Rect(w, h) => w * h
```

## Effect Types

IO is encoded in the verb, not in annotations. The compiler knows which functions touch the world (`inputs`/`outputs`) and which are pure (`transforms`/`validates`). Pure functions get automatic memoization and parallelism.

```prove
inputs read_config(path Path) String!               // IO inherent, ! = can fail

transforms parse(s String) Result<Config, Error>   // pure — failure in return type

transforms rewrite(c Config) Config                // pure, infallible, parallelizable
```

## Ownership Lite (Linear Types with Compiler-Inferred Borrows)

Linear types for resources, but without Rust's lifetime annotation burden. The compiler infers borrows or asks you. Ownership is a type modifier, consistent with mutability and other storage concerns.

```prove
inputs process(file File:[Own]) Data!
from
    content as String = read(file)
    close(file)
```

## No Null

No null — use `Option<T>`, enforced by the compiler.
