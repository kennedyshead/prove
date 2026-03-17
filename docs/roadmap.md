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

### `par_each` — Parallel Side-Effect Iterator

`par_map`, `par_filter`, and `par_reduce` are parallel HOFs restricted to pure
verbs. `par_each` fills the missing quadrant: concurrent iteration where the
callback has IO side effects (`outputs`, `inputs`). Return type is `Unit` — no
results are collected. Async verbs (`detached`, `attached`, `listens`) would be
rejected. Implemented atop the existing pthreads pool in `prove_par_map.h`.
See `future/04-par-each.md`.

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
