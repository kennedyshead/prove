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

- Counterfactual annotations (`why_not`/`chosen`) — parsed but no semantic checking
- Formal invariant network verification — validated syntactically, not proven

### Comptime Polish

Core `comptime` works in all positions. Remaining:

- Build dependency tracking for `comptime read()`
- Comptime match for conditional compilation

### Lint Gaps

- I367/I320 thresholds, unused constant detection, module struct return validation

---

## Proposed

### `streams` Verb

IO verb mirroring `listens` in the async family. Loops over an IO source with
exit-via-match-arm semantics. Completes verb family symmetry:

| Pattern | IO | Async |
|---------|-----|-------|
| Push, move on | `outputs` | `detached` |
| Pull, await | `inputs` | `attached` |
| Loop until exit | `streams` | `listens` |

### Network Stdlib

`Network` module for TCP/UDP. IO verbs for blocking, async verbs for
non-blocking. Depends on `streams` for accept loops.

### Store Stdlib

Runtime management of `:[Lookup]` tables. Storage, versioning, diffs,
three-way merge with user-provided conflict resolution.

### Compiler CLI Extensions

`prove compiler --load` and `--dump` for converting between `.prv` lookup
tables and compiled binaries.

### Self-Hosted Compiler (V2.0)

Rewrite the compiler in Prove. The V1.0 Python bootstrap compiles it,
the resulting binary recompiles itself, and both outputs must match.

---

## Exploring

### Dynamic Self-Modifying Lookup

Programs that modify their own lookup tables at runtime, recompile, and
call the new binary. Depends on Store stdlib and async verbs.

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
