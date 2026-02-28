# Prove

![Prove](../assets/icon.png)

**A programming language that fights back against AI slop and code scraping.**

Prove is a strongly typed, compiler-driven language where contracts generate tests, intent verbs enforce purity, and the compiler rejects code that can't demonstrate understanding. Source is stored as binary AST — unscrapable, unnormalizable, unlicensed for training. If it compiles, the author understood what they wrote. If it's AI-generated, it won't.

```prove
transforms add(a Integer, b Integer) Integer
  ensures result == a + b
  proof
    correctness: result is the sum of a and b
from
    a + b
```

The `ensures` clause declares guarantees. The `proof` block explains *why* they hold. The `transforms` verb guarantees purity. The compiler enforces every contract — and none of it can be faked by autocomplete.

---

## Why Prove?

| Problem | How Prove solves it |
|---|---|
| AI scrapes your code for training | Binary AST format + anti-training license + semantic normalization |
| AI slop PRs waste maintainer time | Compiler rejects code without proof obligations and intent |
| Tests are separate from code | Testing is part of the definition — `ensures`, `requires`, `near_miss` |
| "Works on my machine" | Verb system makes IO explicit |
| Null/nil crashes | No null — `Option<T>` enforced by compiler |
| "I forgot an edge case" | Compiler generates edge cases from types |
| Runtime type errors | Refinement types catch invalid values at compile time |
| Contracts without proof | `ensures` without `proof` is a compile error (E390) |

---

## Quick Start

**Requirements:** Python 3.11+, gcc or clang

```bash
# Install
pip install -e ".[dev]"

# Create a project
prove new hello

# Build and run
cd hello
prove build
./build/hello

# Type-check only
prove check

# Run auto-generated tests
prove test
```

---

## Language Tour

### Intent Verbs

Every function declares its purpose. The compiler enforces it.

```prove
transforms area(s Shape) Decimal
from
    match s
        Circle(r) => pi * r * r
        Rect(w, h) => w * h

validates email(address String)
from
    contains(address, "@") && contains(address, ".")

inputs users(db Database) List<User>!
from
    query(db, "SELECT * FROM users")!

outputs log(message String)
from
    write(stdout, message)
```

The same name can exist with different verbs — the compiler resolves which to call from context:

```prove
validates email(address String)           // check if valid
transforms email(raw String) Email        // convert to Email type
inputs email(user_id Integer) Email!      // fetch from database
```

### Refinement Types

Types carry constraints, not just shapes.

```prove
type Port is Integer:[16 Unsigned] where 1..65535
type Email is String where matches(/^[^@]+@[^@]+\.[^@]+$/)
type NonEmpty<T> is List<T> where len > 0

transforms head(xs NonEmpty<T>) T         // no Option needed — emptiness is impossible
```

The compiler rejects `head([])` statically.

### Contracts and Proofs

Functions declare what they guarantee. The compiler verifies or tests it.

```prove
transforms apply_discount(discount Discount, amount Price) Price
  ensures result >= 0
  ensures result <= amount
  proof
    non_negative: FlatOff is clamped to zero , PercentOff rate is 0 .. 1
    bounded: every discount path subtracts from amount , never adds
from
    match discount
        FlatOff(off) => max(0, amount - off)
        PercentOff(rate) => amount * (1 - rate)
```

### No Loops — Functional Iteration

```prove
names as List<String> = map(users, |u| u.name)
active as List<User> = filter(users, |u| u.active)
total as Decimal = reduce(prices, 0, |acc, p| acc + p)

// Chaining with pipe operator
result as List<String> = users
    |> filter(|u| u.active)
    |> map(|u| u.email)
    |> filter(valid email)
```

### Error Handling

Errors are values. `!` propagates failures. No exceptions.

```prove
main() Result<Unit, Error>!
from
    config as Config = load("app.yaml")!
    db as Database = connect(config.db_url)!
    serve(config.port, db)!
```

---

## Complete Example

A RESTful inventory service demonstrating the full feature set:

```prove
module InventoryService
    narrative: """
    Products are added to inventory with validated stock levels.
    Orders consume stock. The system ensures stock never goes negative
    and all monetary calculations use exact decimal arithmetic.
    """

type Port is Integer:[16 Unsigned] where 1..65535
type Price is Decimal:[128 Scale:2] where >= 0
type Sku is String where matches(/^[A-Z]{2,4}-[0-9]{4,8}$/)

type Product is
    sku Sku
    name String
    price Price
    stock Quantity

/// Checks whether every item in an order can be fulfilled.
validates fulfillable(order Order)
from
    all(order.items, |item| in_stock(item.product, item.quantity))

/// Places an order: validates stock, calculates total, deducts inventory.
outputs place_order(db Database, order Order, tax TaxRule) Order!
  requires fulfillable(order)
  ensures result.status == Confirmed
  proof
    fulfillment: requires clause guarantees stock sufficiency
                 before deduction, so stock never goes negative
from
    total as Price = calculate_total(order.items, None, tax)
    confirmed as Order = Order(order.id, order.items, Confirmed, total)
    insert(db, "orders", confirmed)!
    deduct_stock(all_products(db)!, order.items) |> update_all(db, "products")!
    confirmed

/// Routes incoming HTTP requests.
inputs request(route Route, body String, db Database) Response!
from
    Get("/health")   => ok("healthy")
    Get("/products") => all_products(db)! |> encode |> ok
    Post("/orders")  => parse_order(body)! |> place_order(db, tax)! |> encode |> created
    _                => not_found()

main() Result<Unit, Error>!
from
    cfg as Config = load_config("inventory.yaml")!
    db as Database = connect(cfg.db_url)!
    server as Server = new_server()
    route(server, "/", request)
    listen(server, cfg.port)!
```

---

## Compiler Pipeline

```
Source (.prv) → Lexer → Parser → Checker → Prover → C Emitter → gcc/clang → Native Binary
```

## Ecosystem

- **tree-sitter-prove** — Tree-sitter grammar for editor syntax highlighting
- **chroma-lexer-prove** — Chroma lexer for Gitea/Hugo code rendering

## Status

v0.1.0 — the core compilation pipeline works end-to-end. The compiler lexes, parses, type-checks, verifies proof obligations, emits C, and produces native binaries. 326 tests pass across every stage.

## License

[Prove Source License v1.0](https://github.com/prove-lang/prove/blob/main/LICENSE) — permissive for developers, prohibits use as AI training data.
