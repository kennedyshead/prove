---
title: Roadmap - Prove Programming Language
description: Prove language roadmap with feature status and milestones.
keywords: Prove roadmap, language roadmap, self-hosted compiler
---

# Roadmap

## Versioning

Features use status labels rather than version numbers:

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

### Row Polymorphism

Structural subtyping for record types via the `Struct` builtin type and `with` field constraints.

### Parallel Higher-Order Functions

`par_map`, `par_filter`, and `par_reduce` execute pure higher-order operations in parallel
using a thread pool. The runtime auto-detects available cores. Only pure verbs
(`transforms`, `validates`, `reads`, `creates`, `matches`) are accepted as callbacks —
IO and async verbs are rejected at compile time. Closure support (capturing outer bindings)
is not yet implemented.

### Verification Chain Propagation

`W370` warns when a public function calls verified code (functions with `ensures` clauses)
but has no `ensures` of its own, breaking the verification chain. `W371` (enabled with
`--strict`) extends the warning to internal functions.

---

## Proposed

---

## Exploring

The items below build toward Prove's [vision](vision.md) of local, self-contained development — where the project's own declarations drive code generation without external services.

### Formal `know` Proofs

Extended proof engine beyond the current implementation. Phases 1–3 are done
(`ProofContext`, assumption matching, arithmetic reasoning). Phases 4–5 remain:
callee `ensures` propagation and match-arm path narrowing.

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
