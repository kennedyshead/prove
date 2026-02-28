# Prove Language Specification

> **A programming language that fights back against AI slop and code scraping.**

Prove is a strongly typed, compiler-driven language where contracts generate tests, intent verbs enforce purity, and the compiler rejects code that can't demonstrate understanding. Source is stored as binary AST — unscrapable, unnormalizable, unlicensed for training. If it compiles, the author understood what they wrote. If it's AI-generated, it won't.

## Philosophy

The compiler is your co-author, not your gatekeeper.

Every feature exists to move correctness checks from runtime to compile time, and to generate tests from the code you already write. Most bugs are type errors in disguise — give the type system enough power and they become almost impossible.

---

## Implementation Decisions

### File Extension: `.prv`

Investigated `.pv`, `.prove`, `.prf`, `.pr`, and `.prv`. Chosen: **`.prv`** — short, reads naturally as "Prove", and has no conflicts with existing programming languages or developer tooling.

| Rejected | Reason |
|----------|--------|
| `.pv` | Taken by **ProVerif** (formal methods — same domain, high confusion risk) |
| `.prove` | Taken by **Perl's `prove`** test harness (well-known in dev tooling) |
| `.prf` | Taken by **MS Outlook** profiles and **Qt** feature files |
| `.pr` | Legacy Source Insight 3, but "PR" universally means "pull request" |

### Prototype Implementation: Python

The compiler POC is implemented in Python (>=3.11). The goal is to validate the language design and prove out the compilation pipeline before rewriting in a systems language.

### Compilation Target: Native Code

As close to the CPU as possible. The compiler does the heavy lifting at compile time so the output is fast and memory-efficient. Target: native code via direct assembly emission (x86_64 + ARM64). No VM, no interpreter for production output.

### First POC: Self-Hosting Compiler

The first program written in Prove will be the Prove compiler itself. The bootstrap path: (1) write a complete compiler in Python, (2) use it to compile a Prove compiler written in Prove. This exercises the type system (AST node types, token variants), verb system (transforms for pure passes, inputs for file reading, outputs for code emission), pattern matching (exhaustive over AST nodes), and algebraic types — proving the language works by compiling itself. Self-hosting is the strongest possible validation: if Prove can express its own compiler, it can express anything.

### AI-Resistance: Fundamental

AI-resistance features (proof obligations, intent declarations, narrative coherence, context-dependent syntax, semantic commits) are **mandatory and fundamental to the language identity**, not optional extras. Proof obligations are required for every function that has `ensures` clauses — if you declare what a function guarantees, you must prove why.

### Comptime: IO Allowed

Compile-time computation (`comptime`) allows IO operations. This enables reading config files, schema definitions, and static assets at compile time. Files accessed during comptime become build dependencies — changing them triggers recompilation. This may be revisited if reproducibility concerns arise.

### CLI-First Toolchain: `prove`

The `prove` CLI is the central interface for all development:

```
prove build          # compile the project
prove test           # run auto-generated + manual tests
prove check          # type-check without building
prove format         # auto-format source code
prove lsp            # start the language server
prove build --mutate # run mutation testing
prove new <name>     # scaffold a new project
```

### Syntax Philosophy

No shorthands. No abbreviations. Full words everywhere. The language reads like English prose where possible. Since it is inherently a hard-to-learn language (refinement types, proof obligations, effect tracking), **simplicity is maximized wherever possible**. If something can be simple, it must be. The compiler works for the programmer, not the other way around.

### Secondary Priorities (Deferred)

- **C FFI** — important but not day-one. Will be addressed after the core language is stable.
- **Calling Prove from other languages** — deferred until the FFI story is established.
- **Method syntax** — deferred. All function calls use `function(args)` form. No `object.method()` dot-call syntax. Keeps the language simple and avoids dispatch complexity. Field access (`user.name`) is unaffected.

---

## Syntax Conventions

### Naming

- **Types, modules, and classes**: CamelCase — `Shape`, `Port`, `UserAuth`, `NonEmpty`, `HttpServer`
- **Variables and parameters**: snake_case — `port`, `user_list`, `max_retries`, `db_connection`
- **Functions**: snake_case — `area`, `binary_search`, `get_users`
- **Constants**: UPPER_SNAKE_CASE — `MAX_CONNECTIONS`, `LOOKUP_TABLE`, `DEFAULT_PORT`
- **Effects**: CamelCase — `IO`, `Fail`, `Async`

