# Syntax Reference

## Naming Conventions

- **Types, modules, and classes**: CamelCase — `Shape`, `Port`, `UserAuth`, `NonEmpty`, `HttpServer`
- **Variables and parameters**: snake_case — `port`, `user_list`, `max_retries`, `db_connection`
- **Functions**: snake_case — `area`, `binary_search`, `get_users`
- **Constants**: UPPER_SNAKE_CASE — `MAX_CONNECTIONS`, `LOOKUP_TABLE`, `DEFAULT_PORT`
- **Effects**: CamelCase — `IO`, `Fail`, `Async`

The compiler **enforces** casing. Wrong case is a compile error, not a warning. UPPER_SNAKE_CASE indicates a compile-time constant — no `const` keyword needed.

## Modules and Imports

Each file is a module. The filename (without extension) is the module name in CamelCase. Imports use `with Module use` syntax with verb-qualified function names:

```prove
with String use contains, length
with Auth use validates login, transforms login    // two verb variants of login
with Http use inputs request, inputs session
```

Multiple verbs for the same function name import each variant. The verb is part of the function's identity.

## Blocks and Indentation

No curly braces. Indentation defines scope (like Python). No semicolons — newlines terminate statements. Newlines are suppressed after operators, commas, opening brackets, `->`, `=>`.

## Primitive Types — Full Names, No Shorthands

Every type uses its full name. No abbreviations. Type modifiers use bracket syntax `Type:[Modifier ...]` for storage and representation concerns. Value constraints belong in refinement types (`where`), not modifiers.

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

```prove
count as Integer = 42                          // Integer:[64 Signed]
flags as Integer:[8 Unsigned] = 0xFF
price as Decimal:[128 Scale:2] = 19.99         // financial precision
name as String = "Alice"                        // String:[UTF8]
code as String:[ASCII 4] = "US01"              // ASCII, max 4 characters
active as Boolean = true
raw as Byte = 0x2A
letter as Character = 'A'
```

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

Types are defined with `type Name is`:

```prove
type Shape is
    Circle(radius Decimal)
    | Rect(w Decimal, h Decimal)

type Port is Integer:[16 Unsigned] where 1..65535

type Result<T, E> is Ok(T) | Err(E)

type User is
    id Integer
    name String
    email String
```

## Function Declarations — Intent Verbs

Functions are declared with a **verb** that describes their purpose. No `fn`, no `function` keyword — the verb IS the declaration. The compiler verifies the implementation matches the declared intent.

| Verb | Purpose | Compiler enforces |
|------|---------|-------------------|
| `transforms` | Pure data computation/conversion | No `!`. Failure encoded in return type (`Result`, `Option`) |
| `inputs` | Reads/receives from external world | IO is inherent. `!` marks fallibility. Implicit match when first param is algebraic |
| `outputs` | Writes/sends to external world | IO is inherent. `!` marks fallibility |
| `validates` | Pure boolean check | No `!`. Return type is implicitly `Boolean` |

```prove
transforms area(s Shape) Decimal
    from
        match s
            Circle(r) => pi * r * r
            Rect(w, h) => w * h

validates email(address String)
    from
        contains(address, "@") && contains(address, ".")

transforms normalize(data List<Decimal>) List<Decimal>
    ensures len(result) == len(data)
    from
        max_val as Decimal = max(data)
        divide_each(data, max_val)

transforms parse(raw String) Result<Config, ParseError>
    from
        decode(raw)

inputs users() List<User>!
    from
        query(db, "SELECT * FROM users")!

outputs log(message String)
    from
        write(stdout, message)

inputs request(route Route, req Request) Response!
    from
        Get("/health") => ok("healthy")
        Get("/users")  => users()! |> ok
        Post("/users") => create(req.body)! |> created
        _              => not_found()
```

## Verb-Dispatched Identity

Functions are identified by the triple `(verb, name, parameter types)` — not just `(name, parameter types)`. The same function name can be declared multiple times with different verbs, each with a distinct meaning:

```prove
validates email(address String)
    from
        contains(address, "@") && contains(address, ".")

transforms email(raw String) Email
    from
        lowercase(trim(raw))

inputs email(user_id Integer) Email!
    from
        query(db, "SELECT email FROM users WHERE id = {user_id}")!
```

Three functions, all named `email`, with completely different intents.

## Context-Aware Call Resolution

At call sites, you use **just the function name** — the compiler resolves which verb-variant to call based on context (expected type, parameter types, expression position):

