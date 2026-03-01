# Prove

<img src="./assets/icon.png" alt="Prove" width="100" height="100">

**A programming language that fights back against AI slop and code scraping.**

Prove is a strongly typed, compiler-driven language where contracts generate tests, intent verbs enforce purity, and the compiler rejects code that can't demonstrate understanding. If it compiles, the author understood what they wrote. If it's AI-generated, it won't.

```prove
transforms add(a Integer, b Integer) Integer
  ensures result == a + b
  proof
    correctness: result is the sum of a and b
from
    a + b
```

`ensures` generates property tests. `transforms` guarantees purity. `proof` explains *why* the contract holds. The compiler enforces all of it.

---

## Why Prove?

| Problem | How Prove solves it |
|---|---|
| AI scrapes your code for training | Binary AST format + anti-training license + semantic normalization |
| AI slop PRs waste maintainer time | Compiler rejects code without proof obligations and intent |
| Tests are separate from code | Contracts generate tests automatically |
| "Works on my machine" | Verb system makes IO explicit |
| Null/nil crashes | No null — `Option<T>` enforced by compiler |
| "I forgot an edge case" | Compiler generates edge cases from types |
| Runtime type errors | Refinement types catch invalid values at compile time |

---

## Quick Start

**Requirements:** Python 3.11+, gcc or clang

```bash
pip install -e ".[dev]"

prove new hello
cd hello
prove build
./build/hello

prove check    # type-check only
prove test     # run auto-generated tests
```

---

## Documentation

Full language reference, type system, contracts, AI-resistance details, and design decisions:

**[code.botwork.se/Botwork/prove — Docs](https://code.botwork.se/Botwork/prove)**

---

## Toolchain

```
Source (.prv) → Lexer → Parser → Checker → Prover → C Emitter → gcc/clang → Native Binary
```

## Ecosystem

- **tree-sitter-prove** — Tree-sitter grammar for editor syntax highlighting
- **chroma-lexer-prove** — Chroma lexer for Gitea/Hugo code rendering

## Development

```bash
pip install -e ".[dev]"

python -m pytest tests/ -v    # run tests
ruff check src/ tests/        # lint
mypy src/                     # type check
```

## Repository & Access

Source code is hosted at [code.botwork.se/Botwork/prove](https://code.botwork.se/Botwork/prove).

The Gitea instance is a paid service for issue creators. Developers who want contributor access can reach out to magnusknutas&#x5B;at&#x5D;botwork&#x2E;se.

## License

[Prove Source License v1.0](LICENSE) — permissive for developers, prohibits use as AI training data.
