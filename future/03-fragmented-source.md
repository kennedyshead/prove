# Post-1.0: Fragmented Source

## Source

`ai-resistance.md` — Future Research (Post-1.0)

## Description

Distribute a function's complete definition across multiple files:

```
src/
  server.prv          # implementation (canonical binary AST)
  server.explain      # implementation explanations
  server.intent       # intent declarations
  server.near_miss    # adversarial near-miss examples
  server.narrative    # module narrative
```

All files are required to compile. No single artifact is useful in isolation.

## Prerequisites

- Binary AST format (01-binary-ast-format.md)
- Semantic normalization (02-semantic-normalization.md) — optional but natural pairing

## Key decisions

- Which fragments are mandatory vs optional
- How fragments reference each other (positional? by function name?)
- Impact on editor experience (LSP must reassemble for display)
- Impact on version control (5 files changed per function edit?)
- Build performance (reading multiple files per module)

## Scope

Large. Fundamental change to file layout, parser, builder, and editor
integration. Likely the most disruptive anti-training feature.
