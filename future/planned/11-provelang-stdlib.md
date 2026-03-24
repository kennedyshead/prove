# 11 — Prove Stdlib Module & Unified Grammar

## Status: Planned — detailed plan in `compiler_plan/`

### Summary

This feature has been expanded into a comprehensive multi-phase plan covering
unified grammar, Python tree-sitter migration, recursive variant types, and
the Prove stdlib module. The full plan lives in `compiler_plan/`:

- `compiler_plan/00-overview.md` — master plan, dependency graph, decisions
- `compiler_plan/01-grammar-unification.md` — tree-sitter as single grammar source
- `compiler_plan/02-python-tree-sitter.md` — replace parser.py/lexer.py
- `compiler_plan/03-recursive-variants.md` — direct + mutual recursion
- `compiler_plan/04-prove-stdlib-module.md` — `Prove` module with Tree/Node types
- `compiler_plan/05-self-hosted-path.md` — how unified grammar enables v2.0

### Key Decisions (2026-03-24)

- **Module name:** `Prove`
- **AST types:** opaque binary (`type Node is binary`, `type Tree is binary`)
  backed by tree-sitter C nodes
- **Parsing:** `Parse.tree(source String) Result<Tree>` — lives in Parse module
- **Grammar source of truth:** `tree-sitter-prove/grammar.js` (hand-maintained)
- **Python compiler:** replaces parser.py/lexer.py with py-tree-sitter + CST→AST converter
- **Tree-sitter distribution:** vendored C source (no system dependency)
- **Recursive variants:** direct + mutual recursion, error code E423
- **Error parity:** full — all ~30 E1xx parser error codes reproduced
- **Self-hosted IR:** start with binary types, migrate to recursive variants

### Dependencies

- Generic `Token`/`Rule` in Parse (done — committed `7dc7453`)
- tree-sitter-prove C library (vendored)
- py-tree-sitter Python bindings (vendored wheel)
