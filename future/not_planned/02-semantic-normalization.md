# Post-1.0: Semantic Normalization

## Source

`ai-resistance.md` — Future Research (Post-1.0)

## Description

Canonicalize all code before storage. Variable names, declaration ordering,
whitespace, and stylistic choices are normalized away. A name map is stored
alongside the canonical AST. The LSP reconstructs human-readable code on
demand.

## Prerequisites

- Binary AST format (01-binary-ast-format.md)
- Stable name mangling scheme
- Reversible normalization (name map must be lossless)

## Key decisions

- Normalization scope: within-function only or cross-function?
- Name map format and storage location
- Impact on debugging (stack traces show normalized names?)
- Impact on diff/blame (diffs are on normalized form or human form?)

## Scope

Large. Requires changes to storage, formatter, LSP, debugger integration,
and version control workflows.
