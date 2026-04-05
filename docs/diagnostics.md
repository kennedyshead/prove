---
title: Diagnostic Codes - Prove Programming Language
description: Complete reference for Prove compiler diagnostic codes including errors, warnings, and informational messages.
keywords: Prove diagnostics, compiler errors, compiler warnings, diagnostic codes
---

# Diagnostic Codes

The Prove compiler emits diagnostics with unique codes, source locations, and suggestions. Each diagnostic has a severity level:

- **Error** — compilation fails; must be fixed
- **Warning** — code compiles but the compiler could use this information (e.g., optimization, contract reasoning)
- **Info** — good practice suggestions or issues that `prove format` fixes automatically

Diagnostic codes use a letter prefix matching their severity (`E` = error, `W` = warning, `I` = info) and a numeric group (1xx = lexer/parser, 2xx = parser, 3xx = checker, 4xx = comptime, 5xx = prose coherence, 6xx = completeness).

---

## Errors

### E101 — Unterminated string literal

A string opened with `"` was not closed before end of line or file.

### E102 — Unterminated triple-quoted string

A string opened with `"""` was not closed with a matching `"""`.

### E103 — Unterminated character literal

A character literal opened with `'` was not closed.

### E104 — Unterminated regex literal

A regex literal opened with `r/` was not closed with `/`.

### E105 — Unterminated raw string literal

A raw string opened with `r"` was not closed.

### E106 — Unterminated f-string literal

An f-string opened with `f"` was not closed.

### E107 — Unknown escape sequence

A backslash followed by an unrecognized character inside a string. The error message shows the problematic sequence (e.g., `` `\q` ``). Valid escapes: `\n`, `\r`, `\t`, `\\`, `\"`, `\{`, `\}`, `\0`.

### E108 — Unexpected end of escape sequence

A backslash at the end of a string with no character following it.

### E109 — Unexpected character

A character that doesn't belong to any valid token. The error message shows the problematic character (e.g., `` `@` ``, `` `#` ``, `` `$` ``).

### E150 — Reactive verb body must be a single match expression

The body of a `listens`, `streams`, or `renders` verb must consist of a single `match` expression. Multiple statements or non-match expressions are not allowed.

### E200 — Missing module declaration

Every `.prv` file must begin with a `module` declaration and narrative. When a filename is available, the compiler suggests a module name derived from it (e.g., `my_utils.prv` suggests `module MyUtils`).

```prove
module MyModule
  narrative: """Description of this module"""
```

### E210 — Expected token

The parser expected a specific token (e.g., `)`, `:`, `from`) but found something else. The error message shows both the expected and actual tokens.

### E211 — Expected declaration

The parser expected a top-level declaration (`module`, `transforms`, `validates`, `inputs`, `outputs`, `main`) but found an unexpected token.

### E212 — Expected type body

After `type Name is`, the parser expected a field definition (like `name String`), a variant name (like `Some` or `None`), or `binary`, but found something else.

### E213 — Expected expression

The parser expected an expression (a name, literal, or parenthesized group) but found an unexpected token. The error message shows what was found instead.

### E214 — Verb used as identifier

A verb keyword (`transforms`, `validates`, `derives`, `creates`, `matches`, `inputs`, `outputs`) cannot be used as a variable or function name. Use a different name, or declare it as a verb.

### E215 — Expected pattern

In a `match` arm, the parser expected a pattern (variant name like `Some`, literal like `0` or `"hello"`, binding name, or wildcard `_`) but found something else.

### E300 — Undefined type

A type name used in a type expression could not be resolved. If the name is similar to a known type, the compiler suggests a correction (e.g., `Intger` → did you mean `Integer`?).

### E301 — Duplicate type definition

A type with the same name was already defined.

### E302 — Variable already defined

A variable with the same name was already defined in this scope.

### E310 — Undefined name

An identifier could not be found in any scope. The compiler will suggest similar names if available.

### E311 — Undefined function

An unqualified function call references a function that is not defined or imported.

### E312 — Function not imported from module

A qualified call (`Module.function()`) references a function that was not explicitly imported from that module.

### E313 — Module not imported

A qualified call references a module that has no import declaration. If the module exists (in stdlib or as a local module), the compiler tells you to add an import. If the module name is misspelled, it suggests the closest match.

### E314 — Unknown module in import

An import references a module that is neither part of the standard library nor a known local (sibling) module. The formatter removes the import line.