The compiler **enforces** casing. Wrong case is a compile error, not a warning. UPPER_SNAKE_CASE indicates a compile-time constant — no `const` keyword needed.

### Modules and Imports

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

A verb applies to all space-separated names that follow it. Commas separate verb groups. Multiple verbs for the same function name import each variant. The verb is part of the function's identity.

### Blocks and Indentation

No curly braces. Indentation defines scope (like Python). No semicolons — newlines terminate statements. Newlines are suppressed after operators, commas, opening brackets, `->`, `=>`.

### Primitive Types — Full Names, No Shorthands

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

### Type Definitions

Types live inside the `module` block, defined with `type Name is`:

```prove
module Main
  type Shape is
    Circle(radius Decimal)
    | Rect(w Decimal, h Decimal)

  type Port is Integer:[16 Unsigned] where 1 .. 65535

  type Result<T, E> is Ok(T) | Err(E)

  type User is
    id Integer
    name String
    email String
```

### Function Declarations — Intent Verbs

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
        Get(/health) => ok("healthy")
        Get(/users) => users()! |> ok
        Post(/users) => create(req.body)! |> created
        _ => not_found()
```

### Verb-Dispatched Identity

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

### Context-Aware Call Resolution

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

### Parameters

Go-style: `name Type` (no colon). Inside parentheses, the declaration context is already clear.

```prove
transforms area(s Shape) Decimal
inputs request(route Route, body String) Response!
validates email(address String)
```

### Variable Declarations

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

### Type Inference with Formatter Enforcement

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

### IO and Fallibility

IO is inherent in the verb — `inputs` and `outputs` always interact with the external world. Fallibility is marked with `!` on the return type. Pure verbs (`transforms`, `validates`) have neither IO nor `!`.

```prove
transforms area(s Shape) Decimal
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

The compiler knows which functions touch the world (`inputs`/`outputs`) and which don't (`transforms`/`validates`) — the verb IS the declaration.

### Body Marker: `from`

Every function body begins with `from`. No exceptions. This reads as *"the result comes from..."* and makes it immediately clear where the implementation starts, whether the function has annotations or not.

```prove
transforms area(s Shape) Decimal
from
    pi * s.radius * s.radius

inputs users() List<User>!
  ensures len(result) >= 0
from
    query(db, "SELECT * FROM users")!
```

### Pattern Matching

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

### Lambdas — Constrained Inline Functions

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

### Iteration — No Loops

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

### Keyword Exclusivity

Every keyword in Prove has exactly one purpose. No keyword is overloaded across different contexts. This makes the language predictable and parseable by humans without memorizing context-dependent rules.

**Core keywords:**

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

**AI-Resistance keywords (Phase 1+2):**

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

### Error Propagation

`!` marks fallibility — on declarations it means "this function can fail", at call sites it propagates the error. Only IO verbs (`inputs`, `outputs`) can use `!`. Pure functions encode failure in the return type (`Result<T, E>`) and handle it with `match`.

```prove
main() Result<Unit, Error>!
from
    config as Config = load("app.yaml")!
    db as Database = connect(config.db_url)!
    serve(config.port, db)!
```

### Complete Example: RESTful Server

```prove
type Port is Integer:[16 Unsigned] where 1 .. 65535
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

---

## Type System

### Refinement Types

Types carry constraints, not just shapes. The compiler rejects invalid values statically — no unnecessary runtime checks, no `unwrap()`.

```prove
type Port is Integer:[16 Unsigned] where 1 .. 65535
type Email is String where matches(/^[^@]+@[^@]+\.[^@]+$/)
type NonEmpty<T> is List<T> where len > 0

transforms head(xs NonEmpty<T>) T    // no Option needed, emptiness is impossible
```

The compiler rejects `head([])` statically.

### Algebraic Types with Exhaustive Matching

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

### Effect Types

IO is encoded in the verb, not in annotations. The compiler knows which functions touch the world (`inputs`/`outputs`) and which are pure (`transforms`/`validates`). Pure functions get automatic memoization and parallelism.

```prove
inputs read_config(path Path) String!               // IO inherent, ! = can fail

transforms parse(s String) Result<Config, Error>   // pure — failure in return type

