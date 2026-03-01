# Prove

<img src="../assets/icon.png" alt="Prove" width="100" height="100">

A statically typed programming language that compiles to native code via C.

> "If it compiles, it ships."

Prove features intent verbs, contracts-as-tests, refinement types, proof
obligations, and AI-resistance mechanisms. The compiler is your co-author,
not your gatekeeper.

**Repository:** [code.botwork.se/Botwork/prove](https://code.botwork.se/Botwork/prove)

## Quick Start

```bash
pip install -e ".[dev]"

prove new myproject
cd myproject
prove build
prove test
```

## Commands

```bash
prove new <name>       # scaffold a new project
prove build [path]     # compile .prv to native binary
prove check [path]     # type-check without compiling
prove test [path]      # generate and run contract tests
```

## Language Features

- **Intent verbs** — `transforms`, `validates`, `inputs`, `outputs`
  encode what a function *does*, not just its type
- **Contracts** — `ensures`, `requires`, `believe` declare guarantees;
  `proof` blocks explain *why* they hold
- **Refinement types** — `type Price is Decimal where >= 0`
- **Near-miss testing** — `near_miss: 10 => false` proves you
  understand the boundaries
- **Epistemic annotations** — `know`, `assume`, `believe` express
  certainty levels
- **Counterfactual reasoning** — `why_not` / `chosen` document
  rejected alternatives

## Diagnostic Codes

### Errors (block compilation)

| Code | Meaning |
|------|---------|
| E390 | `ensures` without `proof` block |
| E391 | duplicate proof obligation name |
| E392 | proof obligations < ensures count |
| E393 | `believe` without `ensures` |

### Warnings

| Code | Meaning |
|------|---------|
| W321 | proof text doesn't reference function concepts |
| W322 | duplicate near-miss inputs |
| W324 | `ensures` without `requires` |

## Configuration

Projects use `prove.toml`:

```toml
[package]
name = "myproject"
version = "0.1.0"

[build]
target = "native"
optimize = false

[test]
property_rounds = 1000

[style]
line_length = 90
```

## Development

```bash
python -m pytest tests/ -v    # run tests
ruff check src/ tests/        # lint
mypy src/                     # type check
```

## Repository & Access

Source code is hosted at [code.botwork.se/Botwork/prove](https://code.botwork.se/Botwork/prove).

The Gitea instance is a paid service for issue creators. Developers who want contributor access can reach out to magnusknutas&#x5B;at&#x5D;botwork&#x2E;se.

## License

Prove Source License v1.0 — permissive use with AI training prohibition.