If the module is a local file and its name collides with a stdlib module, use `.ModuleName` to disambiguate (see [E316](#e316-ambiguous-module-name-local-shadows-stdlib)).


### E316 — Ambiguous module name (local shadows stdlib)

A local module and a stdlib module share the same name. The compiler refuses to silently pick one — use a `.` prefix on the import to explicitly request the local module:

```prove
// Error: Format exists both as a local file and in the stdlib
module Report
  Format validates length  // E316

// Fix: prefix with '.' to force local resolution
module Report
  .Format validates length  // OK — uses local Format.prv
```

See [Local imports](syntax.md#local-imports-modulename) for details and caveats.

### E317 — Name shadows builtin type

A user-defined type has the same name as a built-in type (`Integer`, `String`, `Boolean`, `List`, `Option`, `Result`, etc.).

### E320 — Type mismatch in binary expression

The operand types of a binary operator are incompatible. Logical operators (`&&`, `||`) require `Boolean`; arithmetic operators require compatible numeric types.

### E321 — Type mismatch in definition

The inferred type of a constant, variable, or assignment does not match the declared type.

```prove
MAX as Integer = "hello"

port as Port = get_string(config, "port")
```

### E322 — Return type mismatch

The inferred type of a function body does not match the declared return type. For failable functions, the body can return the success type (e.g., a function returning `String!` can have a body that returns `String`).

### E325 — Non-stringable type in f-string

An interpolated expression in an f-string must be a stringable type (`String`, `Integer`, `Decimal`, `Float`, `Boolean`, `Character`).

### E326 — Unit used as variable type

`Unit` cannot be used as a variable type or assigned to a variable. `Unit` represents the absence of a meaningful value and is only used as a return type for side-effecting functions.

### E330 — Wrong number of arguments

A function call has a different number of arguments than the function signature expects.

### E331 — Argument type mismatch / Field mutation in pure function

This code is used in two contexts:

1. **Call checking:** An argument type does not match the corresponding parameter type in the function signature.
2. **Purity enforcement:** A function with a pure verb (`transforms`, `validates`, `derives`, `creates`, `matches`) contains a field assignment. Pure functions must not mutate state — construct a new value instead.

```prove
// Context 1 — argument type mismatch
transforms run(n Integer) Integer
from
    needs_int("hello")

// Context 2 — field mutation in pure function (construct new value instead)
derives set_email(user User, email Email) User
from
    user.email = email
    user
```

### E335 — Type cannot be used as Value

An argument passed to a `Value` parameter has a type that cannot be automatically converted to `Value`. Only scalar types (`Integer`, `Float`, `String`, `Boolean`) and types with known Value representations can be passed where `Value` is expected.

### E340 — Field not found

Field access (`.field`) on a type that either doesn't have that field or doesn't support field access.

### E341 — Cannot pass borrowed value to mutable parameter

A borrowed value cannot be passed to a parameter that requires mutability.

### E350 — Fail propagation in non-failable function

The `!` operator (fail propagation) can only be used inside functions marked as failable with `!` in their signature.

```prove
transforms run(path String) String
from
    read_file(path)!

transforms run(path String) String!
from
    read_file(path)!
```

### E351 — `!` applied to non-failable expression

The `!` fail propagation operator was applied to an expression that cannot fail. Only calls to failable functions (those declared with `!`) can be propagated.

### E352 — Function calls not allowed in `where` constraints

A `where` constraint on a refinement type contains a function call or other complex expression. Only primitive expressions are allowed: comparisons, ranges, boolean operators, literals, regex patterns, identifiers, and field access.

```prove
// Error — function call in constraint
type Valid is Integer where is_prime(value)

// Correct — comparison
type Valid is Integer where value > 0 && value < 100

// Correct — regex pattern for String
type Email is String where r".+@.+\..+"
```

### E355 — Refinement constraint violated at compile time

A literal value assigned to a refinement type does not satisfy the type's `where` constraint. The compiler checks literal values statically.

```prove
type Positive is Integer where >= 0

// Error — -1 violates >= 0
p as Positive = -1

// OK — 42 satisfies >= 0
p as Positive = 42
```

### E356 — Know claim is provably false

A `know` expression can be statically disproven by the compiler's proof engine. The claim contradicts constant arithmetic or algebraic identities.

```prove
// Error — 2 + 2 is not 5
transforms bad(n Integer) Integer
    know: 2 + 2 == 5
    from
        n
```

### E357 — Division by zero

A division or modulo operation has a literal zero as the divisor. This is always an error because it would cause undefined behaviour at runtime.

```prove
// Error — dividing by literal zero
transforms bad(x Integer) Integer
    from
        x / 0
```

### E361 — Pure function cannot be failable

Functions with pure verbs cannot use the `!` fail marker. The exception is `transforms`, which is allowed to be failable.

### E362 — Pure function cannot call IO function

A function with a pure verb cannot call IO functions. This covers both the built-in `sleep` function and any resolved function with an IO verb (`inputs`, `outputs`).

### E363 — Pure function cannot call user-defined IO function

A function with a pure verb cannot call a function that uses an IO verb (`inputs` or `outputs`).

### E364 — Lambda captures variable (deprecated)

Lambdas now support capturing immutable variables from an enclosing scope. This error code is no longer emitted. Captured values are passed via a compiler-generated context struct.

### E365 — `matches` verb requires matchable first parameter

A `matches` function must take a matchable type as its first parameter for dispatch. Matchable types are algebraic types, `String`, and `Integer`.

### E366 — Recursive function missing `terminates`

Every recursive function must declare a `terminates` measure expression.

```prove
transforms factorial(n Integer) Integer
from
    match n
        0 => 1
        _ => n * factorial(n - 1)

transforms factorial(n Integer) Integer
  terminates: n
from
    match n
        0 => 1
        _ => n * factorial(n - 1)
```

### E368 — Parallel HOF requires pure callback

`par_map`, `par_filter`, and `par_reduce` require callbacks with pure verbs (`transforms`, `validates`, `derives`, `creates`, `matches`). IO verbs (`inputs`, `outputs`) and async verbs (`detached`, `attached`, `listens`) are not allowed because they cannot safely execute in parallel.

```prove
// Error — outputs is not a pure verb
outputs show(n Integer) Unit
    from
        n

transforms caller(xs List<Integer>) Integer
    from
        par_map(xs, show)
        0

// OK — derives is pure
derives double(n Integer) Integer
    from
        n + n

transforms caller(xs List<Integer>) Integer
    from
        par_map(xs, double)
        0
```

### E369 — `par_each` callback cannot be an async verb

`par_each` allows IO verb callbacks (unlike `par_map`/`par_filter`/`par_reduce`), but async verbs (`detached`, `attached`, `listens`) cannot be used as callbacks because they run in their own concurrency context and cannot be called as plain functions.

```prove
// Error — detached is an async verb
detached fire_and_forget(n Integer) Integer
    from
        n

outputs caller(xs List<Integer>) Unit
    from
        par_each(xs, fire_and_forget)

// OK — outputs is allowed in par_each
outputs log_item(n Integer) Integer
    from
        n

outputs caller(xs List<Integer>) Unit
    from
        par_each(xs, log_item)
```

### E151 — `listens`/`streams`/`renders` body missing `Exit` arm

A `listens`, `streams`, or `renders` function's `from` block must be a single implicit match (bare arms) with an `Exit` arm. The `Exit` variant terminates the loop.

```prove
// Error — no Exit arm
listens handler(source Event)
from
    Data(text) => process(text)&

// Correct — Exit arm terminates the loop
listens handler(source Event)
from
    Exit       => source
    Data(text) => process(text)&
```

### E370 — Unknown variant / `attached` without return type

This code is used in two contexts:

1. **Pattern matching:** A match arm references a variant that does not exist in the algebraic type.
2. **Async verbs:** An `attached` function is declared without a return type. `attached` spawns a coroutine and blocks until a result is ready — it must declare what it returns.

### E371 — Non-exhaustive match / blocking IO in async body

This code is used in two contexts:

1. **Pattern matching:** A match expression on an algebraic type does not cover all variants and has no catch-all (`_`) pattern.
2. **Async verbs:** A blocking `inputs`/`outputs` call appears inside a `listens` body. `detached` and `attached` are exempt — `detached` runs independently, and `attached` has its own coroutine stack for safe blocking IO.

### E372 — Unknown variant for generic type / async call without `&`

This code is used in two contexts:

1. **Pattern matching:** A match arm on a `Result` or `Option` uses a variant name that does not belong to that type (e.g. `Some(x)` on a `Result`, or `Ok(x)` on an `Option`).
2. **Async verbs:** An `attached` or `listens` function is called without the `&` marker. These verbs always require `&`.

### E373 — Non-exhaustive match on generic type

A match expression on a `Result` or `Option` does not cover all variants and has no catch-all (`_`) pattern. `Result` requires `Ok` and `Err`; `Option` requires `Some` and `None`.

### E374 — `detached` or `renders` declared with a return type

`detached` is fire-and-forget — the caller never waits for a result. `renders` is a UI render loop — it processes events until the `Exit` arm terminates the loop. Neither should declare a return type.

### E375 — Duplicate value in lookup table

A `[Lookup]` type contains duplicate values. Every value in the table must be unique so that reverse lookups are unambiguous.

```prove
// Error — duplicate value
type TokenKind:[Lookup] is String where
    Main | "main"
    From | "main"   // "main" already used → E375

// Correct — unique values
type TokenKind:[Lookup] is String where
    Main | "main"
    From | "from"
```

### E376 — Lookup operand must be literal or variant

The lookup accessor (`TypeName:operand`) requires a compile-time constant: a string literal, integer literal, boolean literal, or variant name. Variables and expressions are not allowed.

```prove
TokenKind:"main"    // ok — string literal
TokenKind:Main      // ok — variant name
TokenKind:some_var  // E376 — variable not allowed
```

### E377 — Value not found in lookup table

The operand of a lookup accessor does not match any entry in the table.

```prove
type TokenKind:[Lookup] is String where
    Main | "main"

TokenKind:"unknown"  // E377 — "unknown" not in table
TokenKind:Missing    // E377 — Missing is not a variant of TokenKind
```

### E378 — Reverse lookup on stacked variant

A reverse lookup was attempted on a variant that maps to multiple values. When a variant has stacked values (like match arms), the reverse direction is ambiguous.

```prove
type TokenKind:[Lookup] is String where
    Foreign | "foreign"
    BooleanLit | "true"
               | "false"

TokenKind:Foreign     // ok → "foreign"
TokenKind:BooleanLit  // E378 — BooleanLit has 2 values ("true", "false")
```

Wrap the reverse lookup in a `matches` function if you need to handle stacked variants.

### E379 — Lookup column count mismatch

An entry in a multi-column `:[Lookup]` table has a different number of values than columns declared.

```prove
type TokenKind:[Lookup] is String Integer Decimal where
    First | "first" | 1          // E379 — 2 values, expected 3
```

### E380 — Invalid ensures expression

The `ensures` expression is not valid.

### E381 — Requires expression must be Boolean

A `requires` precondition expression does not evaluate to `Boolean`.

```prove
transforms process(x Integer) Integer
  requires x + 1

transforms process(x Integer) Integer
  requires x > 0
```

### E382 — Satisfies references undefined type

A `satisfies` annotation references a type that is not defined.

### E383 — Near-miss expected type mismatch

The expected value in a `near_miss` declaration doesn't match the function's return type.

```prove
// Error — function returns Integer but near_miss expects Boolean
derives double(n Integer) Integer
  near_miss 0 => false

// Correct — expected type matches return type
derives double(n Integer) Integer
  near_miss 0 => 0
```

### E384 — Know expression must be Boolean

A `know` expression must evaluate to `Boolean`.

```prove
transforms process(order Order) Receipt
  know: len(order.items)

transforms process(order Order) Receipt
  know: len(order.items) > 0
```

### E385 — Assume expression must be Boolean

An `assume` expression must evaluate to `Boolean`.

```prove
transforms process(order Order) Receipt
  assume: order.total

transforms process(order Order) Receipt
  assume: order.total > 0
```

### E386 — Believe expression must be Boolean

A `believe` expression must evaluate to `Boolean`. See also E384 (`know`) and E385 (`assume`).

### E387 — Unsupported type in lookup column

A multi-column `:[Lookup]` table column uses an unsupported type. Allowed column types: `String`, `Integer`, `Decimal`, `Boolean`.

### E388 — CSV file not found for lookup

The CSV file referenced in a `:[Lookup]` table `file(...)` declaration was not found at the specified path.

### E389 — Lookup column type not found

A lookup expression `TypeName:variable` was used in a function whose return type does not match any column in the lookup table.

```prove
type TokenKind:[Lookup] is String Integer where
    First | "first" | 1

transforms bad(kind TokenKind) Decimal  // E389 — Decimal not a column
from
    TokenKind:kind
```

### E391 — Duplicate explain entry name

Each named explain entry must have a unique name.

### E392 — Explain entries do not cover ensures

The number of named explain entries is less than the number of `ensures` clauses.

### E393 — Believe without ensures

The `believe` keyword requires `ensures` to be present on the function.

### E394 — Explain condition must be Boolean

A `when` condition in an explain entry must evaluate to `Boolean`.

### E395 — Implicit Value conversion

The function body returns `Value` (or `Table<Value>`) but the declared return type is a concrete type like `String` or `Table<String>`. This implicit conversion is not allowed — use explicit conversion or change the return type.

### E396 — Invariant constraint must be Boolean

A constraint expression inside an `invariant_network` referenced by `satisfies` does not evaluate to `Boolean`.

### E397 — `binary` is reserved for stdlib

The `binary` keyword (as a function body marker or type body) is reserved for stdlib implementations. User code should use `:[Lookup]` for lookup tables or wrap stdlib types with Prove functions.

### E398 — IO-bearing `attached` called outside async context

An `attached` function whose body contains blocking IO calls (`inputs`/`outputs`) was called via `&` from a context that does not cooperatively yield. IO-bearing `attached` functions are only safe when called from a `listens` or another `attached` body, because those contexts yield cooperatively while the child coroutine performs IO.

`attached` functions that contain only pure computation (no IO) can be called from any async body.

### E399 — Ambiguous column type in lookup

A lookup table has duplicate column types (e.g. two `Decimal` columns), and the access expression does not disambiguate which column is intended. Use named columns (`name:Type`) to resolve the ambiguity.

### E400 — Match arm returns Unit while others return value

A `match` expression has arms with inconsistent return types — some arms return a value while others return `Unit`. Every arm of a match expression used as an expression must return the same type. This check is skipped for `listens` and `streams` verbs where match arms are loop-body statements.

### E401 — `event_type` must reference an algebraic type

The `event_type` annotation on a `renders` verb references a type that is not an algebraic type. The event type must be an algebraic type so that match arms can dispatch on its variants. This check is currently enforced for `renders` only.

### E402 — Async verb first parameter type mismatch

A `listens` verb's first parameter is not `List<Attached>`, or a `renders` verb's first parameter is not `List<Listens>`. The first parameter must be the appropriate worker/dispatcher reference list.

### E403 — Registered function is not an `attached` verb

A function in the `listens` worker list (the `List<Attached>` first argument) is not declared with the `attached` verb. Only `attached` functions can be registered as event-producing workers.

### E404 — Attached return type doesn't match event variant

A registered worker function's return type is not a variant of the `listens` dispatcher's `event_type`. Each worker must return a variant of the event type so the dispatcher can match on it.

### E405 — `event_type` on non-`listens`/`renders`/`attached` verb

The `event_type` annotation was used on a function that is not a `listens`, `renders`, or `attached` verb. This annotation is only valid on these async verbs.

### E406 — `listens`/`renders` missing `event_type` annotation

A `listens` or `renders` verb was declared without an `event_type` annotation. The `event_type` annotation is required to declare the algebraic type that the dispatcher matches on.

### E407 — Decimal literal exceeds Scale:N precision / `state_init` on non-`renders` verb

This code is used in two contexts:

1. **Decimal precision:** A decimal literal assigned to a `Decimal:[Scale:N]` variable has more decimal places than the scale allows. For example, assigning `3.141` to `Decimal:[Scale:2]` exceeds the allowed 2 decimal places.
2. **Async verbs:** The `state_init` annotation was used on a function that is not a `renders` verb.

### E408 — Scale mismatch / `renders` missing `state_init`

This code is used in two contexts:

1. **Decimal precision:** An assignment or comparison between two `Decimal:[Scale:N]` types with different scale values.
2. **Async verbs:** A `renders` verb was declared without a `state_init` annotation.

### E409 — `state_type` on non-`listens` verb

The `state_type` annotation was used on a function that is not a `listens` verb. This annotation is only valid on `listens` dispatchers.

### E410 — Tail recursion not supported in comptime

A `comptime` block contains a tail-recursive construct. Comptime evaluation does not support tail recursion.

### E411 — Unsupported expression in comptime

A `comptime` block contains an expression type that the compile-time interpreter cannot evaluate.

### E412 — Comptime `++` operand type mismatch

The `++` operator in a `comptime` block requires both operands to be lists or both to be strings.

### E413 — Unsupported binary operator in comptime

A binary operator used in a `comptime` block is not supported by the compile-time interpreter.

### E414 — Unsupported unary operator in comptime

A unary operator used in a `comptime` block is not supported by the compile-time interpreter.

### E415 — Implicit match not supported in comptime

A `match` expression without an explicit subject is not supported in `comptime` blocks.

### E416 — Non-exhaustive match in comptime

A `match` expression in a `comptime` block did not match any arm at evaluation time.

### E417 — Comptime evaluation failed

A `comptime` block failed during evaluation. The error message includes the underlying cause.

### E418 — Undefined variable in comptime

A variable referenced in a `comptime` block is not defined in the comptime scope.

### E419 — Only simple function calls in comptime

A `comptime` block contains a complex call expression (e.g., method call or qualified call). Only simple function calls are supported.

### E420 — `read()` expects a single string argument

The `read()` function in a `comptime` block must be called with exactly one string argument (a file path).

### E421 — File not found in comptime `read()`

The file path passed to `read()` in a `comptime` block does not exist relative to the module's source directory.

### E422 — Unknown function in comptime

A `comptime` block calls a function that is not available in the compile-time interpreter. Built-in comptime functions: `read`, `platform`, `len`, `contains`, `to_upper`, `to_lower`. User-defined pure functions are also callable.

### E423 — Recursive type has no base case

A recursive algebraic type references itself in every variant. At least one variant must not reference the type, otherwise values of this type can never be constructed.

---

### E430 — `with` references unknown parameter

A `with` constraint names a parameter that does not exist in the function signature.

---

### E431 — `with` on non-Struct parameter

A `with` constraint targets a parameter whose type is not `Struct`. Only `Struct`-typed parameters support row-polymorphic field constraints.

---

### E432 — Duplicate `with` for same field

Two `with` constraints declare the same field on the same parameter.

---

### E433 — Field access on Struct not in `with`

Code accesses a field on a `Struct` parameter that was not declared via a `with` constraint. All accessed fields must be declared.

---

### E434 — Record missing required Struct fields

A concrete record passed to a `Struct` parameter does not have all the fields required by the `with` constraints, or one of its fields has an incompatible type.

### E435 — Unit type used as struct field

A struct field has type `Unit`, which has no runtime representation in C and cannot be stored in a struct. Use a concrete type instead.

```prove
type Config is
    name String
    debug Unit    // error: Unit has no runtime representation
```

Fix: use the intended type (`Boolean`, `Option<String>`, etc.).

### E436 — IO verb with `requires` must be failable

An `inputs`, `outputs`, or `dispatches` function declares a `requires` clause but is neither failable (`!`) nor returns `Option<T>`. The contract needs a runtime enforcement path — either fail on violation or return `None`.

```prove
// Error — requires with no enforcement path
inputs load(path String) Config
  requires len(path) > 0

// Fix — make it failable
inputs load(path String) Config!
  requires len(path) > 0
```

### E437 — Pure verb cannot accept Mutable parameters

A non-allocating pure verb (`derives`, `validates`, `matches`) has a parameter with the `Mutable` modifier. These verbs must not mutate their inputs — mutation violates purity guarantees.

```prove
// Error — derives cannot take Mutable
derives total(items List<Item>:[Mutable]) Integer

// Fix — remove Mutable (derives never mutates)
derives total(items List<Item>) Integer
```

---

### E438 — Option\<T\> passed where T expected

An `Option<T>` value is passed to a parameter that expects `T` directly. This would cause a null pointer dereference at runtime if the value is `None`. Unwrap the option explicitly before passing it.

```prove
derives double(n Integer) Integer

outputs main(arguments List<String>)!
from
    maybe as Option<Integer> = find(items, "key")
    // Error — passing Option<Integer> where Integer expected
    double(maybe)
    // Fix — unwrap with match or unwrap()
    double(unwrap(maybe, 0))
```

---

## Warnings

### W300 — Unused local variable

A variable is declared inside a function but never referenced. Remove it or prefix with `_` to suppress.

```prove
outputs export(arguments List<String>)!
from
    config as Config = config()   // warning: unused variable 'config'
    console("done")
```

### W361 — `unwrap()` may panic at runtime

A call to the stdlib `unwrap()` function on an `Option` or `Result` will panic at runtime if the value is `None` or `Err`. Use `match` to handle both cases, or provide a default with the two-argument form `unwrap(option, default)`.

```prove
// warning: unwrap() will panic if the Option is None
name as String = unwrap(value(0, arguments))

// safe alternatives:
name as String = unwrap(value(0, arguments), "default")

name as String = match value(0, arguments)
    Some(n) => n
    _ => "default"
```

### W304 — Match condition guaranteed by requires

A `match` expression tests a condition identical to a `requires` precondition. Since `requires` guarantees the condition is true, the match is redundant and the compiler could optimize it away.

```prove
transforms abs_val(n Integer) Integer
  requires n >= 0
from
    match n >= 0
        true => n
        false => 0 - n

transforms abs_val(n Integer) Integer
  requires n >= 0
from
    n
```

### W305 — Duplicate match arm for variant

A `match` expression has two or more arms matching the same variant without field destructuring. The later arm is unreachable.

### W311 — Intent without contracts

A function has an `intent` declaration but no `ensures` or `requires` to validate it.

### W312 — Import verb mismatch

The verb specified in an import does not match any overload of the function in the imported module.

```prove
module Example
  narrative: "Just an example of imports"
  Parse transforms json   -- W312: Parse has no 'transforms json'; available: creates, derives
```

### W313 — Intent prose doesn't reference function concepts

The `intent:` prose text has no vocabulary overlap with the function body — no called function names, parameter names, or type names appear in the description.

```prove
derives sort(xs List<Value>) List<Value>
  intent: "count the number of elements"  -- W313: 'count' unrelated to sort/xs/merge_sort
from
    merge_sort(xs)
```

Fix: describe what the function actually does using the names of the functions it calls, its parameters, or its return type.

### W321 — Explain text missing concept references

An explain entry doesn't reference any function concepts (parameter names, variable names, or `result`).

### W322 — Duplicate near-miss input

Two `near_miss` declarations on the same function have identical input expressions.

### W323 — Ensures without explain

A function has postconditions but no `explain` block.

### W324 — Ensures without requires

A function has postconditions but no preconditions.

### W325 — Explain without ensures

An `explain` block is present but there are no `ensures` clauses. Without contracts, the explain is unverifiable.

### W326 — Recursion depth may be unbounded

A recursive function's `terminates` measure suggests O(n) call depth. Consider using `map`, `filter`, or `reduce` via the pipe operator instead.

### W327 — Know claim cannot be proven

The compiler's proof engine cannot statically prove a `know` claim. The claim will be treated as a runtime assertion instead.

```prove
// Warning — n > 0 depends on runtime value
transforms process(n Integer) Integer
    know: n > 0
    from
        n
```

### W328 — Ensures clause doesn't reference result

An `ensures` postcondition doesn't reference `result`, which likely means it's checking an input rather than constraining the output. Postconditions should constrain the return value.

```prove
// Warning — checks input, not output
derives double(n Integer) Integer
  ensures n > 0

// Correct — constrains the return value
derives double(n Integer) Integer
  ensures result == n * 2
```

### W330 — Surviving mutant

A previous `prove build` run (mutation testing) found a surviving mutant in this function. The function's contracts were not strong enough to detect the mutation. Add or strengthen `requires`/`ensures` clauses to catch it.

### W332 — Unused pure function result

A pure function (`transforms`, `validates`, `derives`, `creates`, `matches`) is called but its result is discarded. Pure functions have no side effects — if you don't use the result, the call has no effect. Assign the result to a variable or remove the call.

```prove
// Warning — result discarded
transforms foo() Integer
from
    double(21)  // result not used
    0

// OK — result is used
transforms foo() Integer
from
    x as Integer = double(21)
    x + 1
```

### W340 — Domain profile violation

A module declares a `domain:` tag and uses a type or pattern that the domain profile discourages. For example, the `finance` domain prefers `Decimal` over `Float`. Also emitted for unknown domain names.

### W341 — Missing required contract for domain

A function in a domain-tagged module is missing a contract required by the domain profile. For example, the `finance` domain requires `ensures` on all non-trusted functions.

### W342 — Missing required annotation for domain

A function is missing an annotation required by the domain profile. For example, the `safety` domain requires `explain` blocks and `terminates` on recursive functions.

### W343 — Narrative flow step is not a defined function

A `flow:` line in the module `narrative` block references a step name that doesn't match any function defined in the module.

```prove
module PaymentFlow
  narrative: "flow: validate -> charge -> send_receipt"
  // send_receipt is not defined — W343

transforms validate(amount Decimal) Boolean
from amount > 0

outputs charge(amount Decimal) Unit
from System.print("charged")
```

Fix: either define the missing function or update the `flow:` entry to match the actual function names.

### W350 — Duplicate column type in lookup

A lookup table has two or more columns with the same type but no named columns to tell them apart. Use `name:Type` syntax to disambiguate (e.g. `probability:Decimal`).

### W360 — Own/borrow overlap in expression

A pointer field access (e.g., `value.path`) is passed to a function call that will release it **and** also used elsewhere in the same expression. Because C argument evaluation order is unspecified, the release can happen before the borrow, causing use-after-free.

Split the expression into separate statements so the owned call completes before the borrow.

```prove
// Warning — content() releases value.path, but SourceFile also reads it
transforms load(value DirEntry) SourceFile
from
    SourceFile(value.path, content(value.path))

// Correct — separate statements ensure ordering
transforms load(value DirEntry) SourceFile
from
    body as String = content(value.path)
    SourceFile(value.path, body)
```

### W370 — Verification chain broken (public)

A public function calls a verified function (one with `ensures` clauses) but has no `ensures` clause of its own. This means the callee's guarantees do not propagate to callers of this function.

Add `ensures` to propagate verification, or `trusted` to explicitly opt out.

```prove
transforms helper(n Integer) Integer
    ensures result >= 0
    from
        n

// Warning — calls helper (verified) but has no ensures
transforms caller(n Integer) Integer
    from
        helper(n)
```

### W371 — Verification chain broken (strict)

Same as W370 but for internal (underscore-prefixed) functions. Only emitted with `--strict`.

### W372 — Arm-bound `know` claim cannot be proven / Failable call result discarded

This warning has two triggers:

**1. Arm-bound know claim.** A `know:` claim in the function header references a variable that is bound inside a match arm (e.g., `inner` from `Some(inner)`), but the proof context cannot establish the claim. The claim is treated as a runtime assertion.

```prove
// Warning — inner is arm-bound but know claim is not provable
transforms get_first(xs Option<Integer>) Integer
    know: inner > 0     // arm-bound `inner`, but no requires guarantees this
from
    match xs
        Some(inner) => inner
        None => 0
```

Add a `requires` that constrains the subject, or remove the `know` if the claim is not needed as a checked assertion.

**2. Failable call result discarded.** A failable function is called as a statement but its result is not propagated with `!` or handled with `match`. The error is silently ignored.

Use `!` to propagate the failure, or `match` to handle it explicitly.

### W373 — Failable call in lambda without `!`

A failable function is called inside a lambda body without the `!` propagation operator. The lambda returns a `Result` instead of the unwrapped value, which is likely unintended.

### W390 — Temporal operation out of declared order

A function calls temporal operations in an order that violates the module's `temporal:` declaration. If the module declares `temporal: a -> b -> c`, calling `b` before `a` in the same function body is flagged.

```prove
module Auth
  temporal: authenticate -> authorize -> access

// Warning — authorize before authenticate
inputs bad_flow(creds Credentials, resource Resource) Data!
from
    perm as Permission = authorize(token, resource)
    token as Token = authenticate(creds)!
    access(perm, resource)!
```

### W391 — Satisfies invariant without ensures

A function declares `satisfies` for an invariant network but has no `ensures` clauses. Without postconditions, the compiler cannot verify that the function actually satisfies the invariant's constraints.

### W501 — Verb not described in module narrative

A function's verb keyword is not implied by any action word in the module's `narrative:` block. The narrative should describe every kind of operation the module performs. Emitted only with `prove check --coherence`.

### W502 — Explain entry doesn't match from-body

An `explain` entry's prose text has no overlap with the names of operations or parameters in the function's `from` block. The explain block should document what the code actually does. Emitted only with `prove check --coherence`.

### W503 — Chosen declared without why_not

A function declares `chosen:` to document the approach taken but has no `why_not:` entries for rejected alternatives. Design decisions are more valuable when paired with documented trade-offs.

### W504 — Chosen text doesn't relate to from-body

A function's `chosen:` text has no overlap with the operations or parameters in the `from` block. The chosen description should relate to what the implementation actually does.

### W505 — Why-not entry mentions no known name

A `why_not:` entry contains no function name, type name, or other identifier from the current scope. Rejection notes should anchor to something concrete — a function, type, or algorithm — so future readers understand what was considered.

### W506 — Why-not entry contradicts from-body

A `why_not:` entry mentions a function name that the `from` block actually calls. The rejected approach is in use, which contradicts the rationale. Either the `why_not` is outdated, or the implementation should use a different approach.

### W601 — Intent file parse warning

An `.intent` file contains a malformed line — either a vocabulary entry not using `Name is description` format, or an unrecognized verb keyword. Fix the entry format or use a valid verb.

### W602 — Vocabulary term defined but never referenced

A vocabulary entry in an `.intent` file defines a term that is never referenced by any module's intent declarations. Remove the unused vocabulary entry or add a module intent that uses it.

### W603 — Flow references undefined module

A flow declaration in an `.intent` file references a module name that is not defined in any `module` block in the same file. Fix the module name or add the missing module declaration.

### I340 — Vocabulary drift from narrative

A function name uses vocabulary not found in the module's `narrative:` block. This is informational — it helps keep code names consistent with the module's stated purpose. Emitted only with `prove check --coherence`.


---

## Info

Info diagnostics are suggestions for good practice. Most can be auto-fixed by `prove format`.

### I201 — Module missing narrative

A module declaration has no `narrative:` string. The narrative documents the module's purpose.

```prove
module MyModule
  narrative: """Handles user authentication and session management"""
```

### I210 — Verb body should be a single match expression / Trailing comma

This code is used in two contexts:

1. **Checker:** A `listens`, `streams`, or `renders` verb body should be a single `match` expression for clarity.
2. **Parser:** A trailing comma was found in a parameter list. `prove format` removes it automatically.

### I300 — Unused variable

A declared variable is never referenced. The formatter prefixes the name with `_`.

### I301 — Unreachable match arm

A match arm after a wildcard (`_`) pattern is unreachable. The formatter removes it.

### I302 — Unused import

An imported name is never referenced in the module body. The formatter removes unused import items, or the entire import line if all items are unused.

```prove
module Main
  Text derives trim upper

transforms shout(s String) String
from
    Text.upper(s)
```

### I303 — Unused type definition

A user-defined type is declared but never referenced. The formatter removes it.

### I304 — Unused constant definition

A user-defined constant is declared but never referenced. The formatter removes it.

### I305 — Variable initialized outside its used scope

A variable is declared at function scope but only used inside a single match arm. Moving it into that arm avoids unnecessary initialization when the other arms execute.

```prove
outputs build(arguments List<String>)!
from
    config as Config = config()   // info: only used in the _ arm below
    match contains(arguments, "--help")
        true => console(HELP_TEXT)
        _ => pybuild(config, cwd())
```

Fix: move the declaration into the arm where it's used.

### I310 — Implicitly typed variable

A variable declared via `x = expr` without a type annotation. The formatter adds `as Type` based on type inference.

### I311 — Value coercion is checked at runtime

A variable with a concrete type annotation (e.g. `Table<Value>`, `String`) is assigned from a `Value` expression. The compiler inserts a runtime coercion via `prove_value_as_*()`, but the type cannot be verified at compile time.

### I315 — Import not found in module

An import declaration names a function, type, or constant that does not exist in the specified module (stdlib or local). The import is automatically removed by `prove format`.

### I318 — Module cannot import from itself

A module's import block references itself. This is a no-op and is automatically removed by `prove format`.

### I320 — Function without contracts

A function has more than 5 statements (or more than 1 statement for `transforms`/`matches` verbs) but no `requires` or `ensures` clauses. Adding contracts enables mutation testing and helps the compiler reason about correctness.

### I360 — `validates` has implicit Boolean return

A `validates` function always returns `Boolean`. The formatter strips the redundant return type.

```prove
// Before formatting
validates is_active(u User) Boolean

// After formatting
validates is_active(u User)
```

### I367 — Consider extracting match to matches verb

A `match` expression appears inside a function that does not use the `matches` verb. While this is allowed, extracting the match logic into a separate `matches` function improves code flow and makes the branching intent explicit.

```prove
// Info — match in transforms (works, but could be clearer)
transforms classify(n Integer) String
from
    match n > 0
        true => "positive"
        false => "non-positive"

// Better — use matches verb
matches classify(n Integer) String
from
    match n > 0
        true => "positive"
        false => "non-positive"
```

### I438 — `derives` function returns heap type and allocates

A `derives` function returns a heap-allocated type (String, List, record, etc.) and its body allocates. `derives` is intended for non-allocating derivations — use `creates` instead when the function constructs new heap values. Auto-fixable by `prove format`.

### I439 — `creates` function does not allocate

A `creates` function body does not perform any heap allocation. `creates` signals that the function constructs a new value — if it only extracts or recomputes from inputs, use `derives` instead. Auto-fixable by `prove format`.

### I440 — `transforms` function is not failable

A `transforms` function neither uses `!` nor calls any failable function. `transforms` is the failable pure verb — if the function cannot fail, use `creates` (if it allocates) or `derives` (if it doesn't). Auto-fixable by `prove format`.

### I375 — `&` on a non-async callee

The `&` async dispatch marker is used on a call to a function that is not an async verb (`detached`, `attached`, `listens`). The marker has no effect. `prove format` removes it.

### I377 — `attached` call runs synchronously outside `listens`

An `attached` function is called with `&` outside a `listens` body. The call works but runs synchronously — there is no event loop to schedule it on. Inside a `listens` body, `attached&` is the standard await pattern and produces no diagnostic.

### I378 — `detached` function called without `&`

A `detached` function is called without the `&` marker. `detached` is fire-and-forget and should always use `&`. `prove format` will add it.

### I601 — Incomplete implementation (todo)

A function body contains a `todo` placeholder, indicating the implementation is not finished. This is informational only — the function will compile but will panic at runtime if the `todo` path is reached.

```prove
transforms stub(x Integer) Integer
from
    todo "implement hash function"
```