transforms rewrite(c Config) Config                // pure, infallible, parallelizable
```

### Ownership Lite (Linear Types with Compiler-Inferred Borrows)

Linear types for resources, but without Rust's lifetime annotation burden. The compiler infers borrows or asks you. Ownership is a type modifier, consistent with mutability and other storage concerns.

```prove
inputs process(file File:[Own]) Data!
from
    content as String = read(file)
    close(file)
```

### No Null

No null — use `Option<T>`, enforced by the compiler.

---

## Compiler-Driven Development

### Conversational Compiler Errors

Errors are suggestions, not walls:

```
error[E042]: `port` may exceed type bound
  --> server.prv:12:5
   |
12 |   port as Port = get_integer(config, "port")
   |                   ^^^^^^^^^^^^^^^^^^^^^^^^^^^^
   = note: `get_integer` returns Integer, but Port requires 1..65535

   try: port as Port = clamp(get_integer(config, "port"), 1, 65535)
    or: port as Port = check(get_integer(config, "port"))!
```

### Comptime (Compile-Time Computation)

Inspired by Zig. Arbitrary computation at compile time, including IO. Files read during comptime become build dependencies.

```prove
MAX_CONNECTIONS as Integer = comptime
  if cfg.target == "embedded"
    16
  else
    1024

LOOKUP_TABLE as List<Integer:[32 Unsigned]> = comptime
  collect(map(0..256, crc32_step))

ROUTES as List<Route> = comptime
  decode(read("routes.json"))                   // IO allowed — routes.json becomes a build dep
```

### Formal Verification of Contracts

The compiler proves properties when it can, and generates tests when it can't:

```prove
transforms binary_search(xs Sorted<List<Integer>>, target Integer) Option<Index>
  ensures is_some(result) implies xs[unwrap(result)] == target
  ensures is_none(result) implies target not_in xs
```

### Contracts by Example — Why This Matters

Prove's contract system is not syntactic sugar for assertions. It is a fundamentally different relationship between programmer intent and compiler enforcement. To see why, compare the same function — `calculate_total` — across four languages.

#### Prove

```prove
transforms calculate_total(items List<OrderItem>, discount Discount, tax TaxRule) Price
  ensures result >= 0
  requires len(items) > 0
  proof
    subtotal: sums the items Price
    apply_discount: deduct discount if > 0
    apply_tax: adds tax if tax > 0
from
    sub as Price = subtotal(items)
    discounted as Price = apply_discount(discount, sub)
    apply_tax(tax, discounted)
```

Three things happen at compile time:

- **`requires`** — The compiler rejects any call site that cannot prove `len(items) > 0`. This is not a runtime check. If your list might be empty, the code does not compile.
- **`ensures`** — The compiler verifies that every code path produces `result >= 0`. If it cannot prove this statically, it generates property tests that exercise thousands of inputs.
- **`proof`** — The programmer explains *why* the postconditions hold. The compiler uses these proof hints to guide its verification. If the proof is wrong, the compiler says so.

All three are mandatory. You cannot ship a function without declaring what it requires and what it guarantees.

#### Python

```python
def calculate_total(items: list[OrderItem], discount: Discount, tax: TaxRule) -> Price:
    """Calculate order total after discount and tax.

    Args:
        items: must be non-empty
        discount: discount to apply
        tax: tax rule to apply

    Returns:
        total price, always >= 0
    """
    assert len(items) > 0  # only checked if -O is not set
    sub = subtotal(items)
    discounted = apply_discount(discount, sub)
    result = apply_tax(tax, discounted)
    assert result >= 0  # also stripped by -O
    return result
```

- **Preconditions** — `assert` statements, stripped by `python -O`. The type hint `list[OrderItem]` says nothing about length. An empty list passes type checking and reaches runtime.
- **Postconditions** — Another `assert`, also stripped in production. The docstring says "always >= 0" but nothing enforces it.
- **Proof** — Does not exist. The docstring is a comment. Tests are a separate file written by a separate person at a separate time.

#### Haskell

```haskell
calculateTotal :: NonEmpty OrderItem -> Discount -> TaxRule -> Price
-- | Precondition: items is non-empty (enforced by NonEmpty type)
-- | Postcondition: result >= 0 (NOT enforced — Price is just a newtype)
calculateTotal items discount tax =
  let sub = subtotal (toList items)
      discounted = applyDiscount discount sub
  in applyTax tax discounted
