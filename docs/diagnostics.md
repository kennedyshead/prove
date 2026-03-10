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

Diagnostic codes use a letter prefix matching their severity (`E` = error, `W` = warning, `I` = info) and a numeric group (1xx = lexer, 2xx = parser, 3xx = checker, 4xx = comptime).

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

A verb keyword (`transforms`, `validates`, `reads`, `creates`, `matches`, `inputs`, `outputs`) cannot be used as a variable or function name. Use a different name, or declare it as a verb.

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

### E315 — Function not found in module

An import declaration names a function or type that does not exist in the specified module (stdlib or local).

### E316 — Name shadows builtin function

A user-defined function or parameter has the same name as a built-in function (`len`, `map`, `filter`, `reduce`, `each`).

```prove
transforms len(xs List<Integer>) Integer
from
    0

transforms length(xs List<Integer>) Integer
from
    0
```

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
2. **Purity enforcement:** A function with a pure verb (`transforms`, `validates`, `reads`, `creates`, `matches`) contains a field assignment. Pure functions must not mutate state — construct a new value instead.

```prove
// Context 1 — argument type mismatch
transforms run(n Integer) Integer
from
    needs_int("hello")

// Context 2 — field mutation in pure function (construct new value instead)
transforms set_email(user User, email Email) User
from
    user.email = email
    user
```

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

### E361 — Pure function cannot be failable

Functions with pure verbs cannot use the `!` fail marker.

### E362 — Pure function cannot call IO builtin

A function with a pure verb cannot call the built-in IO function `sleep`. Other IO operations (file read/write, console output) are accessed through stdlib modules with IO verbs and are caught by E363.

### E363 — Pure function cannot call user-defined IO function

A function with a pure verb cannot call a function that uses an IO verb (`inputs` or `outputs`).

### E364 — Lambda captures variable

Lambdas cannot reference variables from an enclosing scope (closures not supported). All values must be passed as arguments.

### E365 — `matches` verb requires matchable first parameter

A `matches` function must take a matchable type as its first parameter for dispatch. Matchable types are algebraic types, `String`, and `Integer`.

### E367 — *(moved to I367)*

See [I367](#i367-consider-extracting-match-to-matches-verb) in the Info section.

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

### E151 — `listens` body missing `Exit` arm

A `listens` function's `from` block must be a single implicit match (bare arms) with an `Exit` arm. The `Exit` variant terminates the cooperative loop.

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
2. **Async verbs:** An async function is called without the `&` marker inside an async body.

### E373 — Non-exhaustive match on generic type / `&` used outside async body

This code is used in two contexts:

1. **Pattern matching:** A match expression on a `Result` or `Option` does not cover all variants and has no catch-all (`_`) pattern. `Result` requires `Ok` and `Err`; `Option` requires `Some` and `None`.
2. **Async verbs:** The `&` async dispatch marker is used at a call site outside of an async function body.

### E374 — `detached` or `listens` declared with a return type

`detached` is fire-and-forget — the caller never waits for a result. `listens` is a cooperative loop — it processes items from the first parameter's algebraic type until the `Exit` arm terminates the loop. Neither should declare a return type.

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
transforms double(n Integer) Integer
  near_miss 0 => false

// Correct — expected type matches return type
transforms double(n Integer) Integer
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

---

## Warnings

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

### W311 — Intent without contracts

A function has an `intent` declaration but no `ensures` or `requires` to validate it.

### W312 — Import verb mismatch

The verb specified in an import does not match any overload of the function in the imported module.

```prove
module Example
  narrative: "Just an example of imports"
  Parse transforms json   -- W312: Parse has no 'transforms json'; available: creates, reads
```

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
transforms double(n Integer) Integer
  ensures n > 0

// Correct — constrains the return value
transforms double(n Integer) Integer
  ensures result == n * 2
```

### W330 — Surviving mutant

A previous `prove build` run (mutation testing) found a surviving mutant in this function. The function's contracts were not strong enough to detect the mutation. Add or strengthen `requires`/`ensures` clauses to catch it.

### W332 — Unused pure function result

A pure function (`transforms`, `validates`, `reads`, `creates`, `matches`) is called but its result is discarded. Pure functions have no side effects — if you don't use the result, the call has no effect. Assign the result to a variable or remove the call.

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

### I300 — Unused variable

A declared variable is never referenced. The formatter prefixes the name with `_`.

### I301 — Unreachable match arm

A match arm after a wildcard (`_`) pattern is unreachable. The formatter removes it.

### I302 — Unused import

An imported name is never referenced in the module body. The formatter removes unused import items, or the entire import line if all items are unused.

```prove
module Main
  Text transforms trim upper

transforms shout(s String) String
from
    Text.upper(s)
```

### I303 — Unused type definition

A user-defined type is declared but never referenced. The formatter removes it.

### I310 — Implicitly typed variable

A variable declared via `x = expr` without a type annotation. The formatter adds `as Type` based on type inference.

### I311 — Value coercion is checked at runtime

A variable with a concrete type annotation (e.g. `Table<Value>`, `String`) is assigned from a `Value` expression. The compiler inserts a runtime coercion via `prove_value_as_*()`, but the type cannot be verified at compile time.

### I314 — Unknown module in import

An import references a module that is not part of the standard library. The formatter removes the import line.

### I320 — Function without contracts

A function has multiple statements (or uses `transforms`/`matches` verb) but no `requires` or `ensures` clauses. Adding contracts enables mutation testing and helps the compiler reason about correctness.

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

### I375 — `&` on a non-async callee

The `&` async dispatch marker is used on a call to a function that is not an async verb (`detached`, `attached`, `listens`). The marker has no effect. `prove format` removes it.

### I376 — `attached` body has no `&` calls

An `attached` function body contains no `&` async dispatch calls. This likely means the function should use `inputs` instead. `prove format` changes the verb.
