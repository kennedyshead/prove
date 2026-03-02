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

## Foreign Blocks (C FFI)

Modules can declare `foreign` blocks to bind C functions. Each block names a C library and lists the functions it provides. Foreign functions are raw C bindings — wrap them in a Prove function with a verb to provide type safety and contracts:

```prove
module Math
  narrative: """Mathematical functions via C libm."""

  foreign "libm"
    c_sqrt(x Decimal) Decimal
    c_sin(x Decimal) Decimal

transforms sqrt(x Decimal) Decimal
  ensures result >= 0.0
  requires x >= 0.0
  explain
    delegate to C sqrt
from
    c_sqrt(x)
```

The string after `foreign` is the library name passed to the linker (`"libm"` links `-lm`). Known libraries get automatic `#include` headers (`libm` → `math.h`, `libpthread` → `pthread.h`).

Configure additional compiler and linker flags in `prove.toml`:

```toml
[build]
c_flags = ["-I/usr/local/include"]
link_flags = ["-L/usr/local/lib", "-lm"]
```

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

## Function Declarations — Intent Verbs

Functions are declared with a **verb** that describes their purpose. No `fn`, no `function` keyword — the verb IS the declaration. The compiler verifies the implementation matches the declared intent.

Verbs are divided into two families: **pure** (no side effects) and **IO** (interacts with the outside world).

**Pure verbs:**

| Verb | Purpose | Compiler enforces |
|------|---------|-------------------|
| `transforms` | Pure data computation/conversion | No `!`. Failure encoded in return type (`Result`, `Option`) |
| `validates` | Pure boolean check | No `!`. Return type is implicitly `Boolean` |
| `reads` | Non-mutating access to data | No `!`. Extracts or queries without changing anything |
| `creates` | Constructs a new value | No `!`. Returns a freshly allocated value |
| `matches` | Pure match dispatch on algebraic type | No `!`. First parameter must be algebraic. `from` block is implicitly a match — no `match x` needed |

**IO verbs:**

| Verb | Purpose | Compiler enforces |
|------|---------|-------------------|
| `inputs` | Reads/receives from external world | IO is inherent. `!` marks fallibility. Implicit match when first param is algebraic |
| `outputs` | Writes/sends to external world | IO is inherent. `!` marks fallibility |

```prove
matches area(s Shape) Decimal
from
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

reads length(s String) Integer
from
    count_bytes(s)

creates builder() Builder
from
    allocate_buffer()

inputs request(route Route, body String, db Database) Response!
from
    Get(/health) => ok("healthy")
    Get(/users) => users(db)! |> encode |> ok
    Post(/users) => create(db, body)! |> encode |> created
    _ => not_found()
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
// Predicate context → resolves to validates email
clean_list as List<Email> = filter(inputs, valid email)

// Email context + String param → resolves to transforms email
clean as Email = email(raw_input)

// Email context + Integer param → resolves to inputs email
stored as Email = email(user.id)

// When context is ambiguous, use `valid` for explicit Boolean cast
print(valid email(input))               // forces validates variant

// `valid` as type-cast parameter — passes the validates function itself
filter(users, valid email)              // passes `validates email` as predicate
```

Resolution rules:
1. **Boolean context** (`match` on Boolean, `&&`, `||`, `!`) → resolves to `validates` variant
2. **Expected type** from assignment or parameter → matches the variant returning that type
3. **Parameter types** disambiguate between variants with the same return type
4. **Ambiguous** → compiler error with suggestions listing available variants

The `valid` keyword serves two purposes:
- **As expression**: `valid email(input)` — casts a validates call to its Boolean result explicitly
- **As function reference**: `valid email` (no parens) — passes the validates function as a predicate to higher-order functions like `filter`

Implications:

- **Imports are precise**: `Auth validates login, inputs session`
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

IO is inherent in the verb — `inputs` and `outputs` always interact with the external world. Fallibility is marked with `!` on the return type. Pure verbs (`transforms`, `validates`, `reads`, `creates`, `matches`) have neither IO nor `!`.

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

## Body Marker: `from`

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

## Pattern Matching — The Only Way to Branch

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

There is no `if discount > 0 then apply_discount(...)`. The `requires` clause on `apply_discount` ensures the compiler has already proven the discount is valid before the call happens. The "branching" lives in the type system and contracts, not in boolean conditions.

