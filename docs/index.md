---
title: Prove - Intent-First Programming Language
description: Prove is an intent-first programming language designed to mitigate AI slop and code scraping. Every function declares its purpose, guarantees, and reasoning before implementation.
keywords: programming language, intent-first, AI resistance, code scraping protection, contracts, refinement types
---

# Prove

<img src="assets/icon.png" alt="Prove" width="100" height="100">

**A programming language designed to mitigate AI slop and code scraping.**

Prove is an intent-first programming language — every function declares its purpose (verb), guarantees (contracts), and reasoning (explain) before the implementation begins, and the compiler enforces that intent matches reality. This strict enforcement, coupled with features like explicit verbs and verifiable explain blocks, makes it exceptionally difficult for AI to generate semantically correct and compilable code without true understanding. Source is stored as binary AST — unscrapable, unnormalizable, unlicensed for training. If it compiles, the author understood what they wrote. If it's AI-generated, it won't. [Learn more about Prove's AI Resistance](ai-resistance.md)

```prove
transforms add(a Integer, b Integer) Integer
  ensures result == a + b
from
    a + b
```

The `ensures` clause declares hard postconditions — the compiler enforces them automatically. The `transforms` verb guarantees purity. None of it can be faked by autocomplete.

---

## Why Prove?

| Problem | How Prove solves it |
|---|---|
  | [AI scrapes your code for training](ai-resistance.md#anti-training-license-for-prove-code) | Binary AST format + anti-training license + semantic normalization |
  | [AI slop PRs waste maintainer time](ai-resistance.md#implementation-explanation-as-code) | Compiler rejects code without explanations and intent |
  | [Tests are separate from code](contracts.md) | Testing is part of the definition — `ensures`, `requires`, `near_miss` |
  | ["Works on my machine"](design.md#cli-first-toolchain-prove) | Verb system makes IO explicit |
  | [Null/nil crashes](design.md#error-handling-errors-are-values) | No null — `Option<Value>` enforced by compiler |
  | ["I forgot an edge case"](ai-resistance.md#adversarial-type-puzzles-refinement-types) | Compiler generates edge cases from types |
  | [Runtime type errors](types.md) | Refinement types catch invalid values at compile time |
  | [Code without reasoning](ai-resistance.md#implementation-explanation-as-code) | `explain` documents each step using controlled natural language — verified against contracts |

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

Every function declares its purpose with a verb. The compiler enforces it. Pure verbs (`transforms`, `validates`, `reads`, `creates`, `matches`) cannot perform IO. IO verbs (`inputs`, `outputs`) make side effects explicit.

```prove
matches area(s Shape) Decimal
from
    Circle(r) => pi * r * r
    Rect(w, h) => w * h

validates email(address String)
from
    contains(address, "@") && contains(address, ".")

reads get(key String, table Table<Value>) Option<Value>
from
    lookup(table, key)

creates builder() Builder
from
    allocate_buffer()

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
type Email is String where r"^[^[:space:]@]+@[^[:space:]@]+\.[^[:space:]@]+$"
type NonEmpty<Value> is List<Value> where len > 0

transforms head(xs NonEmpty<Value>) Value         // no Option needed — emptiness is impossible
```

The compiler rejects `head([])` statically.

### Contracts

`requires` and `ensures` are hard rules about the function's interface. The compiler enforces them automatically:

```prove
matches apply_discount(discount Discount, amount Price) Price
  ensures result >= 0
  ensures result <= amount
  requires amount >= 0
from
    FlatOff(off) => max(0, amount - off)
    PercentOff(rate) => amount * (1 - rate)
```

`explain` documents the chain of operations in the `from` block using controlled natural language. With `ensures` present (strict mode), the row count must match the `from` block and references are verified against contracts. Without `ensures` (loose mode), explain is free-form documentation:

```prove
module Example
  narrative: """An example of email update"""
  import Console inputs reads, outputs writes
  import Json creates json, reads json
  import Value validates value

  type Email is String where r"^[^[:space:]@]+@[^[:space:]@]+\.[^[:space:]@]+$"

  type User is
    id Integer
    name String
    email String

  USER_FILE as String = "user.json"

inputs email() Option<Email>!
from
    console("What is your email?")

transforms user(json_data Result<Value, String>) User
  requires valid object(json_data)
from
    data as Table<Value> = object(json_data)
    User(data.id, data.name, data.email)

matches ensure_user(raw String) User
from
    Some(raw) =>
        json_data as Result<Value, String> = json(raw)
        user(json_data)
    _ => User()

validates id(id Option<Integer>)
  requires valid integer(id)
from
    id > 0

transforms set_email(user User, email Option<Email>) User
  requires valid email(email)
from
    User(user.id, user.name, email)

transforms dump_user(user User) String
  requires valid value(user)
from
    json(value(user))

outputs save(json_data String)!
  requires valid string(json_data)
from
    file(USER_FILE, json_data)!

outputs update_email(id Option<Integer>) User!
  ensures valid user(updated)
  requires valid id(id)
  explain
      we get an email address
      we fetch the user
      we set the email to user
      change the user to json string and save it
      return the updated user
from
    email as Option<Email> = email()
    user as User = user(id)!
    updated as User = set_email(user, email)
    save(dump_user(updated))
    updated
```

`explain` is LSP-suggested, not compiler-required — but `ensures` without `explain` produces a warning, since promises should be documented.

### No Loops — Functional Iteration

Prove enforces functional iteration (map, filter, reduce) over traditional loops to ensure pure functions, immutability, easier formal verification, improved testability, and a simpler language design.

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

Errors are values. `!` propagates failures. No exceptions. This explicit approach prevents silent failures, enhances predictability, and simplifies reasoning about program outcomes.

```prove
main()!
from
    config as Config = load("app.yaml")!
    db as Database = connect(config.db_url)!
    serve(config.port, db)!
```

---

## Simple Example

Here's a basic function definition that transforms an integer and ensures its output:
```prove
transforms double(n Integer) Integer
  ensures result == n * 2
from
    n * 2
```

For a more comprehensive demonstration of Prove's features, see the [Inventory Service Example](examples/inventory_service.md).

---

## Compiler Pipeline

```
Source (.prv) → Lexer → Parser → Checker → Prover → Optimizer → C Emitter → gcc/clang → Native Binary
```
*   **Lexer:** Breaks source code into a stream of tokens.
*   **Parser:** Transforms the token stream into an Abstract Syntax Tree (AST).
*   **Checker:** Performs type checking, semantic analysis, and contract verification.
*   **Prover:** Generates and verifies proofs for intent and contracts.
*   **Optimizer:** Applies various optimizations to the AST.
*   **C Emitter:** Translates the optimized AST into C source code.
*   **gcc/clang:** Compiles the C code into a native binary.

The example above — JSON parsing, console I/O, guarded file writes — compiles to a **37 KB** native binary. The runtime is stripped to only the modules actually used.

## Ecosystem

- **tree-sitter-prove** — Tree-sitter grammar for editor syntax highlighting
- **pygments-prove** — Pygments lexer for MkDocs and Sphinx code rendering
- **chroma-lexer-prove** — Chroma lexer for Gitea/Hugo code rendering

## Status

v0.8.3 — Formatter type inference, lint system overhaul, `proof` → `explain` migration, and remaining lint diagnostics are complete. The compiler lexes, parses, type-checks, emits C, and produces native binaries. 506 tests pass across every stage. Next up: v0.9 (lexer export tool) and v1.0 (self-hosting).

## Repository

Source code is hosted at [code.botwork.se/Botwork/prove](https://code.botwork.se/Botwork/prove).

## Contributing

For information on contributing to Prove, see our [Contributing Guide](contributing.md).

## License

The Prove language, its specification, and all `.prv` source code are covered by the [Prove Source License v1.0](https://code.botwork.se/Botwork/prove/src/branch/main/LICENSE) — permissive for developers, prohibits use as AI training data.

The compiler tooling (bootstrap compiler, documentation, editor integrations) is licensed under [Apache-2.0](https://code.botwork.se/Botwork/prove/src/branch/main/prove-py/LICENSE). See [AI Transparency](design.md#ai-transparency) for why the licenses differ.
