---
title: Intent Verbs - Prove Programming Language
description: Complete reference for Prove's intent verbs — transforms, validates, derives, creates, matches, dispatches.
keywords: Prove verbs, intent verbs, transforms, validates, derives, creates, matches, dispatches
---

# Intent Verbs

Functions are declared with a **verb** that describes their purpose. The verb IS the declaration — no `fn` or `function` keyword. The compiler verifies the implementation matches the declared intent.

Verbs are divided into two families: **pure** (no side effects) and **IO** (interacts with the outside world).

## Pure Verbs

Pure verbs have no side effects. The compiler enforces this. They can be memoized, inlined, and parallelized safely.

| Verb | Purpose | Compiler enforces |
|------|---------|-------------------|
| `creates` | Creates a new value from a given value | No `!`. Returns a freshly constructed value |
| `derives` | Non-mutating data access or derivation | No `!`. Never allocates. Non-mutating |
| `transforms` | Failable version of creates/derives | Allows `!`. Pure but can fail at runtime (deserialization, conversion) |
| `validates` | Pure boolean check | No `!`. Return type is implicitly `Boolean` |
| `matches` | Pure match dispatch on matchable type | No `!`. First parameter must be a matchable type (algebraic, String, Integer, Result, or Option). `from` block is implicitly a match |

### Semantic Guarantees

The verb carries strict guarantees that the compiler exploits for optimization:

| Verb | Allocates? | Can fail? | Compiler optimization |
|------|-----------|-----------|----------------------|
| `derives` | Never | Never | Freely inlined, reordered, and eliminated. No region scope needed. Best memoization candidate. |
| `creates` | Always | Never | Needs allocation but no error handling. Safe to inline. |
| `transforms` | May | Yes (`!`) | Requires error propagation. Conservative optimization only. |
| `validates` | Never | Never | Returns `Boolean`. Same safety guarantees as `derives`. |
| `matches` | Never | Never | Pure dispatch on algebraic type. Same safety guarantees as `derives`. |

**`derives` never allocates new values.** It extracts or recomputes from existing data — the return is always derivable from the input without heap allocation. If a function needs to allocate a new value (even if input and output types match), use `creates` instead.

**`creates` always allocates.** It constructs a freshly allocated value of a different type. The compiler knows it cannot fail, so no error-handling scaffolding is emitted.

**`transforms` is the only pure verb that can fail.** The `!` suffix is allowed, and the compiler emits error propagation paths. Because it may allocate and may fail, the optimizer treats it conservatively.

### Examples

```prove
matches area(s Shape) Decimal
from
    Circle(r) => pi * r * r
    Rect(w, h) => w * h

validates email(address String)
from
    contains(address, "@") && contains(address, ".")

transforms config(data String) Config!
  requires valid toml(data)
from
    Config(toml(data))

derives normalize(data List<Decimal>) List<Decimal>
  ensures len(result) == len(data)
from
    max_val as Decimal = max(data)
    divide_each(data, max_val)

derives length(s String) Integer
from
    count_bytes(s)

creates builder() Builder
from
    allocate_buffer()
```

## IO Verbs

IO verbs interact with the external world. Side effects are explicit in the verb.

| Verb | Purpose | Compiler enforces |
|------|---------|-------------------|
| `inputs` | Reads/receives from external world | IO is inherent. `!` marks fallibility |
| `outputs` | Writes/sends to external world | IO is inherent. `!` marks fallibility |
| `dispatches` | IO match dispatch on matchable type | First parameter must be a matchable type. IO calls allowed in match arms. `from` block is implicitly a match |
| `streams` | Blocking IO loop with implicit match | IO is inherent. Body is a single match expression with an `Exit()` arm |

`dispatches` is the IO counterpart to `matches`. Use it when you need to pattern-match on a variant and perform IO in each arm (e.g., routing commands to handlers, dispatching messages by type).

### Examples

```prove
inputs users() List<User>!
from
    query(db, "SELECT * FROM users")!

outputs log(message String)
from
    write(stdout, message)

dispatches parse_command(command Option<String>, arguments List<String>)!
from
    Some("build") => build(arguments)!
    Some("check") => check(arguments)!
    Some("--version") =>
        config as Config = config()!
        console(f"{config.package.version}")
    _ => console(HELP_TXT)

inputs request(route Route, body String, db Store) Response!
from
    match route
        Get(/health) => ok("healthy")
        Get(/users) => users(db)! |> encode |> ok
        Post(/users) => create(db, body)! |> encode |> created
        _ => not_found()
```

## Verb-Dispatched Identity

Functions are identified by the triple `(verb, name, parameter types)` — not just `(name, parameter types)`. The same function name can be declared multiple times with different verbs:

```prove
validates email(address String)
from
    contains(address, "@") && contains(address, ".")

creates email(raw String) Email
from
    lowercase(trim(raw))

inputs email(user_id Integer) Email!
from
    query(db, "SELECT email FROM users WHERE id = {user_id}")!
```

Three functions, all named `email`, with completely different intents.

## Context-Aware Call Resolution

At call sites, you use **just the function name** — the compiler resolves which verb-variant to call based on context:

```prove
// Predicate context → resolves to validates email
clean_list as List<Email> = filter(inputs, valid email)

// Email context + String param → resolves to creates email
clean as Email = email(raw_input)

// Email context + Integer param → resolves to inputs email
stored as Email = email(user.id)
```

Resolution rules:
1. **`valid` keyword** → explicitly invokes the `validates` variant (e.g., `valid email(address)` or `valid email` as a predicate reference)
2. **Expected type** from assignment → matches the variant returning that type
3. **Parameter types** disambiguate between variants with same return type
4. **Ambiguous** → first matching candidate wins based on arity and parameter types

## Parameters

Go-style: `name Type` (no colon):

```prove
matches area(s Shape) Decimal
inputs request(route Route, body String) Response!
validates email(address String)
```

## Body Marker: `from`

Every function body begins with `from`. No exceptions:

```prove
matches area(s Shape) Decimal
from
    pi * s.radius * s.radius

inputs users() List<User>!
  ensures len(result) >= 0
from
    query(db, "SELECT * FROM users")!
```

## IO and Fallibility

IO is inherent in the verb. Fallibility is marked with `!` on the return type. Pure verbs have neither IO nor `!`:

```prove
matches area(s Shape) Decimal
from
    pi * s.radius * s.radius

inputs users() List<User>!
from
    query(db, "SELECT * FROM users")!

outputs write_log(entry String)
from
    append(log_file, entry)
```

Reads as: *"inputs users, returns List of User, can fail!"*

See [Type System — Error Propagation](types.md#error-propagation) for how `!` works at call sites.

See [Contracts](contracts.md#requires-and-ensures) for `ensures` and `requires` on function signatures.
