---
title: Functions & Verbs - Prove Programming Language
description: Complete reference for Prove's function declarations, intent verbs, async verbs, verb dispatch, lambdas, and iteration.
keywords: Prove functions, intent verbs, async verbs, verb dispatch, lambdas, iteration, pure functions
---

# Functions & Verbs

## Intent Verbs

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

inputs request(route Route, body String, db Store) Response!
from
    Get(/health) => ok("healthy")
    Get(/users) => users(db)! |> encode |> ok
    Post(/users) => create(db, body)! |> encode |> created
    _ => not_found()
```

See [Contracts & Annotations](contracts.md#requires-and-ensures) for `ensures` and `requires` on function signatures.

---

## Async Verbs

| Verb | Purpose | Compiler enforces |
|------|---------|-------------------|
| `detached` | Spawn and move on — fire-and-forget | No return type. Body runs concurrently; caller does not wait |
| `attached` | Spawn and await — caller blocks until result is ready | Must declare a return type. No blocking IO calls |
| `listens` | Cooperative loop — processes items until `Exit` | `from` block must be a single implicit match with an `Exit` arm. No return type |

Async verbs form a third family alongside pure and IO. The key difference from IO verbs: `attached` and `listens` bodies must not call blocking `inputs`/`outputs` functions — they run cooperatively and blocking would stall the yield cycle. `detached` is exempt since it runs independently. Concurrency is cooperative — no threads, no data races. Runtime backed by `prove_coro` stackful coroutines (`ucontext_t` on POSIX, sequential fallback on Windows).

### The `&` Marker

`&` marks an async call at the call site. It mirrors `!` for failable calls:

| Marker | Meaning | Example |
|--------|---------|---------|
| `!` | can fail — propagate error | `result = parse(input)!` |
| `&` | async invocation — dispatch to coroutine | `data = fetch(url)&` |

The verb (`detached`, `attached`, `listens`) declares intent at the function level. `&` only appears at call sites inside async bodies where work is dispatched to another async function.

### `detached` — Fire and Forget

Spawns a coroutine and returns immediately. The caller does not wait for completion. Cannot declare a return type ([E374](diagnostics.md#e374-detached-or-listens-declared-with-a-return-type)). May call blocking IO freely since it runs independently.

```prove
type Event is
    Info(message String)
  | Warning(message String)

/// Log an event — fire and forget, caller moves on immediately.
detached log(event Event)
from
    console(event.message)
```

### `attached` — Spawn and Await

Spawns a coroutine and blocks the caller until the result is ready. Must declare a return type ([E370](diagnostics.md#e370-unknown-variant-attached-without-return-type)). Cannot call blocking IO ([E371](diagnostics.md#e371-non-exhaustive-match-blocking-io-in-async-body)) — use `&` to dispatch to other async functions instead.

```prove
/// Fetch and parse data — caller waits for the result.
attached fetch(url String) String
from
    request(url)&
```

### `listens` — Cooperative Loop

The `listens` verb declares a cooperative loop that processes items from an algebraic type source until an `Exit` arm terminates the loop. This is the async equivalent of iterating over a stream.

**Key rules:**

- The first parameter must be an algebraic type — the loop dispatches on its variants
- The `from` block must be a single implicit match (bare arms, no `match` keyword)
- One arm must match the `Exit` variant — this terminates the loop
- Cannot declare a return type ([E374](diagnostics.md#e374-detached-or-listens-declared-with-a-return-type)) — `listens` never produces a value
- Cannot call blocking IO ([E371](diagnostics.md#e371-non-exhaustive-match-blocking-io-in-async-body)) — use `&` to dispatch to async functions

```prove
type Command is
    Process(data String)
  | Tick
  | Exit

/// Handle commands until Exit — cooperative loop.
listens dispatcher(source Command)
from
    Exit           => source
    Process(data)  => handle(data)&
    Tick           => heartbeat()&