```

- **Preconditions** — `NonEmpty` enforces non-emptiness at the type level. This is genuinely good. But most preconditions ("discount is valid", "tax rate is between 0 and 1") require dependent types that Haskell does not have.
- **Postconditions** — Comments. The type `Price` does not carry the invariant `>= 0` unless you build a custom smart constructor, and even then the compiler does not verify that `applyTax` preserves it.
- **Proof** — Does not exist in the language. QuickCheck can test properties, but it is a library, it is opt-in, and the properties are written in test files separate from the function.

#### Rust

```rust
fn calculate_total(items: &[OrderItem], discount: &Discount, tax: &TaxRule) -> Price {
    debug_assert!(!items.is_empty(), "items must be non-empty");
    let sub = subtotal(items);
    let discounted = apply_discount(discount, sub);
    let result = apply_tax(tax, discounted);
    debug_assert!(result >= Price::ZERO, "result must be non-negative");
    result
}
```

- **Preconditions** — `debug_assert!`, compiled out in release builds. The slice type `&[OrderItem]` permits empty slices. A `NonEmpty` wrapper exists in crates but is not standard.
- **Postconditions** — Another `debug_assert!`, also absent in release. The type system enforces memory safety but says nothing about business logic invariants.
- **Proof** — Does not exist. Tests are in a `#[cfg(test)]` module. Property testing requires `proptest` or `quickcheck` crates, and properties are written manually in test files.

#### Summary

| Capability | Prove | Python | Haskell | Rust |
|---|---|---|---|---|
| **Preconditions** | `requires` — compile-time enforced | `assert` — runtime, strippable | Types cover some; rest are comments | `debug_assert!` — stripped in release |
| **Postconditions** | `ensures` — compiler-verified or auto-tested | `assert` — runtime, strippable | Comments or smart constructors (manual) | `debug_assert!` — stripped in release |
| **Proof of correctness** | `proof` — checked by compiler | Does not exist | Does not exist | Does not exist |
| **Test generation** | Automatic from contracts | Manual (pytest, hypothesis) | Manual (QuickCheck) | Manual (proptest) |
| **Contracts are...** | Mandatory, part of the function signature | Optional, easily ignored | Convention, not enforced | Convention, not enforced |

The gap is not about syntax. Python, Haskell, and Rust all have *mechanisms* for expressing some of these ideas. The difference is that in Prove, contracts are **mandatory**, **compiler-enforced**, and **self-testing**. You cannot write a function that silently ignores its own guarantees.

---

## Auto-Testing

Testing is not a separate activity. It is woven into the language — contracts are mandatory and the compiler enforces them.

### Level 1: Contracts Generate Property Tests

No test file needed. No QuickCheck boilerplate. The compiler generates thousands of random inputs and verifies all postconditions hold. Contracts are mandatory — every function declares what it guarantees.

```prove
transforms sort(xs List<T>) List<T>
  ensures len(result) == len(xs)
  ensures is_sorted(result)
  ensures is_permutation_of(result, xs)
from
    // implementation
```

### Level 2: Automatic Edge-Case Generation

Given the type signature alone, the compiler knows to test boundary values and heuristic edge cases:

```prove
transforms divide(a Integer, b NonZero<Integer>) Integer
// Auto-generated test inputs: (0, 1), (1, 1), (-1, 1), (MAX_INT, 1),
// (MIN_INT, -1), (7, 3), ...
// Derived from type bounds + heuristic edge-case generation
```

For refinement types, boundary testing is automatic:

```prove
transforms set_port(p Port) Config    // Port = 1..65535
// Auto-tests: 1, 2, 65534, 65535, and random values between
// Also verifies that 0 and 65536 are rejected at the call site
```

### Level 4: Built-in Mutation Testing

```
$ prove build --mutate

Mutation score: 97.2% (347/357 mutants killed)
Surviving mutants:
  src/cache.prv:45  — changed `>=` to `>` (boundary condition not covered)
  src/cache.prv:82  — removed `+ 1` (off-by-one not detected)

  Suggested contract to add:
    ensures len(cache) <= max_size   // would kill both mutants
```

---

## Concurrency — Structured, Typed, No Data Races

