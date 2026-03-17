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
  comprehensive standard library, complete tooling. The reference implementation.
- **V2.0** — Self-hosted compiler written in Prove, compiled by the V1.0 bootstrap.

V1.0 ships when the language is mature. V2.0 planning begins after.

---

## Proposed

---

## Exploring

The items below build toward Prove's [vision](vision.md) of local, self-contained development — where the project's own declarations drive code generation without external services.

### `Scale:N` Modifier Enforcement

The `Decimal:[Scale:N]` modifier is parsed and stored but not enforced. Static literal
rejection for refinements (e.g., `Integer where != 0`) is already implemented (E355).
What remains: validate that decimal literals assigned to `Decimal:[Scale:N]` have
at most N decimal places, emit rounding code for arithmetic results, and check
type compatibility between different Scale values.
See `future/06-refinement-static-rejection.md`.

### Closure Capture for HOF Callbacks

All HOF callbacks (`map`, `filter`, `reduce`, `each`, `par_map`, `par_filter`,
`par_reduce`, `par_each`) require named functions — inline lambdas with captured
bindings are not yet supported. Phase 1: sequential lambdas with stack-allocated
capture structs. Phase 2: parallel lambdas with region-allocated capture structs
and mutability enforcement. See `future/09-parallel-closures.md`.

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
