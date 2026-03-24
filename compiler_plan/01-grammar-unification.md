# Phase 1: Grammar Unification

## Goal

Make `tree-sitter-prove/grammar.js` the single source of truth for Prove
syntax. Remove the `export.py` code that patches grammar.js and highlights.scm,
replacing it with validation-only checks.

## Current Flow

`export.py` patches **one section** of grammar.js (verbs) and **five sections**
of highlights.scm (verbs, keywords, contract-keywords, ai-keywords,
builtin-types) via sentinel markers. The rest of grammar.js is already
hand-maintained. The external scanner (`src/scanner.c`) is also hand-maintained.

```
tokens.py (138 token kinds)
    │
    ▼  export.py patches sentinel sections
grammar.js (verbs section)
highlights.scm (5 sections)
    │
    ▼  tree-sitter generate
parser.c + node-types.json
```

## Target Flow

```
grammar.js (fully hand-maintained, canonical)
highlights.scm (fully hand-maintained)
scanner.c (hand-maintained, newline handling)
    │
    ├──▶ tree-sitter generate → parser.c + node-types.json
    │
    ├──▶ validate_grammar.py → checks tokens.py is in sync
    │
    └──▶ node-types.json → shared constants for all consumers
```

## Steps

### 1.1 Full exhaustive audit: grammar.js vs parser.py

Parse every `.prv` file in the repo with both tree-sitter and the Python
parser. Compare the output trees structurally.

**Method:**

1. Write `scripts/audit_grammar.py` that:
   - Collects all `.prv` files from `prove-py/src/prove/stdlib/`, `examples/`,
     `proof/src/stdlib/`, `benchmarks/`, `prove-py/tests/fixtures/`
   - Parses each with `Lexer` + `Parser` → AST
   - Parses each with `tree-sitter` → CST
   - Compares: for every AST node, verify a corresponding CST subtree exists
     with matching structure (node kind, children, field names)
   - Reports mismatches: syntax accepted by one parser but not the other

2. Also audit `.intent` files: compare `intent_parser.py` output against
   tree-sitter's intent node types.

3. Structural comparison of all 60 `_parse_*` methods against grammar.js
   rules — document the mapping in a table.

**Deliverable:** `compiler_plan/audit-grammar-vs-parser.md` containing:
- File-by-file parse results (pass/fail/mismatch)
- Method-to-rule mapping table
- Any gaps found and fixes needed (grammar.js patches or parser.py bugs)

**This audit must complete and show zero gaps before Phase 2 begins.**

### 1.2 Pin grammar.js and highlights.scm as fully hand-maintained

Remove the sentinel-patching code path from `export.py`:

- `generate_treesitter()` currently writes to grammar.js (verbs section only)
  and highlights.scm (5 sections). Remove this function entirely.
- `build_treesitter()` (runs `tree-sitter generate` + `tree-sitter test`) —
  keep, but decouple from `generate_treesitter()`.
- Add `validate_treesitter()` that **reads** grammar.js and highlights.scm,
  extracts the relevant tokens, and compares against `tokens.py`. Emits
  warnings for any drift.
- Update CLI: `prove export --format treesitter` → `prove export --validate-grammar`.
- Update `test_export.py` to test validation, not generation.

**What stays in sentinel sections:** Nothing. The sentinel markers in
grammar.js and highlights.scm are removed. These files become fully
hand-maintained. This means when a new verb or keyword is added to Prove,
you update grammar.js, highlights.scm, AND tokens.py — and the validation
step catches if you forget one.

**Files changed:**
- `prove-py/src/prove/export.py` — delete `generate_treesitter()`, add `validate_treesitter()`
- `prove-py/src/prove/cli.py` — update CLI command
- `prove-py/tests/test_export.py` — test validation logic
- `tree-sitter-prove/grammar.js` — remove sentinel markers
- `tree-sitter-prove/queries/highlights.scm` — remove sentinel markers
- `tree-sitter-prove/queries/prove/highlights.scm` — remove sentinel markers

### 1.3 Extract shared constants from node-types.json

`tree-sitter generate` produces `src/node-types.json` — a machine-readable
list of every node type, field name, and child relationship.

Write a script `tree-sitter-prove/scripts/extract_constants.py` that reads
`node-types.json` and generates:

- `tree-sitter-prove/constants/node_kinds.py` — Python dict of node type
  names → string constants (for the CST→AST converter in Phase 2)
- `tree-sitter-prove/constants/node_kinds.h` — C `#define`s (for the Prove
  stdlib runtime in Phase 4)

These are **generated artifacts**, committed to the repo, rebuilt by
`tree-sitter generate && python scripts/extract_constants.py`.

**Files created:**
- `tree-sitter-prove/scripts/extract_constants.py`
- `tree-sitter-prove/constants/node_kinds.py` (generated)
- `tree-sitter-prove/constants/node_kinds.h` (generated)

### 1.4 Add grammar.js to CI validation

In `.gitea/workflows/`, add a step that:

1. Runs `tree-sitter generate` (ensures grammar.js is valid)
2. Runs `tree-sitter test` (corpus tests pass)
3. Runs `prove export --validate-grammar` (tokens.py in sync)
4. Checks that `constants/` are up to date (diff generated vs committed)

**Files changed:**
- `.gitea/workflows/ci.yml` (or new workflow file)

### 1.5 Document grammar.js as canonical

Update `CLAUDE.md` layout section to list `tree-sitter-prove/` as the
canonical grammar source. Add a note that syntax changes start with
grammar.js, not tokens.py or parser.py.

## Risks

- **Low:** The grammar is already comprehensive. export.py only patches
  6 sentinel sections, not the whole file — removing patching is mechanical.
- **Scanner.c is small** (1.5KB, newline handling) and already hand-maintained.
- Care needed when adding new keywords/verbs post-migration: must update
  grammar.js, highlights.scm, AND tokens.py. The validation step catches
  drift but only if you run it.

## Completion Criteria

- [ ] `grammar.js` has no sentinel markers; fully hand-maintained
- [ ] `highlights.scm` has no sentinel markers; fully hand-maintained
- [ ] `generate_treesitter()` deleted from `export.py`
- [ ] `prove export --validate-grammar` checks tokens.py ↔ grammar.js sync
- [ ] `node_kinds.py` and `node_kinds.h` generated from `node-types.json`
- [ ] CI validates grammar on every push
- [ ] Audit document committed
