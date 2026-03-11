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

## Preview

### AI-Resistance Enforcement

Parsing, domain profiles (W340-W342), temporal ordering (W390), and invariant
network constraints (E396, W391) are all active. Remaining:

- Counterfactual annotations (`why_not`/`chosen`) — parsed but no semantic checking (see *Prose Coherence Analysis* below)
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

---

## Proposed

### Compiler CLI Extensions

`prove compiler --load` and `--dump` for converting between `.prv` lookup
tables and compiled binaries.

### Cache Indexing & Reindexing

Reliable `.prove_cache` lifecycle across all commands and the LSP.

The project indexer (used for ML completion ranking) writes a PDAT binary cache to
`.prove_cache/` but never reads it back — every LSP session re-parses all source files
from scratch, and CLI commands (`check`, `build`, `format`) ignore the cache entirely.

Planned work:

- **Manifest** — `manifest.json` alongside the PDAT files, recording per-file mtime/size
  and a `cache_version` integer. Staleness is detected by comparing against live filesystem.
- **Warm load** — `_ProjectIndexer.load()` restores in-memory tables from PDAT on a valid
  cache, avoiding full re-parse at LSP startup.
- **`did_change` patch** — incremental re-index on every edit, not just on save, so
  completions reflect unsaved content.
- **CLI write-back** — `check` and `build` update the cache after running (reusing the
  parse already done). `format` patches changed files.
- **`prove index`** — new explicit subcommand to (re)build the cache from the command
  line, useful for CI pre-warming and post-clone setup.

### Prose Coherence Analysis

Semantic analysis of `narrative`, `explain`, `intent`, `chosen`, and `why_not` blocks
that connects natural-language prose to the actual code it describes.

**Checker (`--coherence` flag):**

- **W501** — function verb not implied by module narrative
  (e.g. a `transforms` function in a module whose narrative only describes reading)
- **W502** — `explain` entry text has no word overlap with the `from`-block operations
  (catches stale prose after refactoring)
- **W503** — `chosen:` declared without any `why_not` alternatives
- **W504** — `chosen:` text doesn't correspond to any operation in the `from`-block
  (catches copy-paste or stale rationale)
- **W505** — `why_not` entry mentions no known function or type name
  (enforces that rejected alternatives are anchored to something real, not vague)

**LSP (always active, shown as hints in editor):**

- Coherence checks run on every save, surfacing W501–W505 as warnings
- Context-aware completions inside prose blocks:
  - `narrative` — verb synonyms and function names from the module
  - `explain` — param names and called-function names from the body
  - `intent` — param names, return type, phrase starters
  - `chosen` — body operation names, verb synonyms, approach-phrase starters ("X because")
  - `why_not` — function and type names from the module scope, algorithmic alternative phrases
- When a `narrative` exists, verb keyword suggestions at function-declaration sites
  are re-ranked to surface verbs implied by the narrative first

Implemented in a new `_nl_intent.py` utility (pure Python, no external deps) shared
by the checker and LSP.

### Self-Hosted Compiler (V2.0)

Rewrite the compiler in Prove. The V1.0 Python bootstrap compiles it,
the resulting binary recompiles itself, and both outputs must match.

---

## Exploring

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

---

## Ecosystem

| Project | Description |
|---------|-------------|
| [tree-sitter-prove](https://code.botwork.se/Botwork/tree-sitter-prove) | Tree-sitter grammar for editor syntax highlighting |
| [pygments-prove](https://code.botwork.se/Botwork/pygments-prove) | Pygments lexer for MkDocs and Sphinx code rendering |
| [chroma-lexer-prove](https://code.botwork.se/Botwork/chroma-lexer-prove) | Chroma lexer for Gitea and Hugo code rendering |

The `scripts/export-lexers.py` script keeps all three lexer projects in sync
with the compiler's canonical keyword lists automatically.
