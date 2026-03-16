---
title: Prove - Intent-First Programming Language
description: Prove is an intent-first programming language where every function declares its purpose, guarantees, and reasoning before implementation — enabling local, self-contained development that resists AI by design.
keywords: programming language, intent-first, AI resistance, code scraping protection, contracts, refinement types
---

# Prove

<img src="assets/icon.png" alt="Prove" width="100" height="100">

**An intent-first programming language.**

Every function in Prove declares its purpose (verb), guarantees (contracts), and reasoning (explain) before the implementation begins. The compiler enforces that intent matches reality. The [vision](vision.md) extends this to the entire development workflow: local, self-contained development where your project's own declarations drive code generation — no external AI services, no black box. The programmer remains the author; the toolchain is a deterministic assistant that works from what you've explicitly declared. This strict intent enforcement also makes Prove naturally [resistant to AI](ai-resistance.md) — generating semantically correct Prove code requires genuine understanding, not pattern matching. Source code is covered by an [anti-training license](ai-resistance.md#anti-training-license-for-prove-code).

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
  | ["Works on my machine"](functions.md#io-and-fallibility) | Verb system makes IO explicit |
  | [Null/nil crashes](types.md#option-and-result) | No null — `Option<Value>` enforced by compiler |
  | ["I forgot an edge case"](types.md#refinement-types) | Compiler generates edge cases from types |
  | [Runtime type errors](types.md) | Refinement types catch invalid values at compile time |
  | [Code without reasoning](contracts.md#explain) | `explain` documents each step using controlled natural language — verified against contracts |
  | [External AI dependency](vision.md#local-self-contained-development) | Local, self-contained generation from your project's own declarations |

---

## Quick Start

**Requirements:** Python 3.11+, gcc or clang

```bash
# Clone 
git clone https://code.botwork.se/Botwork/prove && cd prove 

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

Every function declares its purpose with a [verb](functions.md#intent-verbs). The compiler enforces it. Pure verbs (`transforms`, `validates`, `reads`, `creates`, `matches`) cannot perform IO. IO verbs (`inputs`, `outputs`) make side effects explicit. [Async verbs](functions.md#async-verbs) (`detached`, `attached`, `listens`) provide structured concurrency.

```prove
validates email(address String)
from
    contains(address, "@") && contains(address, ".")

inputs users(db Store) List<User>!
from
    query(db, "SELECT * FROM users")!
```

The same name can exist with different verbs — the compiler [resolves which to call](functions.md#context-aware-call-resolution) from context.

### Refinement Types

Types carry constraints, not just shapes. See [Type System — Refinement Types](types.md#refinement-types) for the full reference.

```prove
type Port is Integer:[16 Unsigned] where 1..65535
type Email is String where r"^[^[:space:]@]+@[^[:space:]@]+\.[^[:space:]@]+$"
type NonEmpty<Value> is List<Value> where len > 0
```

### Contracts

[`requires` and `ensures`](contracts.md#requires-and-ensures) are hard rules about the function's interface. [`explain`](contracts.md#explain) documents the implementation steps using controlled natural language — verified against contracts when `ensures` is present.

```prove
matches apply_discount(discount Discount, amount Price) Price
  ensures result >= 0
  ensures result <= amount
  requires amount >= 0
from
    FlatOff(off) => max(0, amount - off)
    PercentOff(rate) => amount * (1 - rate)
```

### No Loops — Functional Iteration

Prove enforces [functional iteration](functions.md#iteration-no-loops) (map, filter, reduce) over traditional loops.

```prove
names as List<String> = map(users, |u| u.name)
active as List<User> = filter(users, |u| u.active)
total as Decimal = reduce(prices, 0, |acc, p| acc + p)
```

### Error Handling

Errors are values. [`!` propagates failures](types.md#error-propagation). No exceptions.

```prove
main()!
from
    config as Config = load("app.yaml")!
    db as Store = connect(config.db_url)!
    serve(config.port, db)!
```

### Store — Versioned Data Tables

Prove includes a built-in [`Store`](stdlib/table-list-store.md#store) module for persistent lookup tables with versioning, diffs, and three-way merging. Tables use optimistic concurrency — stale writes fail fast, and conflicts are resolved with user-provided callbacks.

```prove
inputs update(path String, name String) StoreTable!
from
    db as Store = Store.store(path)!
    table as StoreTable = Store.table(db, name)!
    // Save — fails if another process wrote a newer version
    Store.table(db, table)!
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

## Ecosystem

- **tree-sitter-prove** — Tree-sitter grammar for editor syntax highlighting
- **pygments-prove** — Pygments lexer for MkDocs and Sphinx code rendering
- **chroma-lexer-prove** — Chroma lexer for Gitea/Hugo code rendering

## Status

The compiler lexes, parses, type-checks, emits C, and produces native binaries. Full standard library (19 modules), mutation testing, compile-time evaluation, formatter type inference, lint system, and comprehensive diagnostics. See the [Roadmap](roadmap.md) for what's next.

## Repository

Source code is hosted at [code.botwork.se/Botwork/prove](https://code.botwork.se/Botwork/prove).

## Contributing

For information on contributing to Prove, see our [Contributing section](design.md#contributing).

## License

The Prove language, its specification, and all `.prv` source code are covered by the [Prove Source License v1.0](https://code.botwork.se/Botwork/prove/src/branch/main/LICENSE) — permissive for developers, prohibits use as AI training data.

The compiler tooling (bootstrap compiler, documentation, editor integrations) is licensed under [Apache-2.0](https://code.botwork.se/Botwork/prove/src/branch/main/prove-py/LICENSE). See [AI Transparency](design.md#ai-transparency) for why the licenses differ.