```prove
// Boolean context (if) → resolves to validates email
if email(input)
    clean as Email = email(raw_input)    // Email context + String param → transforms
    stored as Email = email(user.id)     // Email context + Integer param → inputs

// When context is ambiguous, use `valid` for explicit Boolean cast
print(valid email(input))               // forces validates variant

// `valid` as type-cast parameter — passes the validates function itself
filter(users, valid email)              // passes `validates email` as predicate
```

Resolution rules:

1. **Boolean context** (`if`, `&&`, `||`, `!`) → resolves to `validates` variant
2. **Expected type** from assignment or parameter → matches the variant returning that type
3. **Parameter types** disambiguate between variants with the same return type
4. **Ambiguous** → compiler error with suggestions listing available variants

The `valid` keyword serves two purposes:

- **As expression**: `valid email(input)` — casts a validates call to its Boolean result explicitly
- **As function reference**: `valid email` (no parens) — passes the validates function as a predicate to higher-order functions like `filter`

Implications:

- **Imports are precise**: `with Auth use validates login, inputs session`
- **API docs group by verb**: what can you validate? what can you yield? what can you transform?
- **Call sites are clean**: just the function name in most cases
- **AI resistance**: declarations require the correct verb, and the resolution rules add non-local reasoning requirements

## Parameters

Go-style: `name Type` (no colon). Inside parentheses, the declaration context is already clear.

```prove
transforms area(s Shape) Decimal
inputs request(route Route, body String) Response!
validates email(address String)
```

## Variable Declarations

Variables use `name as Type = value`. The `as` keyword reads naturally: *"port, as a Port, equals 8080"*.

```prove
port as Port = 8080
server as Server = new_server()
config as Config = load("app.yaml")!
user_list as List<User> = users()!
```

Variables are **immutable by default**. Mutability is a type modifier — it's a storage concern, like size and signedness:

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

## IO and Fallibility

IO is inherent in the verb — `inputs` and `outputs` always interact with the external world. Fallibility is marked with `!` on the return type. Pure verbs (`transforms`, `validates`) have neither IO nor `!`.

```prove
transforms area(s Shape) Decimal                       // pure — no IO, no !
    from
        pi * s.radius * s.radius

inputs users() List<User>!                             // IO inherent, ! = can fail
    from
        query(db, "SELECT * FROM users")!

outputs write_log(entry String)                        // IO inherent, infallible — no !
    from
        append(log_file, entry)
```

Reads as: *"inputs users, returns List of User, can fail!"*

The compiler knows which functions touch the world (`inputs`/`outputs`) and which don't (`transforms`/`validates`) — the verb IS the declaration.

## Body Marker: `from`

Every function body begins with `from`. No exceptions. This reads as *"the result comes from..."* and makes it immediately clear where the implementation starts, whether the function has annotations or not.

```prove
// Simple function — from marks the body
transforms area(s Shape) Decimal
    from
        pi * s.radius * s.radius

// Annotated function — from separates annotations from body
inputs users() List<User>!
    ensures len(result) >= 0
    from
        query(db, "SELECT * FROM users")!
```

## Pattern Matching

Indentation-based, no braces:

```prove
match route
    Get("/health") => ok("healthy")
    Get("/users")  => users()!
    _              => not_found()

if connected
    send(data)
else
    retry()
```

## Lambdas — Constrained Inline Functions

Lambdas are single-expression anonymous functions, used exclusively as arguments to higher-order functions like `map`, `filter`, and `reduce`. They cannot capture mutable state and must be pure.

Syntax: `|params| expression`

```prove
// Filtering with a lambda
active_users as List<User> = filter(users, |u| u.active)

// Mapping with a lambda
names as List<String> = map(users, |u| u.name)

// Reducing with a lambda
total as Decimal = reduce(prices, 0, |acc, p| acc + p)

// Using `valid` to pass a validates function as predicate (no lambda needed)
verified_emails as List<String> = filter(emails, valid email)
```

**Constraints:**

- **Single expression only** — no multi-line bodies, no statements. If you need more, write a named function.
- **Must be pure** — no IO effects inside a lambda. Side effects require a named function.
- **No closures over mutable state** — lambdas can reference immutable bindings from the enclosing scope, but not `:[Mutable]` variables.
- **Only as arguments** — lambdas cannot be assigned to variables or returned from functions. They exist only at the call site of a higher-order function.

## Iteration — No Loops