```prove
inputs fetch_all(urls List<Url>) List<Response>!
from
    par_map(urls, fetch)
```

The ownership system and effect types combine to eliminate data races at compile time.

---

## Error Handling — Errors Are Values

No exceptions. Every failure path is visible in the type signature. Uses `!` for error propagation. Panics exist only for violated `assume:` assertions at system boundaries — normal error handling is always through `Result` values.

```prove
main() Result<Unit, Error>!
from
    config as Config = read_config("app.yaml")!
    db as Database = connect(config.db_url)!
    serve(config.port, db)!
```

---

## Zero-Cost Abstractions

- Pure functions auto-memoized and inlined
- Region-based memory for short-lived allocations
- Reference counting only where ownership is shared (compiler-inserted)
- No GC pauses, predictable performance
- Native code output

---

## Pain Point Comparison

| Pain in existing languages | How Prove solves it |
|---|---|
| Tests are separate from code | Testing is part of the definition — `ensures`, `requires`, `near_miss` |
| "Works on my machine" | Verb system makes IO explicit (`inputs`/`outputs`) |
| Null/nil crashes | No null — use `Option<T>`, enforced by compiler |
| Race conditions | Ownership + verb system prevents data races |
| "I forgot an edge case" | Compiler generates edge cases from types |
| Slow test suites | Property tests run at compile time when provable |
| Runtime type errors | Refinement types catch invalid values at compile time |

---

## AI-Resistance Phase 1 — Generation Resistance

AI models generate code by pattern-matching on statistical regularities in training data. To resist AI generation, a language needs correctness to require deep, holistic understanding — local patterns alone are insufficient.

### Context-Dependent Syntax

Instead of fixed keywords, the language adapts syntax based on the module's declared domain. AI cannot memorize syntax because it shifts per-context.

```prove
domain Finance
  // "balance" is now a keyword, arithmetic operators
  // follow financial rounding rules
  total as Balance = sum(ledger.entries)  // compiler enforces Decimal with financial Scale

domain Physics
  // "balance" is just an identifier again
  // operators now track units
  balance as Acceleration = force / mass   // type: Acceleration, not a keyword
```

### Proof Obligations as Code

Every function with `ensures` clauses requires an inline proof sketch that the compiler verifies. No ensures, no proof needed — the rule is clear and mechanical. AI can generate plausible-looking proofs, but they won't verify — you need to actually understand why the code is correct.

```prove
transforms merge_sort(xs List<T>) Sorted<List<T>>
  proof
    base: len(xs) <= 1 implies already sorted
    split: halves are strictly smaller (terminates)
    merge: merging two sorted halves preserves ordering
           by induction on combined length
from
    // implementation
```

### Intentional Ambiguity Resolution

Constructs that are deliberately ambiguous without understanding intent. The `intent` string is parsed by the compiler using a formal semantics model and must match the code's behavior.

```prove
// Does this filter IN or filter OUT? Depends on the declared intent.
intent: "keep only valid records"
result as List<Record> = filter(records, valid record)

intent: "remove corrupt entries"
result as List<Record> = filter(records, valid corrupt)
// Same filter() call, but the compiler checks that the intent
// matches the predicate's semantics (keep vs discard)
```

### Non-Local Coherence Requirements

The compiler enforces that an entire module tells a coherent "story." Functions unrelated to the narrative produce compile errors.

```prove
module UserAuth
  narrative: """
  Users authenticate with credentials, receive a session token,
  and the token is validated on each request. Tokens expire
  after the configured TTL.
  """

  inputs login(creds Credentials) Session!
  transforms validate(token Token) User
  outputs expire(session Session)
  // outputs send_email(...)   // compiler error: unrelated to narrative
```

Coherence across an entire module requires understanding the *purpose* of the system, not just local patterns.

### Adversarial Type Puzzles

Refinement types that encode constraints requiring genuine reasoning, not just pattern matching:

```prove
type BalancedTree<T> is
  Node(left BalancedTree<T>, right BalancedTree<T>)
  where abs(left.depth - right.depth) <= 1

transforms insert(tree BalancedTree<T>, val T) BalancedTree<T>
  // Can't just pattern match — you need to construct a value
  // that satisfies the depth constraint, which requires
  // understanding rotation logic
```

### Semantic Commit Messages as Compilation Input

