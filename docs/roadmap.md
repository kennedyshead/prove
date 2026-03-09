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
| v0.8.3 | Remaining lints (E316, E317, I302, I303, W323, W326) — 506 tests |
| v0.9 | Lexer export tool — 612 tests |
| v0.9.1 | Documentation parity — mark unimplemented features, add missing diagnostics |
| v0.9.5 | Auto-Memoization + Memory Regions |
| v0.9.6 | Mutation Testing, Stdlib: List, Math, Types |
| v0.9.7 | Stdlib: Path, Pattern |
| v0.9.8 | Stdlib: Format, Error |
| v0.9.9 | Stdlib: Random, Time, Bytes, Hash; Format + Parse extensions |

All versions above are complete. Current version: **v0.9.9**.

---

## Remaining for V1.0

Features that are partially implemented or have remaining gaps. Items marked
*(done)* were completed during the v0.9.x cycle.

### Comptime Execution *(done)*

`comptime` expressions work in any position — variable declarations, function
bodies, etc. The tree-walking interpreter evaluates pure constant expressions
and `read()` for file I/O. Results are inlined as C constants at compile time.

Remaining polish:

- Build dependency tracking (files read via comptime `read()` should trigger rebuilds)
- Comptime match for conditional compilation (documented but not verified end-to-end)

### Linear Types and Ownership *(done)*

Move tracking covers assignment, nested calls, pipe expressions, field paths,
and return position. Borrow inference active for read-only parameters.

### Memory Regions *(done)*

Per-function region scoping with `prove_region_enter/exit` in all functions.
String and list literals use region allocation inside functions; return-position
values use malloc to prevent dangling pointers (escape analysis).

### AI-Resistance Enforcement *(mostly done)*

- Parsing complete for all keywords (`domain`, `temporal`, `invariant_network`,
  `why_not`, `chosen`, `intent`)
- Domain profiles enforced (W340–W342), coherence checking active
- Temporal effect ordering enforced (W390)
- Invariant network constraints type-checked (E396) with W391 when no `ensures`

Remaining:

- Counterfactual annotations (`why_not`/`chosen`) — parsed but no semantic checking
- Formal invariant network verification (constraint expressions validated
  syntactically, not proven against implementations)

### C Runtime Test Coverage *(done)*

All 16 stdlib modules now have dedicated C runtime test files.

### Optimizer Passes *(done)*

All documented passes implemented: iterator fusion, copy elision, match to
jump tables, plus tail call optimization, dead branch elimination, small
function inlining, dead code elimination, memoization candidates, and
match compilation.

### Remaining Gaps

| Feature | Status | Priority |
|---------|--------|----------|
| Verification chain propagation | `ensures` stats reported but no per-call-site warnings | Low |
| Formal `know` proofs | Lightweight `ClaimProver` (constants, algebraic identities); no general proof | Low |
| `par_map` concurrency | Runtime scaffolding exists; not callable from user code | Low (may defer) |
| Row polymorphism | Mentioned in `types.md`; not implemented | Low |
| Lint fixes | I367/I320 thresholds, unused constant detection, module struct return validation | Medium |

---

## Post-V1.0 Roadmap

Future work planned after V1.0 is stable. Listed in dependency order — each
item builds on the ones above it.

### 1. User-Facing Lookup Modifier *(implemented)*

`type Name:[Lookup]` syntax for user code with multi-column support.
No new runtime work — reuses existing lookup table emission.

### 2. Async Verb Family *(implemented)*

Three verbs for structured concurrency: `detached` (fire-and-forget),
`attached` (spawn and await), `listens` (loop until exit). The `&` marker
at call sites, analogous to `!` for fallibility. Lexer, parser, checker,
and C emitter support is complete. Runtime backed by `prove_coro`.

### 3. IO Improvement — `streams` Verb

A `streams` verb for the IO family, mirroring `listens` in the async family.
Loops over an IO source with exit-via-match-arm semantics. Completes the
verb family symmetry:

| Pattern | IO | Async |
|---------|-----|-------|
| Push, move on | `outputs` | `detached` |
| Pull, await | `inputs` | `attached` |
| Loop until exit | `streams` | `listens` |

Also includes renaming `InputOutput` module to `System` to reflect its full
scope (files, processes, stdin/stdout, environment).

### 4. Network Stdlib

New `Network` module for TCP and UDP communication. Uses IO verbs for blocking
operations and async verbs for non-blocking. Depends on the `streams` verb for
accept loops and message streaming.

### 5. Database Stdlib

General-purpose stdlib module for managing `:[Lookup]` tables at runtime.
Storage, versioning, diffs, three-way merge with user-provided conflict
resolution. Depends on the Lookup modifier.

### 6. Compiler CLI Extensions

`prove compiler --load` and `--dump` for converting between `.prv` lookup
tables and compiled binaries. Depends on the Lookup modifier.

### 7. Dynamic Self-Modifying Lookup

Programs that modify their own lookup tables at runtime using the Database
stdlib, recompile, and call the new binary. Depends on the Database stdlib
and async verbs.

### 8. Self-Hosted Compiler (V2.0)

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
