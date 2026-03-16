---
title: Roadmap - Prove Programming Language
description: Prove language roadmap with feature status and milestones.
keywords: Prove roadmap, language roadmap, self-hosted compiler
---

# Roadmap

## Versioning

Features use status labels rather than version numbers:

- **Stable** — Shipped, tested, documented.
- **Preview** — Implemented but may change.
- **Proposed** — Designed, not yet built.
- **Exploring** — Idea stage, no commitment.

Two milestones frame the overall project:

- **V1.0** — Fully featured Python compiler. All language features implemented,
  comprehensive standard library, complete tooling. The reference implementation.
- **V2.0** — Self-hosted compiler written in Prove, compiled by the V1.0 bootstrap.

V1.0 ships when the language is mature. V2.0 planning begins after.

---

## Stable

### Runtime Check Optimization

Compiler-first coordination of safety checks between the compile step and the C runtime.
Four items following the compiler-first principle:

- **Dead null guards** — Removed defensive `!ptr` checks from HOF, parallel map, random,
  and sort runtime functions for types that Prove's type system guarantees are never null.
- **Region scope elision** — `_needs_region_scope()` analysis skips `prove_region_enter/exit`
  for functions whose body contains no allocating calls.
- **Division by zero** — Constant zero divisors are compile errors (E357). Variable
  divisors without a `requires` contract get a runtime guard behind `#ifndef PROVE_RELEASE`.
  Divisors covered by `requires param != 0` elide the guard entirely.
- **Refinement type IO enforcement** — Refinement panics in pure functions are wrapped in
  `#ifndef PROVE_RELEASE` (stripped in release builds). IO verb functions and `main` always
  keep the guard.

### Prose Coherence Analysis

Semantic analysis of `narrative`, `explain`, `intent`, `chosen`, and `why_not` blocks
that connects natural-language prose to the actual code it describes.

**Checker (`--coherence` flag, enabled by default in LSP):**

- **W501** — function verb not implied by module narrative
- **W502** — `explain` entry text has no word overlap with the `from`-block operations
- **W503** — `chosen:` declared without any `why_not` alternatives
- **W504** — `chosen:` text doesn't correspond to any operation in the `from`-block
- **W505** — `why_not` entry mentions no known function or type name

**LSP** — coherence checks run on every save; context-aware completions inside
`narrative`, `explain`, `intent`, `chosen`, and `why_not` prose blocks; verb keyword
suggestions re-ranked by narrative when present.

Implemented in `_nl_intent.py` (pure Python, no external deps) shared by the checker
and LSP.

### Stub Generation from Narrative

`prove generate` produces function stubs from `narrative:` prose. The verb-prose
mapping (`_nl_intent.py`) extracts which verbs the narrative implies, noun
extraction identifies domain objects, and `pair_verbs_nouns` predicts parameter
types and return types. The output is function signatures with `todo`-marked
`from` blocks. `todo` is a first-class incomplete marker: the checker emits
I601, the linter reports module completeness via `--status`, and the C emitter
compiles it to a clear panic.

### Intent-Driven Body Generation

`prove generate` fills `from` blocks where the system has enough knowledge.
A function whose verb and noun match a stdlib function gets a complete body
with a direct stdlib call, plus generated `explain`, `chosen`, and `why_not`
blocks. Functions with no stdlib match remain as `todo` stubs. The stdlib
knowledge base indexes `///` docstrings for prose-to-function lookup via
`implied_functions()`. Re-running with `--update` regenerates `@generated`
functions that still have todos.

### Project Intent Declaration (`.intent` format)

`prove intent` works with `.intent` project declaration files — a human-readable
format where module blocks list verb phrases that become functions, vocabulary
defines domain concepts, flow declarations drive imports, and constraints map
to contracts. `prove intent --generate` produces `.prv` files from intent.
`prove check --intent` verifies the code stays aligned with declarations.

### Array Safe Access

Opt-in `get_safe`/`set_safe` variants that return `Option<T>` instead of producing
undefined behaviour on out-of-bounds indices. The existing unchecked `get`/`set` remain
as the fast path. Safe variants are explicitly named — the choice is visible at the
call site.

### Array HOF Operations

`map`, `reduce`, `each`, and `filter` on `Array<T>` without the boxing round-trip
through `List<Value>`. The optimizer fuses `map(map(...))`, `reduce(map(...))`, and
`filter(map(...))` into single-pass C loops via the same `_fuse_iterators_in_expr`
mechanism used for existing Sequence fusions. `filter` returns `List<Value>` because
output length is unknown at compile time — the type makes the escape explicit.

---

## Preview

### AI-Resistance Enforcement

Parsing, domain profiles (W340-W342), temporal ordering (W390), and invariant
network constraints (E396, W391) are all active. Remaining:

- Counterfactual annotations (`why_not`/`chosen`) — parsed but no semantic checking beyond W503-W505
- Formal invariant network verification — validated syntactically, not proven

### Comptime Polish

Core `comptime` works in all positions. Remaining:

- Build dependency tracking for `comptime read()`
- Comptime match for conditional compilation

### Lint Gaps

- I367/I320 thresholds, unused constant detection, module struct return validation

### Store Stdlib

Runtime management of `:[Lookup]` tables. Storage, versioning, diffs,
three-way merge with user-provided conflict resolution via
[`Verb<Conflict, Resolution>`](types.md#function-types-verb).
Store-backed lookup types (`runtime` body) allow `[Lookup]` types with
dynamic data from a `StoreTable`. Remaining:

- Schema conflict detection (addition and value conflicts implemented)
- Store spotlight in Language Tour (index.md)

### Lookup Improvements

Named columns (`probability:Float confidence:Float`) disambiguate duplicate column
types and enable `.name` field access. Binary search for large tables (>16 entries)
replaces linear scan in reverse lookups. Remaining:

- Edge cases in named column error reporting

### Compiler CLI Extensions

`prove advanced compiler --load` and `--dump` for converting between `.prv` lookup
tables and PDAT binary format. Auto-detects mode from file extension.

### Cache Indexing & Reindexing

`.prove_cache` lifecycle with manifest, warm load, and incremental re-index.
Manifest (`manifest.json` with per-file mtime/size and `cache_version`) and
`did_change` incremental re-index are implemented. Remaining:

- **CLI write-back** — `check` and `build` update the cache after running
- **`prove index`** — explicit subcommand to (re)build the cache from the command
  line, useful for CI pre-warming and post-clone setup

---

## Proposed

---

## Exploring

The items below build toward Prove's [vision](vision.md) of local, self-contained development — where the project's own declarations drive code generation without external services.

### Dynamic Self-Modifying Lookup

Programs that modify their own lookup tables at runtime, recompile, and
call the new binary. Store-backed lookup types (`runtime`) provide the
runtime data layer; subprocess recompilation provides the binary update.
Depends on Store stdlib and async verbs.

### Row Polymorphism

Structural subtyping for record types.

### `par_map` Concurrency

Runtime scaffolding exists but is not callable from user code.

### Verification Chain Propagation

Per-call-site warnings for unverified `ensures` chains.

### Formal `know` Proofs

General proof beyond the current lightweight `ClaimProver`.

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
