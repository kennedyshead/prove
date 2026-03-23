---
title: Roadmap - Prove Programming Language
description: Prove language roadmap with feature status and milestones.
keywords: Prove roadmap, language roadmap, self-hosted compiler
---

# Roadmap

## Versioning

Features use status labels rather than version numbers:

- **Proposed** — Designed, not yet built.
- **Exploring** — Idea stage, no commitment.

Two milestones frame the overall project:

- **V1.0** — Fully featured Python compiler. All language features implemented,
  comprehensive standard library, complete tooling. The reference implementation. **Released.**
- **V2.0** — Self-hosted compiler written in Prove, compiled by the V1.0 bootstrap.

V1.0 has shipped. V2.0 planning is underway.

---

## Released

### V1.1 — March 2026

Structured concurrency, terminal UI, GUI, and the `proof` CLI wrapper.

- `attached`, `detached`, `listens`, and `renders` async verbs with `prove_coro` stackful coroutines
- Terminal, UI, and Graphic stdlib modules (TUI via ANSI, GUI via SDL2 + Nuklear)
- `proof` CLI — unified binary: `proof check`, `proof build`, `proof test`, `proof format`, `proof new`
- Compound assignment operators (`+=`, `-=`, `*=`, `/=`), `constants` import verb, `LookupPattern` matching
- Cross-platform release pipeline with `curl | sh` installer (Linux x86_64, macOS aarch64)
- Go-to-definition in the LSP (local vars, params, imports, cross-file)
- Tree-sitter and Pygments grammar updates for async verbs and constants
- 22 stdlib modules total (added Terminal, UI, Graphic)

### V1.0 — March 2026

The Python bootstrap compiler is complete and released as the reference implementation.

- Full compiler pipeline: lex → parse → type-check → emit C → native binary
- 19 stdlib modules (plus aliases): Character, Text, Table, Array, System, Parse, Math, Types, List, Path, Pattern, Format, Random, Time, Bytes, Hash, Log, Network, Language
- Checker with refinement types, contracts (`requires`/`ensures`/`explain`/`know`/`assume`/`believe`), intent coverage
- 13-pass AST optimizer (TCO, dead code elimination, iterator fusion, memoization, escape analysis, etc.)
- LSP with ML-powered n-gram completions and intent-driven stub generation
- Mutation testing, compile-time evaluation, formatter, lint/diagnostics system
- CI/CD pipeline with automated builds, tests, and releases

---

## Proposed

### V1.2 — Package Manager

Pure-Prove package distribution via AST-level sharing in SQLite archives.

- Package format: `.prvpkg` files (SQLite databases) containing typed AST, module signatures, and comptime-resolved assets
- `prove package` CLI: `init`, `add`, `remove`, `install`, `publish`, `list`, `clean`
- `[dependencies]` section in `prove.toml` with `prove.lock` lockfile
- Static HTTP registry — no git dependency, pure Python stdlib (`sqlite3`, `urllib`)
- Flat dependency resolution (one version per package name across the tree)
- String-interned binary AST format for compact storage
- SQL-based AST migrations for cross-compiler-version compatibility
- Purity validation on publish: no `foreign` blocks, all imports must resolve to stdlib or declared dependencies
- Checker integration: package signatures loaded from exports table without full AST deserialization
- Full design: [`future/14-package-manager.md`](https://code.botwork.se/Botwork/prove/src/branch/main/future/14-package-manager.md)

### V1.2 — Sqlite Stdlib

General-purpose SQLite database access with cursor-based iteration.

- `Database`, `Statement`, `Cursor`, `Row` types
- Parameterized queries (SQL injection prevention by design)
- Cursor iteration via lambda HOFs: `each(rows, |row| column(row, "name")!)`
- Transactions, WAL mode, prepared statements
- SQLite amalgamation vendored (public domain, no external dependency)
- Full design: [`future/15-sqlite-stdlib.md`](https://code.botwork.se/Botwork/prove/src/branch/main/future/15-sqlite-stdlib.md)

---

## Exploring

The items below build toward Prove's [vision](vision.md) of local, self-contained development — where the project's own declarations drive code generation without external services.

### Binary AST Format

Store `.prv` files as a compact binary AST instead of human-readable text. The `prove` CLI provides views and the LSP decodes on the fly. Web scrapers and training pipelines see binary blobs, not parseable source code.

### Semantic Normalization

Canonicalize all code before storage. Variable names, declaration ordering, whitespace, and stylistic choices are normalized away. A name map is stored alongside the canonical AST. The LSP reconstructs human-readable code on demand.

### Fragmented Source

Distribute a function's complete definition across multiple files — implementation, explanations, intent declarations, near-miss examples, and narrative. All files are required to compile. No single artifact is useful in isolation.

### Identity-Bound Compilation

Source files carry a cryptographic signature chain. The compiler verifies authorship. Scraped code with stripped signatures won't compile.

### Project-Specific Grammars

Each project can define syntactic extensions via `prove.toml`. Two Prove projects may look completely different at the surface level, destroying the statistical regularities that AI training depends on.

### Semantic Commit Verification

The compiler diffs the previous version, reads the commit message, and verifies the change actually addresses the described bug. Vague messages like "fix stuff" don't compile.

### Self-Hosted Compiler (V2.0)

Rewrite the compiler in Prove. The V1.0 Python bootstrap compiles it,
the resulting binary recompiles itself, and both outputs must match.

---

## Ecosystem

| Project | Description |
|---------|-------------|
| [tree-sitter-prove](https://code.botwork.se/Botwork/tree-sitter-prove) | Tree-sitter grammar for editor syntax highlighting |
| [pygments-prove](https://code.botwork.se/Botwork/pygments-prove) | Pygments lexer for MkDocs and Sphinx code rendering |
| [chroma-lexer-prove](https://code.botwork.se/Botwork/chroma-lexer-prove) | Chroma lexer for Gitea and Hugo code rendering |

The `scripts/export-lexers.py` script keeps all three lexer projects in sync
with the compiler's canonical keyword lists automatically.
