---
title: Tutorial - Prove Programming Language
description: Step-by-step introduction to Prove programming — from your first function to contracts and async.
keywords: Prove tutorial, getting started with Prove, Prove basics
---

# Tutorial

This tutorial walks you through Prove's core concepts step by step. By the end, you'll understand intent-first programming and why it's different from other languages.

## Prerequisites

- Python 3.11+
- gcc or clang
- A text editor

**Optional** (for GUI applications using the Graphic module):

- SDL2 (`brew install sdl2` on macOS, `apt install libsdl2-dev` on Linux)

Install Prove:

```bash
pip install -e ".[dev]"
```

---

## Your First Function

Every Prove function declares its **intent** before implementation. The verb tells the compiler (and readers) what the function does:

```prove
derives double(n Integer) Integer
  ensures result == n * 2
from
    n * 2
```

Let's break this down:

| Part | Meaning |
|------|---------|
| `derives` | This is a pure function — non-mutating data access |
| `double(n Integer) Integer` | Takes an Integer, returns an Integer |
| `ensures result == n * 2` | Contract: the result must equal n times 2 |
| `from` | Everything after this is the implementation |
| `n * 2` | The actual computation |

Try running it:

```bash
proof new hello
cd hello
# Edit src/main.prv to add the double function, then:
proof build
./build/hello
```

---

## Verbs: Declaring Intent

Prove uses **verbs** instead of generic `function` or `fn`. Each verb has a specific meaning:

### Pure Verbs (No Side Effects)

```prove
transforms add(a Integer, b Integer) Integer
from
    a + b

validates is_positive(n Integer)
from
    n > 0

derives first(items List<Integer>) Option<Integer>
from
    len(items) > 0 => Some(items[0])
    _ => None

creates builder() StringBuilder
from
    allocate()
```

| Verb | Purpose |
|------|---------|
| `transforms` | Convert data from one form to another |
| `validates` | Return true/false (implicitly Boolean) |
| `derives` | Extract or query without modification |
| `creates` | Construct a new value |

### IO Verbs (Side Effects)

```prove
inputs read_file(path String) String!
from
    file(path)

outputs write_file(path String, content String)!
from
    file(path, content)
```

| Verb | Purpose |
|------|---------|
| `inputs` | Read from external world |
| `outputs` | Write to external world |

The compiler **enforces** these distinctions. A `transforms` function cannot call `inputs` or `outputs` — the verb itself guarantees purity.

---

## Types and Refinements

Types in Prove carry **constraints**, not just shapes:

```prove
// A port number — must be between 1 and 65535
type Port is Integer:[16 Unsigned] where 1 .. 65535

// An email — must match a regex pattern
type Email is String where r"^[^[:space:]@]+@[^[:space:]@]+\.[^[:space:]@]+$"

// A non-empty list — length must be greater than 0
type NonEmpty<Value> is List<Value> where len > 0
```

With `NonEmpty`, you never need to check if a list is empty — the type guarantees it:

```prove
transforms first(items NonEmpty<Value>) Value
from
    items[0]  // Safe! Compiler knows it's not empty
```

---

## Pattern Matching

Prove has no `if/else`. All branching uses `match`:

```prove
matches area(shape Shape) Decimal
from
    match shape
        Circle(r) => pi * r * r
        Rect(w, h) => w * h
```

The compiler **enforces exhaustiveness** — if you add a new variant to `Shape`, it will error until you handle it everywhere.

### Why No `if`?

1. **Types replace booleans** — model your domain with types, not conditions
2. **Exhaustiveness is enforced** — no forgotten edge cases
3. **One construct is simpler** — `match` handles all branching

---

## Contracts: Proving Correctness

Contracts declare what a function guarantees. The compiler enforces them:

```prove
transforms apply_discount(price Price, discount Discount) Price
  requires discount >= 0
  requires price >= 0
  ensures result >= 0
  ensures result <= price
from
    match discount
        None => price
        FlatOff(amount) => max(0, price - amount)
        PercentOff(rate) => price * (1 - rate)
```

- `requires` — what must be true **before** the function is called
- `ensures` — what is guaranteed **after** the function returns

---

## Error Handling

Errors are values, not exceptions:

```prove
inputs load_config(path Path) Config!
from
    content as String = file(path)!
    parse(content)
```

The `!` marks fallibility — it propagates errors up the call chain. IO verbs (`inputs`, `outputs`) and `transforms` (the only failable pure verb) can use `!`.

For pure functions that need to represent failure, use `Result`:

```prove
transforms divide(a Decimal, b Decimal) Decimal!
  requires b != 0
from
    a / b
```

---

## No Null

Prove has no null. Use `Option<Value>` instead:

```prove
inputs find_user(db Store, id Integer) Option<User>!
from
    match query(db, "SELECT * FROM users WHERE id = {id}")!
        [] => None
        [user] => Some(user)
        _ => None  // Should never happen
```

---

## Iteration: Functional Style

No loops. Use `map`, `filter`, `reduce`:

```prove
// Get names of all active users
names as List<String> = map(users, |u| u.name)

// Filter to active users only
active as List<User> = filter(users, |u| u.active)

// Calculate total price
total as Decimal = reduce(items, 0, |acc, item| acc + item.price)

// Chain operations with pipe
result as List<String> = users
    |> filter(|u| u.active)
    |> map(|u| u.email)
```

---

## Async: Structured Concurrency

Three async verbs for different patterns:

```prove
// Fire and forget — caller doesn't wait
detached log(message String)
from
    console(message)

// Spawn and await — caller waits for result
attached fetch(url String) String
from
    request(url)&

// Event dispatcher — cooperative loop
listens handler(workers List<Attached>)
    event_type Command
from
    Process(data) => handle(data)&
    Exit => Unit
```

The `&` marker dispatches to a coroutine. No threads, no data races.

---

## What's Next?

- Read [Syntax Reference](syntax.md) for the complete grammar
- Explore the [Standard Library](stdlib/index.md) modules
- See the [Inventory Example](examples/inventory_service.md) for a full application
- Check the [Roadmap](roadmap.md) for upcoming features
