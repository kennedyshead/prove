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

### `intent:` Prose Consistency Check

Function-level `intent:` annotations are parsed and W311 fires when declared
without `ensures`/`requires`, but the prose text is not yet checked against
the function body. A new diagnostic (W313) should warn when the `intent:`
description has no vocabulary overlap with called function names, parameter
names, or type names in the body — using the same `prose_overlaps` /
`body_tokens` infrastructure already powering the W501–W505 narrative checks.
A longer-term extension links `intent:` to the refutation challenge engine
(W503–W506). See `future/03-intent-annotation-enforcement.md`.

### Adversarial Tests for `believe`

`believe` claims are type-checked and usable as proof context assumptions, but
generate no tests. The plan: emit a runtime assertion for each `believe` in
debug builds (parallel to `assume`) and include `believe` clauses as
falsification targets in `prove test` — reported as advisories by default,
failures under `--strict`. See `future/03-intent-annotation-enforcement.md`.

### `explain` Block Semantic Verification

`why_not` and `chosen` are parsed and stored but not checked against the function
body — any prose is accepted. `narrative` blocks are required and structurally
valid, but `flow:` step names are not checked against defined functions.
Plan: W314/W315 for `why_not`/`chosen` with no symbol overlap; W341 for
`narrative flow:` steps referencing undefined functions.
See `future/05-explain-verification.md`.

### Refinement Type Static Enforcement

The compiler inserts runtime guards at IO boundaries but does not yet reject
provably-invalid literals at compile time (e.g., passing `0` to
`Integer where != 0`). The `Scale:N` modifier is parsed but not enforced.
See `future/06-refinement-static-rejection.md`.

### Memory — Per-Function Region Scoping and `Own` Tracking

`prove_region_enter/exit` is emitted for all functions; a `_needs_region_scope()`
analysis pass would skip it for non-allocating functions. Use-after-move detection
(`Own` modifier) marks moved variables but does not yet emit an error when they are
referenced after the move. See `future/08-memory-ownership.md`.

### Closure Capture for HOF Callbacks

All HOF callbacks (`map`, `filter`, `reduce`, `each`, `par_map`, `par_filter`,
`par_reduce`, `par_each`) require named functions — inline lambdas with captured
bindings are not yet supported. Phase 1: sequential lambdas with stack-allocated
capture structs. Phase 2: parallel lambdas with region-allocated capture structs
and mutability enforcement. See `future/09-parallel-closures.md`.

### `know` Claims Inside Match Arms

`know` claims are function-level. The match arm structural bindings are recorded
in the proof context but `know` cannot yet be written inside an arm body to
reference the locally-bound variant variable. See `future/10-match-arm-know.md`.

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
