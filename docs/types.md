# Type System

## Refinement Types

Types carry constraints, not just shapes. The compiler rejects invalid values statically — no unnecessary runtime checks, no `unwrap()`.

```prove
type Port is Integer:[16 Unsigned] where 1..65535
type Email is String where matches(/^[^@]+@[^@]+\.[^@]+$/)
type NonEmpty<T> is List<T> where len > 0

transforms head(xs NonEmpty<T>) T    // no Option needed, emptiness is impossible
```

The compiler rejects `head([])` statically.

## Algebraic Types with Exhaustive Matching

Like Rust/Haskell, but with row polymorphism. Compiler errors if you forget a variant.

```prove
type Result<T, E> is Ok(T) | Err(E)
type Shape is Circle(radius Decimal) | Rect(w Decimal, h Decimal)

// compiler error if you forget a variant
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
        content as String = read(file)     // immutable borrow, inferred
        close(file)                       // ownership consumed
        // read(file)                     // compile error: used after close
```

## No Null

No null — use `Option<T>`, enforced by the compiler.