**5. Boolean matching is a code smell.**

`match x > 0 / true => ... / false => ...` is technically valid but signals that you should model your domain better. Instead of branching on `amount > 0`, define `type Positive is Integer where > 0` and let the type system handle it. The branching disappears into the type — where the compiler can prove things about it.

### The Rule

Branch on *what something is*, not on *whether something is true*. Types and contracts handle the rest — `requires` guards preconditions, `ensures` guarantees postconditions, and `explain` documents the reasoning. No boolean branch needed.

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
- **No closures** — lambdas cannot reference variables from the enclosing scope. All values must be passed as arguments or accessed through the lambda's own parameters.
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

For complex iteration that doesn't fit map/filter/reduce, use recursion with a `transforms` function.

## Keyword Exclusivity

Every keyword in Prove has exactly one purpose. No keyword is overloaded across different contexts. This makes the language predictable and parseable by humans without memorizing context-dependent rules.

**Core keywords:**

| Keyword | What it does |
|---------|-------------|
| `transforms` | Declares a pure function — no side effects, just data in, data out |
| `validates` | Declares a function that returns true or false |
| `reads` | Declares a pure function that extracts or queries data without changing it |
| `creates` | Declares a pure function that constructs a new value |
| `inputs` | Declares a function that reads from the outside world (database, file, network) |
| `outputs` | Declares a function that writes to the outside world |
| `main` | The program's entry point — can freely mix reading and writing |
| `from` | Marks where the function body starts — "the result comes from..." |
| `where` | Adds a value constraint to a type — `Integer where 1..65535` |
| `as` / `is` | `as` declares a variable — `port as Port = 8080` (what it's treated as). `is` defines a type — `type Port is Integer` (what it is) |
| `type` | Starts a type definition — `type Port is Integer where 1..65535` |
| `match` | Branches on a value — the only way to do conditional logic |
| `ensures` | States what a function guarantees about its result — a hard postcondition |
| `requires` | States what must be true before calling a function — a hard precondition |
| `matches` | Declares a pure function that dispatches on an algebraic first parameter |
| `explain` | Documents each step in the `from` block using controlled natural language. **Strict** (with `ensures`): row count must match `from`, references verified against contracts. **Loose** (without `ensures`): free-form text, documentation only. LSP-suggested, not compiler-required |
| `terminates` | Required for recursive functions — declares a measure expression that decreases on each call. Compiler error if omitted |
| `trusted` | Explicitly marks a function as unverified — acknowledges the gap when `ensures` would otherwise be expected |
| `valid` | References a `validates` function as a predicate |
| `comptime` | Runs code at compile time instead of runtime |
| `foreign` | Declares a C FFI block inside a module — `foreign "libname"` |

### Interface Contracts: `requires`, `ensures`

`requires` and `ensures` are hard rules about the function's interface. The compiler enforces them automatically.

```prove
type Clamped is Integer where low .. high

transforms clamp(value Integer, low Integer, high Integer) Clamped
  requires low <= high
  ensures result >= low
  ensures result <= high
from
    max(low, min(value, high))
```

`requires` states what must be true before calling the function — the compiler rejects call sites that can't prove it. `ensures` states what the function guarantees about its result — the compiler verifies every code path or generates property tests. Here, the refinement type `Clamped` does the heavy lifting.

### Implementation Explanation: `explain`

`explain` documents the chain of operations in the `from` block using controlled natural language. It is **LSP-suggested, not compiler-required** — the LSP recommends adding it when a function has enough complexity to warrant documentation.

**Two strictness modes:**

**Strict mode** (function has `ensures`): Each explain row corresponds to a **top-level statement** in the `from` block — a binding, a final expression, or a match arm. Multi-line expressions (pipe chains, multi-line arms) count as one. The count must match exactly (mismatch is a compiler error). The compiler warns if a single arm grows complex enough to warrant extraction into a named function.

The compiler parses each row for an **operation** (action verb), **connectors** (prepositions like `by`, `to`, `all`), and **references** (identifiers from the function). Operations are verified against called functions' contracts — if the called function has no contracts supporting the claimed operation, the compiler warns. References must be real identifiers. Sugar words ("the", "applicable", etc.) are ignored — keeping explain readable as natural English while remaining machine-verifiable.

```prove
transforms calculate_total(items List<OrderItem>, discount Discount, tax TaxRule) Price
  ensures result >= 0
  requires len(items) > 0
  explain
    sum all items . price
    reduce sub by discount
    add tax to discounted
from
    sub as Price = subtotal(items)
    discounted as Price = apply_discount(discount, sub)
    apply_tax(tax, discounted)
```

Sugar words keep it readable — the compiler sees the same thing:

```prove
  explain
    sum all the items.price
    reduce the sub by discount
    add applicable tax to the discounted total
```

Compiler parses: `sum` (operation) + `all` (connector) + `items.price` (reference), ignoring "the". Both forms are equivalent.

**Loose mode** (no `ensures`): Row count is flexible. Free-form text. Documentation value only.

```prove
transforms merge_sort(xs List<T>) Sorted<List<T>>
  explain
    split the list at the midpoint
    recursively sort both halves
    merge the sorted halves back together
  terminates: len(xs)
from
    halves as Pair<List<T>> = split_at(xs, len(xs) / 2)
    left as Sorted<List<T>> = merge_sort(halves.first)
    right as Sorted<List<T>> = merge_sort(halves.second)
    merge(left, right)
```

**Warning pairs:**

- `ensures` without `explain` → warning: add explain to document how ensures are satisfied
- `explain` without `ensures` → warning: explain is unverifiable without contracts to check against

**Bare functions are fine.** Trivial code needs no annotations:

```prove
validates email(address String)
from
    contains(address, "@") && contains(address, ".")
```

No explain needed — the implementation is self-evident. The LSP suggests explain only when complexity warrants it.

For `matches` functions, each explain row corresponds to one arm. The LSP suggests per-arm explain for complex dispatch:

```prove
matches apply_discount(discount Discount, amount Price) Price
  ensures result >= 0
  ensures result <= amount
  explain
    clamp the difference to zero
    scale amount by complement of rate
    subtract bulk discount from amount
from
    FlatOff(off) => max(0, amount - off)
    PercentOff(rate) => amount * (1 - rate)
    BuyNGetFree(buy, free) =>
        sets as Integer = len(items) / (buy + free)
        amount - sets * cheapest_price(items)
```

**Custom vocabulary** for operations and connectors can be declared at module level or in `prove.toml`:

```toml
# prove.toml
[explain]
operations = ["amortize", "interpolate", "normalize"]
connectors = ["across", "between", "within"]
```

`explain` is independent of `requires` and `ensures`. A function can have any combination — though the strictness mode depends on whether `ensures` is present.

### Termination: `terminates`

Recursive functions must declare `terminates` with a measure expression — an expression that strictly decreases on each recursive call. Omitting `terminates` on a recursive function is a compiler error.

```prove
transforms merge_sort(xs List<T>) Sorted<List<T>>
  explain
    split the list at the midpoint
    recursively sort the first half
    recursively sort the second half
    merge both sorted halves preserving order
  terminates: len(xs)
from
    halves as Pair<List<T>> = split_at(xs, len(xs) / 2)
    left as Sorted<List<T>> = merge_sort(halves.first)
    right as Sorted<List<T>> = merge_sort(halves.second)
    merge(left, right)
```

The compiler verifies that `len(halves.first) < len(xs)` and `len(halves.second) < len(xs)` at both recursive call sites.

### Annotation Ordering

All annotations appear between the verb line and `from`. The compiler accepts any order. The formatter normalizes to this canonical order:

1. `requires` — preconditions
2. `ensures` — postconditions
3. `terminates` — recursion measure
4. `trusted` — explicit verification opt-out
5. `know` / `assume` / `believe` — confidence levels
6. `why_not` / `chosen` — design reasoning
7. `near_miss` — boundary examples
8. `satisfies` — invariant networks
9. `explain` — implementation documentation (adjacent to `from`)

**AI-Resistance keywords (Phase 1+2):**

### Module-level: `narrative`, `domain`, `temporal`

```prove
module PaymentService
  narrative: """
  Customers submit payments. Each payment is validated,
  charged through the gateway, and recorded in the ledger.
  """
  domain Finance
  temporal: validate -> charge -> record
```

`narrative` is required — it describes the module's purpose in plain language. `domain` tags the module's problem domain. `temporal` declares the expected ordering of operations. These are currently **documentation keywords** — the compiler requires `narrative` but does not yet verify semantic coherence. Compiler verification (rejecting unrelated functions, enforcing domain-specific rules, checking temporal ordering) is planned for a future release.

### Function-level: `why_not`, `chosen`, `near_miss`

```prove
transforms select_gateway(amount Price, region Region) Gateway
  why_not: "Round-robin ignores regional latency differences"
  why_not: "Cheapest-first causes thundering herd on one provider"
  chosen: "Latency-weighted routing balances cost and speed per region"
from
    closest_by_latency(region, available_gateways())

validates leap_year(y Year)
  near_miss: 1900  => false
  near_miss: 2000  => true
  near_miss: 2100  => false
from
    y % 4 == 0 && (y % 100 != 0 || y % 400 == 0)
```

`why_not` documents rejected alternatives. `chosen` explains the selected approach. These are currently **documentation keywords** — compiler verification of rationale consistency is planned. `near_miss` provides inputs that *almost* break the code — the compiler verifies each near-miss exercises a distinct boundary condition.

### Confidence: `know`, `assume`, `believe`

```prove
transforms process_order(order Order) Receipt
  know: len(order.items) > 0            // proven by NonEmpty type — zero cost
  assume: order.total == sum(prices)    // runtime check inserted at boundaries
  believe: order.user.is_verified       // compiler generates tests to disprove this
from
    // implementation
```

`know` = the compiler can prove it (free). `assume` = the compiler adds a runtime check. `believe` = the compiler tries to break it with generated tests.

### Verification Chain: `trusted`

`ensures` requirements propagate through the call graph. If function A has `ensures` and calls function B, the compiler needs B's contracts to verify A's postconditions. If B has no `ensures`, the compiler warns — A's verification is incomplete.

`trusted` is the explicit opt-out. It acknowledges that a function is unverified and silences the warning:

```prove
transforms subtotal(items List<OrderItem>) Price
  trusted: "sum of non-negative prices is non-negative"
from
    reduce(items, 0, |acc, item| acc + item.price)
```

The compiler also warns when IO functions (`inputs`/`outputs`) or exported functions lack `ensures` — these are API boundaries where contracts matter most.

`prove check` reports verification coverage:

```
$ prove check

Verification:
  ✓ 42 functions with ensures (property tests)
  ✓ 11 validators with near_miss (boundary tests)
  ⚠ 3 functions trusted
  ✗ 1 unverified in chain → add ensures or trusted

Coverage: 89%
```

Functions outside any verification chain and with no callers that have `ensures` are fine without annotations — nobody depends on them contractually. The LSP suggests `near_miss` for `validates` functions with compound logic (multiple `&&`/`||`, modular arithmetic, negation). Trivial validators like `user.active` get no suggestion.

### Intent: `intent`

```prove
intent: "keep only valid records"
result as List<Record> = filter(records, valid record)

intent: "remove corrupt entries"
result as List<Record> = filter(records, valid corrupt)
```

`intent` annotates a statement with its purpose. Currently a **documentation keyword** — the compiler records it but does not yet verify that the intent matches the code's behavior. Verification using controlled natural language (similar to `explain`) is planned for a future release.

### Invariants: `invariant_network`, `satisfies`

```prove
invariant_network AccountingRules
  total_assets == total_liabilities + equity
  revenue - expenses == net_income
  every(transaction) preserves total_assets == total_liabilities + equity

transforms post_transaction(ledger Ledger, tx Transaction) Ledger
  satisfies AccountingRules
from
    // implementation — compiler verifies the rules hold after every change
```

`invariant_network` defines rules that must always hold together. `satisfies` declares that a function obeys those rules.

## Error Propagation

`!` marks fallibility — on declarations it means "this function can fail", at call sites it propagates the error upward. Only IO verbs (`inputs`, `outputs`) can use `!`. There is one `Error` type — errors are program-ending, not flow control. `!` errors propagate up the call chain until they reach `main`, which exits with an error message. There is no try/catch.

Pure functions that need to represent expected failure cases use `Result<T, E>` and handle them with `match` — these are values, not errors.

```prove
main()!
from
    config as Config = load("app.yaml")!
    db as Database = connect(config.db_url)!
    serve(config.port, db)!
```

## Complete Example: RESTful Server

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
main()!
from
    port as Port = 8080
    db as Database = connect("postgres://localhost/app")!
    server as Server = new_server()
    route(server, "/", request)
    listen(server, port)!
```