Prove has no `for`, `while`, or loop constructs. Iteration is expressed through `map`, `filter`, `reduce`, and recursion. This keeps all data transformations as expressions (they produce values) rather than statements.

```prove
// Instead of: for each user, get their name
names as List<String> = map(users, |u| u.name)

// Instead of: for each item, keep valid ones
valid_items as List<Item> = filter(items, |i| i.quantity > 0)

// Instead of: accumulate a total with a loop
total as Decimal = reduce(order.items, 0, |acc, item| acc + item.price * item.quantity)

// Chaining with pipe operator
result as List<String> = users
    |> filter(|u| u.active)
    |> map(|u| u.email)
    |> filter(valid email)
```

For complex iteration that doesn't fit map/filter/reduce, use recursion with a `transforms` function. The compiler verifies termination through proof obligations.

## Keyword Exclusivity

Every keyword in Prove has exactly one purpose. No keyword is overloaded across different contexts. This makes the language predictable and parseable by humans without memorizing context-dependent rules.

### Core Keywords

| Keyword | Exclusive purpose |
|---------|-------------------|
| `transforms` | Verb — pure data computation/conversion |
| `inputs` | Verb — reads/receives from external world (implicit match when first param is algebraic) |
| `outputs` | Verb — writes/sends to external world |
| `validates` | Verb — pure boolean check |
| `main` | Entry point — no verb, the program itself. Only function that freely mixes inputs/outputs |
| `from` | Body marker — introduces function implementation |
| `where` | Refinement constraint — value predicates only |
| `as` | Variable declaration — `name as Type = value` |
| `!` | Fallibility — on declaration: can fail. At call site: propagate failure. IO verbs only |
| `with` | Import — `with Module use function` |
| `type` | Type definition — `type Name is ...` |
| `is` | Type body — follows `type Name` |
| `match` | Pattern matching expression |
| `if`/`else` | Conditional expression |
| `ensures` | Postcondition contract |
| `requires` | Precondition contract |
| `proof` | Proof obligation block |
| `valid` | Predicate reference for validates functions |
| `comptime` | Compile-time computation |

### AI-Resistance Keywords (Phase 1+2)

| Keyword | Exclusive purpose |
|---------|-------------------|
| `domain` | Domain declaration — context-dependent syntax |
| `intent` | Intentional ambiguity resolution |
| `narrative` | Module coherence requirement |
| `why_not` | Counterfactual annotation — rejected alternatives |
| `chosen` | Counterfactual annotation — selected rationale |
| `near_miss` | Adversarial boundary example |
| `know` | Epistemic — proven by type system (zero cost) |
| `assume` | Epistemic — runtime validated at boundaries |
| `believe` | Epistemic — compiler generates adversarial tests |
| `temporal` | Temporal effect ordering constraint |
| `satisfies` | Invariant network conformance |
| `invariant_network` | Invariant network declaration |

## Error Propagation

`!` marks fallibility — on declarations it means "this function can fail", at call sites it propagates the error. Only IO verbs (`inputs`, `outputs`) can use `!`. Pure functions encode failure in the return type (`Result<T, E>`) and handle it with `match`.

```prove
main() Result<Unit, Error>!
    from
        config as Config = load("app.yaml")!
        db as Database = connect(config.db_url)!
        serve(config.port, db)!
```

## Complete Example: RESTful Server

```prove
type Port is Integer:[16 Unsigned] where 1..65535
type Route is Get(path String) | Post(path String) | Delete(path String)

type User is
    id Integer
    name String
    email String

/// Checks whether a string is a valid email address.
validates email(address String)
    from
        contains(address, "@") && contains(address, ".")

/// Retrieves all users from the database.
inputs users(db Database) List<User>!
    from
        query(db, "SELECT * FROM users")!

/// Creates a new user from a request body.
outputs create(db Database, body String) User!
    ensures email(result.email)
    proof
        email_valid: decode validates the email field before insertion
    from
        user as User = decode(body)!
        insert(db, "users", user)!
        user

/// Routes incoming HTTP requests.
inputs request(route Route, body String, db Database) Response!
    from
        Get("/health") => ok("healthy")
        Get("/users")  => users(db)! |> encode |> ok
        Post("/users") => create(db, body)! |> encode |> created
        _              => not_found()

/// Application entry point — no verb, main is special.
main() Result<Unit, Error>!
    from
        port as Port = 8080
        db as Database = connect("postgres://localhost/app")!
        server as Server = new_server()
        route(server, "/", request)
        listen(server, port)!
```