The compiler diffs the previous version, reads the commit message, and verifies the change actually addresses the described bug.

```prove
commit "fix: off-by-one in pagination — last page was empty
       when total % page_size == 0"

// The compiler diffs the previous version, reads the commit message,
// and verifies the change actually addresses the described bug.
// Vague messages like "fix stuff" don't compile.
```

---

## AI-Resistance Phase 2 — Advanced Generation Resistance

Phase 2 targets deeper failure modes in AI code generation: the inability to reason about alternatives, uncertainty, temporal ordering, and interconnected constraints.

### Counterfactual Annotations

Every non-trivial design choice must explain what would break under alternative approaches. AI cannot reason about paths not taken.

```prove
transforms evict(cache Cache:[Mutable]) Option<Entry>
  why_not: "FIFO would evict still-hot entries under burst traffic"
  why_not: "Random eviction has unbounded worst-case for repeated keys"
  chosen: "LRU because access recency correlates with reuse probability"
from
    // LRU implementation
```

The compiler verifies the `chosen` rationale is consistent with the implementation's actual behavior (e.g., it really does track recency). `why_not` clauses are checked for plausibility against the function's type signature and effects.

### Adversarial Near-Miss Examples

Require inputs that *almost* break the code but don't. This proves the programmer understands the exact boundary between correct and incorrect behavior.

```prove
validates leap_year(y Year)
  near_miss: 1900  => false
  near_miss: 2000  => true
  near_miss: 2100  => false
from
    y % 4 == 0 && (y % 100 != 0 || y % 400 == 0)
```

The compiler verifies each near-miss actually exercises a distinct branch or boundary condition. Redundant near-misses are rejected. AI can memorize correct implementations but cannot identify the *diagnostic* inputs that prove understanding.

### Epistemic Annotations — `know` vs `assume` vs `believe`

Track the programmer's confidence level about invariants. The compiler treats each tier differently.

```prove
transforms process_order(order Order) Receipt
  know: len(order.items) > 0            // enforced by NonEmpty type — zero cost
  assume: order.total == sum(prices)    // validated at boundary, runtime check inserted
  believe: order.user.is_verified       // generates aggressive property tests to falsify
from
    // implementation
```

- **`know`** — Proven by the type system. Zero runtime cost. Compiler error if not actually provable.
- **`assume`** — Compiler inserts runtime validation at system boundaries. Logged when violated.
- **`believe`** — Compiler generates adversarial test cases specifically targeting this claim.

AI has no model of its own uncertainty — it would either mark everything `know` (fails verification) or `assume` (wasteful and reveals lack of understanding).

### Temporal Effect Ordering

Not just *what* effects a function has, but the *required order* — enforced across function boundaries and call graphs.

```prove
module Auth
  temporal: authenticate -> authorize -> access

  inputs authenticate(creds Credentials) Token!
  transforms authorize(token Token, resource Resource) Permission
  inputs access(perm Permission, resource Resource) Data!

// Compiler error: access() called before authorize()
inputs bad_handler(req Request) Response!
from
    token as Token = authenticate(req.creds)!
    data as Data = access(token, req.resource)!    // ERROR: skipped authorize
```

The compiler builds a call graph and verifies temporal constraints are satisfied across all execution paths. AI generates plausible call sequences but does not reason about protocol ordering.

### Invariant Networks

Instead of isolated `ensures` clauses, define networks of mutually-dependent invariants. Changing one cascades verification across the entire network.

```prove
invariant_network AccountingRules
  total_assets == total_liabilities + equity
  revenue - expenses == net_income
  net_income flows_to equity
  every(transaction) preserves total_assets == total_liabilities + equity

transforms post_transaction(ledger Ledger, tx Transaction) Ledger
  satisfies AccountingRules
from
    // implementation
```

No function can be written in isolation — the compiler checks that the entire network remains consistent after every change. This is the ultimate non-local reasoning requirement. Requires a constraint solver that scales across modules.

### Refutation Challenges

The compiler deliberately generates plausible-but-wrong alternative implementations and requires the programmer to explain why they fail. Compilation becomes a dialogue.

```
$ prove check src/sort.prv

challenge[C017]: Why doesn't this simpler implementation work?

  transforms sort(xs List<Integer>) Sorted<List<Integer>>
      reverse(dedup(xs))     // appears sorted for some inputs

  refute: _______________

  hint: Consider [3, 1, 2]
```

