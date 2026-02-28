# Prove

**A programming language that fights back against AI slop and code scraping.**

Prove is a strongly typed, compiler-driven language where contracts generate tests, intent verbs enforce purity, and the compiler rejects code that can't demonstrate understanding. Source is stored as binary AST — unscrapable, unnormalizable, unlicensed for training. If it compiles, the author understood what they wrote. If it's AI-generated, it won't.

```prove
transforms add(a Integer, b Integer) Integer
  ensures result == a + b
from
    a + b
```

The `ensures` clause generates property tests. The `transforms` verb guarantees purity. The compiler proves or tests every contract — and none of it can be faked by autocomplete.

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

### Pattern Matching

Exhaustive, indentation-based.

```prove
type Shape is Circle(radius Decimal) | Rect(w Decimal, h Decimal)

match shape
    Circle(r) => pi * r * r
    Rect(w, h) => w * h
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

## Auto-Testing

Testing is built into the language — not bolted on.

**Contracts generate property tests.** The compiler generates thousands of random inputs and checks all postconditions. No test files, no boilerplate — contracts are mandatory and the compiler enforces them.

```prove
transforms sort(xs List<T>) List<T>
  ensures len(result) == len(xs)
  ensures is_sorted(result)
  ensures is_permutation_of(result, xs)
```

**Edge cases from types.** Given `Port` (1..65535), the compiler auto-tests boundaries: 1, 2, 65534, 65535, and verifies 0 and 65536 are rejected.

**Mutation testing.** `prove build --mutate` tells you which mutations survive your contracts — and suggests contracts to add.

---

## AI-Resistance

Prove is designed so that generating correct code requires genuine understanding, not statistical pattern matching.

### Counterfactual Annotations

Explain what you considered and why you rejected it.

```prove
transforms evict(cache Cache:[Mutable]) Option<Entry>
  why_not: "FIFO would evict still-hot entries under burst traffic"
  why_not: "Random eviction has unbounded worst-case for repeated keys"
  chosen: "LRU because access recency correlates with reuse probability"
from
    least_recently_used(cache)
```

### Epistemic Annotations

Declare your confidence level. The compiler treats each tier differently.

```prove
transforms process_order(order Order) Receipt
  know: len(order.items) > 0           // proven by type system — zero cost
  assume: order.total == sum(prices)   // runtime validation inserted
  believe: order.user.is_verified      // adversarial tests generated
```

### Near-Miss Testing

Prove you understand the exact boundary between correct and incorrect.

```prove
validates leap_year(y Year)
  near_miss: 1900  => false
  near_miss: 2000  => true
  near_miss: 2100  => false
from
    y % 4 == 0 && (y % 100 != 0 || y % 400 == 0)
```

### Anti-Training Protections

- `.prv` files stored as binary AST, not plain text
- Semantic normalization strips naming patterns before storage
- Fragmented source (implementation, proofs, intents in separate files)
- Identity-bound compilation with cryptographic signatures
- **Prove Source License v1.0** — permissive for developers, prohibits AI training

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

## Project Structure

```
prove/
├── src/prove/
│   ├── cli.py           # CLI entry point (prove new/build/check/test)
│   ├── lexer.py         # Tokenizer (indent/dedent, string interpolation)
│   ├── parser.py        # Pratt expression parser + recursive descent
│   ├── ast_nodes.py     # Frozen dataclass AST nodes
│   ├── checker.py       # Two-pass semantic analyzer
│   ├── prover.py        # Proof verification
│   ├── c_emitter.py     # C code generation
│   ├── c_compiler.py    # gcc/clang invocation
│   ├── builder.py       # Full pipeline: lex → parse → check → emit → compile
│   ├── testing.py       # Test generation from contracts
│   ├── runtime/         # C runtime library (strings, lists, HTTP, etc.)
│   └── stdlib/          # Standard library (.prv files)
├── examples/
│   ├── hello/           # Hello world
│   ├── math/            # Math with contracts
│   └── http_server/     # HTTP routing with algebraic types
└── tests/               # 283 tests covering every compilation stage
```

## Development

```bash
pip install -e ".[dev]"

python -m pytest tests/ -v    # run tests
ruff check src/ tests/        # lint
mypy src/                     # type check
```

## Toolchain

```
Source (.prv) → Lexer → Parser → Checker → Prover → C Emitter → gcc/clang → Native Binary
```

## Design Inspirations

**Rust** — ownership, exhaustive matching, no null.
**Haskell** — algebraic types, pure functions.
**Go** — `name Type` parameter syntax, simplicity.
**Python** — indentation-based blocks, readability.
**Zig** — compile-time computation with IO.
**Ada/SPARK** — contract-based programming, formal verification.

## Ecosystem

- **[tree-sitter-prove](../tree-sitter-prove)** — Tree-sitter grammar for editor syntax highlighting
- **[chroma-lexer-prove](../chroma-lexer-prove)** — Chroma lexer for Gitea/Hugo code rendering

## Status

v0.1.0 — the core compilation pipeline works end-to-end. The compiler lexes, parses, type-checks, emits C, and produces native binaries. 283 tests pass across every stage. Next milestone: assembly backend (x86_64 + ARM64) and advanced AI-resistance features.

## License

[Prove Source License v1.0](LICENSE) — permissive for developers, prohibits use as AI training data.
