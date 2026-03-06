# Prove

<img src="./assets/icon.png" alt="Prove" width="100" height="100">

**An intent-first programming language designed to mitigate AI slop and code scraping.**

Prove is an intent-first programming language — every function declares its purpose (verb), guarantees (contracts), and reasoning (explain) before the implementation begins, and the compiler enforces that intent matches reality. If it compiles, the author understood what they wrote. If it's AI-generated, it won't.

> **TL;DR — If AI wrote your code, Prove won't compile it.**

```prove
transforms add(a Integer, b Integer) Integer
  requires valid integer(a) && valid integer(b) 
  ensures result == a + b
  explain
      sum of a and b
from
    a + b
```

`ensures` generates property tests. `transforms` guarantees purity. `explain` documents *how* the implementation satisfies the contract. The compiler enforces all of it.

---

## Features at a glance

- **Contracts as code** — `ensures` auto-generates property tests; `requires` defines preconditions
- **Purity by default** — `transforms` marks pure functions; IO is explicit via the verb system
- **No null** — `Option<Value>` enforced by compiler; no `NullPointerException`
- **Refinement types** — Catch invalid values at compile time (`Integer where 1..65535`)
- **Self-hosting** — Prove compiles itself (V2.0 in progress)
- **Binary AST** — Output binaries can't be scraped for AI training

---

## Why Prove?

> "If it compiles, you understood what you wrote. If it's AI-generated, it won't."

| Problem | How Prove solves it |
|---|---|
| AI scrapes your code for training | Binary AST — can't be scraped, normalized, or licensed for training |
| AI slop PRs waste maintainer time | Compiler rejects code without explanations and intent |
| Tests are an afterthought | Contracts generate tests automatically — testing is in the code |
| "Works on my machine" | Verb system makes IO explicit and trackable |
| Null/nil crashes | No null — `Option<Value>` enforced by compiler |
| Edge cases slip through | Compiler generates edge cases from refinement types |
| Runtime type errors | Refinement types catch invalid values at compile time |

**Self-hosting compiler**: Prove compiles itself. That's rare — most languages can't say that.

---

## Sponsor

Prove is free and open source. If it adds value to your work, consider sponsoring:

- **GitHub Sponsors**: https://github.com/sponsors/kennedyshead
- **Direct**: Reach out at magnusknutas[at]botwork.se

---

## Quick Start

**Requirements:** Python 3.11+, gcc or clang

```bash
pip install -e ".[dev]"

prove new hello
cd hello
prove build
./build/hello

prove check               # type-check only
prove format --md         # format all .prv and prove blocks in markdown
prove test                # run auto-generated tests
prove lsp                 # run the language server
prove new project-name    # Create a boilerplate
prove view path/to/.prv  # View AST file
```

---

## Documentation

Full language reference, type system, contracts, AI-resistance details, and design decisions:

**[prove.botwork.se — Docs](https://prove.botwork.se)**

---

## Toolchain

```
Source (.prv) → Lexer → Parser → Checker → Prover → C Emitter → gcc/clang → Native Binary
```

## Ecosystem

- **tree-sitter-prove** — Tree-sitter grammar for editor syntax highlighting
- **chroma-lexer-prove** — Chroma lexer for Gitea/Hugo code rendering
- pygments-prove — Pygments lexer

## Development

```bash
pip install -e ".[dev]"

python -m pytest tests/ -v    # run tests
ruff check src/ tests/        # lint
mypy src/                     # type check
```

## Repository & Access

Source code is hosted at [code.botwork.se/Botwork/prove](https://code.botwork.se/Botwork/prove).

Contributors welcome — reach out to magnusknutas[at]botwork.se for access.

## AI Transparency

The Prove language — its syntax, semantics, type system, verb model, contract
system, and all novel design ideas — is entirely human-invented.

AI tools (various LLMs and open source models) have been used as implementation
aids for the tooling surrounding the language: the Python bootstrap compiler,
C runtime, documentation, and editor integration (tree-sitter grammar, Pygments
and Chroma lexers). No single AI tool is credited — multiple have been used
across the project's development as conceptual partners and coding assistants.
All prove source code is written by human and no AI.

Once the compiler is self-hosted (V2.0), AI involvement will be limited to
documentation, lexers and conceptual discussion.

This distinction is reflected in the licensing: the language itself is covered
by the Prove Source License (which prohibits AI training use), while the
AI-assisted tooling is licensed under Apache-2.0.

## License

This repository contains sub-projects under different licenses:

| Project | License | Why |
|---------|---------|-----|
| **Language spec & .prv code** | [Prove Source License v1.0](LICENSE) | Human-authored language; prohibits AI training use |
| **prove-py/** (bootstrap compiler) | [Apache-2.0](prove-py/LICENSE) | AI-assisted tooling |
| **docs/** | [Apache-2.0](docs/LICENSE) | AI-assisted documentation |
| **tree-sitter-prove/** | [Apache-2.0](tree-sitter-prove/LICENSE) | AI-assisted editor integration |
| **pygments-prove/** | [Apache-2.0](pygments-prove/LICENSE) | AI-assisted editor integration |
| **chroma-lexer-prove/** | [Apache-2.0](chroma-lexer-prove/LICENSE) | AI-assisted editor integration |

The root [LICENSE](LICENSE) (Prove Source License v1.0) covers the Prove
language, its specification, and any `.prv` source files not covered by a
sub-project license.