The programmer must provide a counterexample or logical argument. The compiler verifies the refutation is valid. This ensures the programmer understands not just *what* works, but *why alternatives don't*.

---

## AI-Resistance Phase 3 — Anti-Training

Phase 1 and 2 make it hard for AI to *generate* correct Prove code. Phase 3 goes further: making Prove source code **resistant to being useful as AI training data**. Even if scraped, Prove codebases should yield minimal learnable signal.

AI training pipelines assume: (1) source code is plain text, (2) syntax is consistent across projects, (3) individual files are self-contained enough to learn from, and (4) surface patterns correlate with semantics. Prove attacks all four assumptions.

### Project-Specific Grammars

Each project can define syntactic extensions via its `prove.toml` manifest. Two Prove projects may look completely different at the surface level. Training data cannot generalize across projects.

```prove
// prove.toml
[syntax]
pipe_operator = "|>"
match_arrow = "=>"

// Another project's prove.toml
[syntax]
pipe_operator = ">>"
match_arrow = "->"
```

```prove
// Project A
result as List<Data> = data |> filter(valid record) |> map(transform)

// Project B — same semantics, different surface
result as List<Data> = data >> filter(valid record) >> map(transform)
```

The compiler normalizes all syntax variants to the same AST. Scrapers see inconsistent syntax; the compiler sees identical programs. This destroys the statistical regularities that AI training depends on.

### Structured Source Format (`.prv` is not plain text)

`.prv` files are stored as a compact binary AST, not human-readable text. The `prove` CLI provides views:

```
$ prove view src/server.prv              # pretty-print to terminal
$ prove view src/server.prv --raw        # show the binary structure
$ prove edit src/server.prv              # open in editor with LSP decoding
$ prove export src/server.prv --text     # one-time text export
```

The editor experience is seamless — the language server decodes `.prv` on the fly, and the formatter writes binary back. But web scrapers, GitHub raw views, and training pipelines see binary blobs, not parseable source code.

**Why this works:** Every major AI training pipeline (The Stack, StarCoder, etc.) filters for text files and parses by file extension. Binary files are discarded. Prove code is invisible to these pipelines by default.

The `prove export --text` command exists for code review, diffs, and human sharing — but text is a *view*, not the source of truth.

### Semantic Normalization (Surface Patterns Destroyed)

The compiler canonicalizes all code before storage. Variable names, ordering of declarations, whitespace, and stylistic choices are normalized away. What the programmer writes is not what is stored.

```prove
// What you write:
transforms calculate_total_price(items List<Item>, tax TaxRate) Price
from
    subtotal as Decimal = sum(prices(items))
    subtotal * (1 + tax.rate)

// What is stored (canonical form):
transforms _f0(_a0 List<_T0>, _a1 _T1) _T2
from
    _v0 as _T3 = _f1(_f2(_a0))
    _v0 * (1 + _a1._f3)

// What you see (reconstructed with your naming via the LSP):
transforms calculate_total_price(items List<Item>, tax TaxRate) Price
from
    subtotal as Decimal = sum(prices(items))
    subtotal * (1 + tax.rate)
```

A **name map** is stored alongside the canonical AST. The LSP reconstructs human-readable code on demand. But the stored form strips all semantic signal from identifiers — AI cannot learn naming conventions, domain patterns, or stylistic habits from Prove source.

### Fragmented Source (No File Is Self-Contained)

A function's complete definition is distributed across multiple sections that only make sense together:

```
src/
  server.prv          # implementation (canonical binary AST)
  server.proof        # proof obligations for server.prv
  server.intent       # intent declarations
  server.near_miss    # adversarial near-miss examples
  server.narrative    # module narrative
```

A scraper that grabs `server.prv` alone gets a canonical binary AST with no variable names, no comments, no documentation, and no proofs. The proof file without the implementation is meaningless. The intent file without both is noise.

**All five files are required to compile.** The compiler assembles the complete picture. No single artifact is useful in isolation.

### Identity-Bound Compilation

Source files carry a cryptographic signature chain. The compiler verifies authorship.

```prove
// Embedded in .prv binary header
[signature]
author = "alice@example.com"
key_fingerprint = "A1B2C3..."
signed_at = 2026-02-27T14:30:00Z
chain = ["alice@example.com", "bob@example.com"]  // co-authors
```

