# Diagnostic Codes

The Prove compiler emits diagnostics with unique codes, source locations, and suggestions. Each diagnostic has a severity level:

- **Error** — compilation fails; must be fixed
- **Warning** — code compiles but the compiler could use this information (e.g., optimization, contract reasoning)
- **Info** — good practice suggestions or issues that `prove format` fixes automatically

Diagnostic codes use a letter prefix matching their severity (`E` = error, `W` = warning, `I` = info) and a numeric group (1xx = lexer, 2xx = parser, 3xx = checker, etc.).

---

## Errors

### E100 — Tab character not allowed

Prove uses spaces for indentation. Tab characters are not permitted.

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

A backslash followed by an unrecognized character inside a string.

### E108 — Unexpected end of escape sequence

A backslash at the end of a string with no character following it.

### E109 — Unexpected character

A character that doesn't belong to any valid token.

### E110 — Inconsistent indentation

Mixed indentation widths within the same file.

### E200 — Missing module declaration

Every `.prv` file must begin with a `module` declaration and narrative.

```prove
module MyModule
  narrative: """Description of this module"""
```

### E210 — Expected token

The parser expected a specific token (e.g., `)`, `:`, `from`) but found something else.

### E211 — Expected declaration

The parser expected a top-level declaration (`module`, `transforms`, `validates`, `inputs`, `outputs`, `main`) but found an unexpected token.

### E212 — Expected type body

After `type Name is`, the parser expected a type body (field definitions, variant names, or `binary`) but found something else.

### E213 — Expected expression

The parser expected an expression but found an unexpected token.

### E214 — Verb used as identifier

A verb keyword (`transforms`, `validates`, `reads`, `creates`, `matches`, `inputs`, `outputs`) cannot be used as an identifier.

### E215 — Expected pattern

In a `match` arm, the parser expected a pattern (variant name, literal, binding, or wildcard `_`).

### E216 — Duplicate verb in import

The same verb appears twice in an import declaration. Group all names under a single verb.

```prove
module Main
  // Wrong — duplicate 'transforms'
  Text transforms trim, transforms upper

  // Correct
  Text transforms trim upper
```

### E300 — Undefined type

A type name used in a type expression could not be resolved.

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

A qualified call references a module that has no import declaration.

### E315 — Function not found in module

An import declaration names a function that does not exist in the specified stdlib module.

### E316 — Name shadows builtin function

A user-defined function or parameter has the same name as a built-in function (`len`, `map`, `filter`, `reduce`, `each`, `to_string`, `clamp`, `println`, `print`, `readln`).

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

### E330 — Wrong number of arguments

A function call has a different number of arguments than the function signature expects.

### E331 — Argument type mismatch

An argument type does not match the corresponding parameter type in the function signature.

### E340 — Field not found

Field access (`.field`) on a type that either doesn't have that field or doesn't support field access.

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

A `where` constraint on a refinement type contains a function call or other complex expression. Only primitive expressions are allowed: comparisons, ranges, boolean operators, literals, identifiers, and field access.

```prove
type Valid is Integer where is_prime(value)

type Valid is Integer where value > 0 && value < 100
```

### E361 — Pure function cannot be failable

Functions with pure verbs cannot use the `!` fail marker.

### E362 — Pure function cannot call IO builtin

A function with a pure verb cannot call built-in IO functions (`read_file`, `write_file`, `open`, `close`, `flush`, `sleep`).

### E363 — Pure function cannot call user-defined IO function

A function with a pure verb cannot call a function that uses an IO verb (`inputs` or `outputs`).

### E364 — Lambda captures variable

Lambdas cannot reference variables from an enclosing scope (closures not supported). All values must be passed as arguments.

### E365 — `matches` verb requires algebraic first parameter

A `matches` function must take an algebraic type as its first parameter for dispatch.

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

### E370 — Unknown variant

A match arm references a variant that does not exist in the algebraic type.

### E371 — Non-exhaustive match

A match expression on an algebraic type does not cover all variants and has no catch-all (`_`) pattern.

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

### E391 — Duplicate explain entry name

Each named explain entry must have a unique name.

### E392 — Explain entries do not cover ensures

The number of named explain entries is less than the number of `ensures` clauses.

### E393 — Believe without ensures

The `believe` keyword requires `ensures` to be present on the function.

### E394 — Explain condition must be Boolean

A `when` condition in an explain entry must evaluate to `Boolean`.

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

### I314 — Unknown module in import

An import references a module that is not part of the standard library. The formatter removes the import line.

### I360 — `validates` has implicit Boolean return

A `validates` function always returns `Boolean`. The formatter strips the redundant return type.

```prove
// Before formatting
validates is_active(u User) Boolean

// After formatting
validates is_active(u User)
```
