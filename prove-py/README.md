# Prove

<img src="../assets/icon.png" alt="Prove" width="100" height="100">

An intent-first programming language that compiles to native code via C.

> "If it compiles, it ships."

Prove features intent verbs, contracts-as-tests, refinement types, explain
entries, and AI-resistance mechanisms. The compiler is your co-author,
not your gatekeeper.

**Repository:** [code.botwork.se/Botwork/prove](https://code.botwork.se/Botwork/prove)

## Quick Start

```bash
# Install all workspace dependencies (from repo root)
../dev-setup.sh

# Or install just the compiler manually
pip install -e ".[dev]"

prove new myproject
cd myproject
prove build
prove test
```

## Commands

```bash
prove new <name>                # scaffold a new project
prove build [path]              # compile to native binary
prove check [path] [--md]       # type-check and lint
prove test [path]               # run contract tests
prove format [path] [--check]   # format source files
prove view <file>               # print AST
prove lsp                       # start language server
```

## Language Features

- **Intent verbs** encode what a function *does*, not just its type:
  - Pure: `transforms`, `validates`, `reads`, `creates`, `matches`
  - IO: `inputs`, `outputs`
- **Contracts** — `ensures`, `requires`, `believe` declare guarantees;
  `explain` blocks document *how* the implementation satisfies them
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
| E360 | `validates` has implicit Boolean return |
| E361 | pure function cannot be failable |
| E362 | pure function cannot call IO builtin |
| E363 | pure function cannot call IO function |
| E364 | lambda captures variable (closures not supported) |
| E390 | `ensures` without `explain` block |
| E391 | duplicate explain entry |
| E392 | explain entries < ensures count |
| E393 | `believe` without `ensures` |
| E394 | explain condition must be Boolean |

### Warnings

| Code | Meaning |
|------|---------|
| W321 | explain text doesn't reference function concepts |
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

## Standard Library

### InputOutput

Console and file I/O through channel dispatch:

| Verb | Channel | Signature |
|------|---------|-----------|
| `outputs` | `console` | `(text String)` |
| `inputs` | `console` | `() String` |
| `inputs` | `file` | `(path String) Result<String, Error>!` |
| `outputs` | `file` | `(path String, content String) Result<Unit, Error>!` |

## Development

```bash
# One-time setup (installs all deps)
../dev-setup.sh

# Run tests, lint, type check
python -m pytest tests/ -v
ruff check src/ tests/
mypy src/
```

## Roadmap

| Version | Focus | Status |
|---------|-------|--------|
| v0.1 | Core pipeline, contract enforcement, runtime builtins | Complete |
| v0.2 | ASM backend reference implementation (x86_64) | Complete, archived |
| v0.3 | Legacy stdlib cleanup, `List` module | Complete |
| v0.4 | Pure verbs, binary types, namespaced calls, channel dispatch | Complete |
| v0.5 | Turbo runtime: arena allocator, fast hash, string intern | Complete |
| v0.6 | Core stdlib: Character, Text, Table | Complete |
| v0.7 | IO extensions, Parse, and C FFI | Complete |
| v0.8 | Formatter type inference | Complete |
| v1.0 | Self-hosting: rewrite compiler in Prove | Planned |

## Repository & Access

Source code is hosted at [code.botwork.se/Botwork/prove](https://code.botwork.se/Botwork/prove).

The Gitea instance is a paid service for issue creators. Developers who want contributor access can reach out to magnusknutas&#x5B;at&#x5D;botwork&#x2E;se.

## AI Transparency

This bootstrap compiler is built with the help of AI tools (various LLMs and
open source models) for Python implementation, C runtime code, and
documentation. The language design, syntax, semantics, and all novel ideas are
entirely human-invented. See the [workspace README](../README.md) for full
details.

## License

[Apache-2.0](LICENSE)

The Prove language specification and `.prv` source code are covered by the
[Prove Source License v1.0](../LICENSE) at the workspace root.