- Unsigned code triggers a compiler warning (or error in strict mode).
- The signature chain tracks who wrote and reviewed each function.
- Scraped code with stripped signatures won't compile.
- The compiler can optionally refuse to build code signed by unknown keys.

This isn't DRM — it's **provenance**. The programmer can always export and re-sign. But mass scraping destroys the signature chain, making the code uncompilable.

### Anti-Training License as Default

Every `prove new` project is initialized with the **Prove Source License v1.0** (see `LICENSE`). It is a permissive MIT-style license with comprehensive AI restrictions covering:

- **Training, fine-tuning, and distillation** (Section 3.1)
- **Dataset inclusion, vector stores, RAG indices, and embedding databases** (Section 3.2)
- **Synthetic data generation** from the Software (Section 3.3)
- **Sublicensing for AI use** — third parties cannot be granted AI rights (Section 3.4)
- **Downstream propagation** — all redistributors must carry the restrictions forward (Section 3.5)
- **Technical protection circumvention** — bypassing binary format, normalization, or signatures for AI training is a breach (Section 4)

The license explicitly permits using AI tools *to write* Prove code and building AI-powered applications *with* Prove — it only prohibits using Prove source *as training data*.

Design draws from: NON-AI-MIT (base structure), Common Paper (precise LLM language), Authors Guild (sublicensing prohibition), Open RAIL-S (downstream propagation). Should be reviewed by legal counsel before production use.

This is not just a legal barrier — combined with the binary format and semantic normalization, it creates a layered defense: the code is hard to scrape, useless if scraped, and illegal to train on.

---

## The Fundamental Tension

Every feature that makes code harder for AI also makes it harder for humans.

The AI-resistance features force the programmer to:

- **Explain their reasoning** (proofs, intents, narratives, counterfactuals)
- **Maintain global coherence** (not just local correctness)
- **Understand *why*, not just *what*** (near-misses, refutation challenges)
- **Acknowledge uncertainty** (epistemic annotations)
- **Respect temporal protocols** (effect ordering)

The uncomfortable truth is that the things AI is bad at are the things lazy humans skip too. A language that resists AI would also resist copy-paste programming, cargo-culting Stack Overflow, and coding without understanding.

The anti-training features (binary format, semantic normalization, fragmented source) add friction to sharing and collaboration. The mitigation is a first-class toolchain: the `prove` CLI and LSP make the experience seamless for developers working inside the ecosystem, while making the code opaque to anything outside it.

**The design answers both questions:** Prove resists AI *writing* the code (Phase 1 + 2) and resists AI *training on* the code (Phase 3).

---

## Trade-offs

An honest assessment of the costs:

1. **Compilation speed** — Proving properties is expensive. Incremental compilation and caching are essential. Expect Rust-like compile times, not Go-like.
2. **Learning curve** — Refinement types and effect types are unfamiliar to most developers. The compiler's suggestions help, but there's still a ramp-up.
3. **Ecosystem bootstrap** — A new language needs libraries. A C FFI and a story for wrapping existing libraries is a secondary priority, deferred until the core language is stable.
4. **Not every property is provable** — For complex invariants the compiler falls back to runtime property tests, which is still better than nothing but not a proof.

**The core bet:** Making the compiler do more work upfront saves orders of magnitude more time than writing and maintaining tests by hand.

---

## Design Inspirations

| Language | What Prove borrows | What Prove avoids |
|---|---|---|
| **Rust** | Ownership model, exhaustive matching, no null | Lifetime annotation burden, borrow checker complexity |
| **Haskell** | Type system, pure functions, algebraic types | IO monad complexity, lazy evaluation surprises |
| **Go** | Parameter syntax (`name Type`), simplicity as goal | Weak type system, error handling verbosity |
| **Python** | Indentation-based blocks, readability philosophy | Dynamic typing, runtime errors |
| **Zig** | `comptime` (compile-time computation with IO) | Manual memory management |
| **Ada/SPARK** | Contract-based programming, formal verification | Verbose syntax |
| **Idris/Agda** | Dependent types for encoding invariants | Academic accessibility barrier |
| **Elm** | Eliminating runtime exceptions, compiler as assistant | Limited to frontend |
| **F#** | Pragmatic algebraic types, pipeline operator | — |