```

The `from` block works like the `matches` verb — arms are matched against the first parameter without an explicit `match` keyword. Each iteration of the loop yields cooperatively, then dispatches the next item to the matching arm. When the `Exit` variant is matched, the loop terminates.

**Full example — async event processor:**

```prove
module EventProcessor
  narrative: """Process events using all three async verbs."""
  InputOutput outputs console

  type Event is Data(payload String)
    | Exit

/// Fire and forget — log without blocking.
detached fire(msg String)
from
    console(msg)

/// Cooperative loop — process events until Exit.
listens handler(source Event)
from
    Exit        => source
    Data(text)  => fire(text)&

main() Unit
from
    fire("system started")
    fire("processing complete")
```

**Safety rules the compiler enforces:**

| Code | Trigger | Severity |
|------|---------|----------|
| [E370](diagnostics.md#e370-unknown-variant-attached-without-return-type) | `attached` declared without a return type | Error |
| [E371](diagnostics.md#e371-non-exhaustive-match-blocking-io-in-async-body) | Blocking `inputs`/`outputs` call in `attached` or `listens` body (`detached` is exempt) | Error |
| [E372](diagnostics.md#e372-unknown-variant-for-generic-type-async-call-without) | Async function called without `&` inside an async body | Error |
| [E373](diagnostics.md#e373---used-outside-an-async-body) | `&` used outside an async body | Error |
| [E374](diagnostics.md#e374-detached-or-listens-declared-with-a-return-type) | `detached` or `listens` declared with a return type (caller never waits) | Error |
| [E151](diagnostics.md#e151--listens-body-missing-an-exit-arm) | `listens` body missing an `Exit` arm | Error |
| [I375](diagnostics.md#i375---on-a-non-async-callee) | `&` on a non-async callee — has no effect; `prove format` removes it | Info |
| [I376](diagnostics.md#i376--attached-body-with-no--calls) | `attached` body with no `&` calls — probably meant `inputs`; `prove format` changes the verb | Info |

---

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

---

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

---

## Parameters

Go-style: `name Type` (no colon). Inside parentheses, the declaration context is already clear.

```prove
transforms area(s Shape) Decimal
inputs request(route Route, body String) Response!
validates email(address String)
```

---

## IO and Fallibility

IO is inherent in the verb — `inputs` and `outputs` always interact with the external world. Fallibility is marked with `!` on the return type. Pure verbs (`transforms`, `validates`, `reads`, `creates`, `matches`) have neither IO nor `!`. Async verbs (`detached`, `attached`, `listens`) are concurrent — `detached` may call IO freely (runs independently), while `attached` and `listens` must not block.

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

The compiler knows which functions touch the world (`inputs`/`outputs`) and which don't (`transforms`/`validates`) — the verb IS the declaration. See [Type System — Error Propagation](types.md#error-propagation) for how `!` works at call sites.

---

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

See [Contracts & Annotations](contracts.md#annotation-ordering) for the ordering of annotations between the verb line and `from`.

---

## Lambdas

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

---

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

For complex iteration that doesn't fit map/filter/reduce, use recursion with a `transforms` function and a [`terminates`](contracts.md#terminates) annotation.

---

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

/// Retrieves all users from the store.
inputs users(db Store) List<User>!
from
    query(db, "SELECT * FROM users")!

/// Creates a new user from a request body.
outputs create(db Store, body String) User!
  ensures email(result.email)
from
    user as User = decode(body)!
    insert(db, "users", user)!
    user

/// Routes incoming HTTP requests.
inputs request(route Route, body String, db Store) Response!
from
    Get("/health") => ok("healthy")
    Get("/users")  => users(db)! |> encode |> ok
    Post("/users") => create(db, body)! |> encode |> created
    _              => not_found()

/// Application entry point — no verb, main is special.
main()!
from
    port as Port = 8080
    db as Store = connect("postgres://localhost/app")!
    server as Server = new_server()
    route(server, "/", request)
    listen(server, port)!
```
