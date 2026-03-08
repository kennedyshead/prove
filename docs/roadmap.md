---
title: Roadmap - Prove Programming Language
description: Prove language roadmap including V1.0 and V2.0 milestones, self-hosting compiler, and ecosystem development.
keywords: Prove roadmap, language roadmap, self-hosted compiler
---

# Roadmap

## Versioning

- **V1.0** — Fully featured Python compiler. All language features specified and
  implemented, comprehensive standard library, complete tooling (formatter, LSP,
  testing, mutation testing). This is the reference implementation.
- **V2.0** — Self-hosted compiler. The exact same language and feature set, but
  the compiler is written in Prove and compiled by the V1.0 Python bootstrap.

The Python compiler remains as the bootstrap for V2.0. V2.0 planning begins
after V1.0 is stable.

---

## Version History

| Version | Description |
|---------|-------------|
| v0.1 | Core pipeline — lexer, parser, checker, prover, C emitter, native binaries |
| v0.2 | ASM backend reference implementation (x86_64, archived) |
| v0.3 | Legacy stdlib cleanup, `List` module |
| v0.4 | Pure verbs, binary types, namespaced calls, channel dispatch |
| v0.5 | Turbo runtime — arena allocator, fast hash, string intern |
| v0.6 | Core stdlib — Character, Text, Table — 440 tests |
| v0.7 | IO extensions, Parse, C FFI — 484 tests |
| v0.8 | Formatter type inference |
| v0.8.1 | Lint system overhaul — diagnostic code splits, doc links, Suggestions |
| v0.8.2 | `proof` → `explain` migration |
| v0.8.3 | Remaining lints (E316, E317, W302, W303, W323, W326) — 506 tests |
| v0.9 | Lexer export tool — 612 tests |
| v0.9.1 | Documentation parity — mark unimplemented features, add missing diagnostics |
| v0.9.5 | Auto-Memoization + Memory Regions |
| v0.9.6 | Mutation Testing, Stdlib: List, Math, Convert |
| v0.9.7 | Stdlib: Path, Pattern |
| v0.9.8 | Stdlib: Format, Error |
| v0.9.9 | Stdlib: Random, Time, Bytes, Hash; Format + Parse extensions |

All versions above are complete. Current version: **v0.9.9**.

---

## Remaining for V1.0

These features are partially implemented or parsed-only and need to be completed
before V1.0 can ship.

### Comptime Execution

The compile-time interpreter exists and handles constant folding of pure
function calls. Remaining work:

- Wire `comptime { ... }` blocks for full execution in user code
- Build dependency tracking (files read via comptime become rebuild triggers)
- Comptime match for conditional compilation

### Linear Types and Ownership

Basic use-after-move detection and `Own`/`Mutable` modifiers are implemented.
Remaining work:

- Assignment moves (`x = y` where y is `Own`)
- Nested and return-position moves
- Comprehensive borrow inference across function bodies

### Memory Regions

The region runtime (`prove_region.c`) exists and is initialized. Remaining work:

- Per-function region scoping (currently only wraps `main`)
- Route temporary allocations through `prove_region_alloc`

### AI-Resistance Enforcement

Keywords `domain`, `temporal`, `invariant_network`, `why_not`, `chosen`, and
`intent` are parsed into the AST. Remaining work:

- Fix incomplete parsing that causes spurious linting errors
- Temporal effect ordering verification across call graphs
- Invariant network constraint checking
- Counterfactual plausibility verification

### C Runtime Test Coverage

Four stdlib modules lack dedicated C runtime test files:

- Time, Random, Hash, Bytes

### Optimizer Passes

Three documented passes are not yet implemented:

- Iterator fusion (`map(filter(...))` → single pass)
- Copy elision (avoid copies when source not reused)
- Match to jump tables (efficient decision trees)

---

## Post-V1.0 Roadmap

Future work planned after V1.0 is stable. Listed in dependency order — each
item builds on the ones above it.

### 1. User-Facing Lookup Modifier

Expose `type Name:[Lookup]` syntax for user code (currently `binary` keyword
is stdlib-only). No new runtime work — reuses existing lookup table emission.

**Docs impact:** `types.md`, `syntax.md`

### 2. Database Stdlib

General-purpose stdlib module for managing `:[Lookup]` tables at runtime.
Storage, versioning, diffs, three-way merge with user-provided conflict
resolution. Depends on the Lookup modifier.

**Docs impact:** `stdlib.md`

### 3. Compiler CLI Extensions

`prove compiler --load` and `--dump` for converting between `.prv` lookup
tables and compiled binaries. Depends on the Lookup modifier.

**Docs impact:** `cli.md`

### 4. Async Verb Family

Three new verbs for structured concurrency: `detached` (fire-and-forget),
`attached` (spawn and await), `listens` (loop until exit). The `&` marker
at call sites, analogous to `!` for fallibility. Independent of the database
work — can be implemented in parallel.

**Docs impact:** `syntax.md`, `types.md`

### 5. Dynamic Self-Modifying Lookup

Programs that modify their own lookup tables at runtime using the Database
stdlib, recompile, and call the new binary. Depends on the Database stdlib
and async verbs.

**Docs impact:** `compiler.md`, `stdlib.md`

### 6. Self-Hosted Compiler (V2.0)

Rewrite the Prove compiler in Prove and compile it with the V1.0 Python
bootstrap:

1. Python compiler compiles compiler `.prv` source to a native binary.
2. That binary compiles the same source again.
3. If both produce identical output, the compiler is self-hosting.

The self-hosted compiler will be architecturally different from the Python
version — Prove's algebraic types and pattern matching naturally replace
Python's class hierarchies and `isinstance` dispatch.

---

## Ecosystem

| Project | Description |
|---------|-------------|
| [tree-sitter-prove](https://code.botwork.se/Botwork/tree-sitter-prove) | Tree-sitter grammar for editor syntax highlighting |
| [pygments-prove](https://code.botwork.se/Botwork/pygments-prove) | Pygments lexer for MkDocs and Sphinx code rendering |
| [chroma-lexer-prove](https://code.botwork.se/Botwork/chroma-lexer-prove) | Chroma lexer for Gitea and Hugo code rendering |

Starting with v0.9, the `scripts/export-lexers.py` script keeps all three lexer projects
in sync with the compiler's canonical keyword lists automatically.
