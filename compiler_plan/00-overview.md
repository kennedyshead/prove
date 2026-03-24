# Unified Grammar & AST Plan — Overview

## Goal

One grammar, used everywhere: tree-sitter-prove is the canonical definition
of Prove syntax. The Python bootstrap compiler, the Prove stdlib, editor
tooling, and eventually the self-hosted compiler all consume the same grammar.
No parallel parsers, no divergence.

## Phases

```
Phase 1: Grammar Unification
    │
    ├──────────────────────┐
    ▼                      ▼
Phase 2: Python        Phase 4: Prove
Tree-sitter            Stdlib Module
    │                      │
    ▼                      ▼
    └──────────┬───────────┘
               ▼
         Phase 5: Self-hosted Path

Phase 3: Recursive Variants (independent, parallel with any phase)
```

| Phase | Title | Depends on | Risk |
|-------|-------|------------|------|
| 1 | Grammar Unification | — | Low: grammar already comprehensive |
| 2 | Python Tree-sitter | Phase 1 | High: 13+ consumer files, LSP/ML token deps |
| 3 | Recursive Variants | — (independent) | **DONE** |
| 4 | Prove Stdlib Module | Phase 1 | Low: opaque binary types, follows Graphic module pattern |
| 5 | Self-hosted Path | Phases 2 + 4 (+ Phase 3 for IR) | Large: full compiler rewrite, post-v1 |

Phase 2 and Phase 4 can proceed **in parallel** after Phase 1. Phase 4
(C runtime wrappers around tree-sitter) doesn't need the Python compiler to
use tree-sitter — it only needs the grammar to be canonical and the C library
to be buildable.

## Current State

- **tree-sitter-prove**: Complete grammar (801 lines), external scanner for
  newlines (`scanner.c`), 270-line highlights, test corpus, multi-platform
  bindings. `export.py` currently patches the **verbs section** of grammar.js
  and **5 sections** of highlights.scm from `tokens.py` — this patching must
  be removed in favor of hand-maintenance + validation.
- **Python parser**: 2,874 lines, 60 parse methods, 52 AST node types,
  702-line lexer, 138 token kinds. Authoritative but duplicates grammar.
  **13+ files** import `Parser` directly, 13+ import `Lexer`.
- **tokens.py**: Used by lexer, parser, export.py, LSP (completion context),
  and ML pipeline (n-gram training). Cannot be deleted even after parser.py
  is removed — LSP and ML still need token-level APIs.
- **Prove stdlib**: Parse module has `Token`/`Rule`. No AST types yet.
- **Self-hosted compiler** (`future/in_progress/07`): Planned for v2.0.

## Key Design Decisions

1. **tree-sitter-prove/grammar.js is the source of truth.** `export.py`
   currently patches the verb section of grammar.js and 5 sections of
   highlights.scm. This patching is removed; grammar.js and highlights.scm
   are fully hand-maintained. A validation step checks that tokens.py stays
   in sync with the grammar.

2. **Full exhaustive audit before migration.** Parse every `.prv` file in the
   repo with both tree-sitter and the Python parser, compare output trees.
   No assumptions about completeness — prove it.

3. **CST→AST, not CST directly.** tree-sitter produces a concrete syntax
   tree. The compiler needs an abstract syntax tree (52 node types in
   `ast_nodes.py`). Phase 2 writes a converter, keeping existing AST nodes
   unchanged so checker/emitter/optimizer are untouched.

4. **tokens.py stays.** Even after parser.py and lexer.py are deleted, the
   LSP needs `TokenKind` and `KEYWORDS` for completion context, and the ML
   pipeline needs token sequences for n-gram training. tokens.py becomes a
   shared vocabulary file validated against grammar.js. Lexer.py is deleted
   — tree-sitter leaf extraction provides token-level API.

5. **Full error message parity.** Every existing E1xx parser error code must
   have a corresponding diagnostic from the tree-sitter path. No "generic
   syntax error" fallback — map all ~30 parse error codes.

6. **Opaque binary AST for Prove stdlib.** Phase 4 wraps tree-sitter C nodes
   as `type Node is binary` / `type Tree is binary`. Recursive variant types
   (Phase 3) are a nice language feature but NOT a prerequisite for the stdlib
   module — binary types sidestep the limitation.

7. **Recursive variants: direct + mutual recursion.** Phase 3 implements both
   direct self-reference and mutual recursion between types in the same module.
   Mutual recursion requires multi-pass type registration but is worth doing
   from the start to avoid a partial implementation.

8. **Vendor tree-sitter source for the C runtime.** Tree-sitter core +
   generated parser.c + scanner.c vendored in `runtime/vendor/`. No system
   dependency required. Fallback plan for pkg-config in future if needed.

9. **Self-hosted IR: start binary, migrate to variants.** The self-hosted
   compiler begins with opaque binary IR types (no Phase 3 dependency), then
   migrates to recursive variant types once they're battle-tested.

10. **Vendored wheel for tree-sitter-prove Python bindings.** Build a `.whl`
    from `tree-sitter-prove/bindings/python/` for the Python compiler's
    tree-sitter dependency. No PyPI publishing.

## Files Superseded

These future/ files are superseded by this plan and should be removed once
the compiler_plan directory is accepted:

- `future/planned/11-provelang-stdlib.md` → `compiler_plan/04-prove-stdlib-module.md`
- `future/planned/12-recursive-variant-types.md` → `compiler_plan/03-recursive-variants.md`
- `future/in_progress/07-self-hosted-compiler.md` — remains as-is, referenced by Phase 5

## Success Criteria

- [ ] `tree-sitter-prove test` passes on all `.prv` files in the corpus
- [ ] Python compiler uses tree-sitter for parsing; `parser.py` and `lexer.py` deleted
- [ ] `tokens.py` validated against grammar.js in CI
- [ ] All existing e2e tests pass with tree-sitter backend
- [ ] `Prove` stdlib module provides `Node`, `Tree`, accessors
- [ ] `Parse.tree()` returns `Result<Tree>` backed by tree-sitter
- [x] Recursive variant types work (separate from but enabled by this plan)
