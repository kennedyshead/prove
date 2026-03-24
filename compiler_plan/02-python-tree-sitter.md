# Phase 2: Python Tree-sitter Integration

## Goal

Replace `parser.py` (2,874 lines) and `lexer.py` (702 lines) with
tree-sitter parsing via `py-tree-sitter`. Keep all 52 AST node types in
`ast_nodes.py` unchanged — the checker, emitter, and optimizer see no
difference.

## Architecture

```
.prv source
    │
    ▼  py-tree-sitter (C library via Python bindings)
tree-sitter CST (concrete syntax tree)
    │
    ▼  cst_converter.py (new, ~1000-1500 lines)
ast_nodes.py AST (existing 52 node types)
    │
    ▼  checker → emitter → optimizer (unchanged)
```

## Steps

### 2.1 Add py-tree-sitter dependency via vendored wheel

Add `tree-sitter` (core Python bindings) to `prove-py/pyproject.toml`.
For the Prove grammar, build a `.whl` from
`tree-sitter-prove/bindings/python/` and vendor it.

**Wheel build process:**
1. `cd tree-sitter-prove && python -m build` (uses `bindings/python/` setup)
2. Produces `tree_sitter_prove-0.1.0-*.whl`
3. Store in `prove-py/vendor/tree_sitter_prove-0.1.0-*.whl`
4. `pyproject.toml` references the vendored wheel

**New file:** `prove-py/src/prove/tree_sitter_setup.py` — language loading
helper that imports tree-sitter-prove, initializes the parser, and provides
a `ts_parse(source: str) -> tree_sitter.Tree` function.

**Build script:** `scripts/build_ts_wheel.sh` — builds the wheel from
tree-sitter-prove and copies it to `prove-py/vendor/`. Run when grammar.js
changes.

**Files changed:**
- `prove-py/pyproject.toml` — add `tree-sitter` + vendored wheel dependency
- `prove-py/src/prove/tree_sitter_setup.py` (new)
- `prove-py/vendor/` (new, contains `.whl`)
- `scripts/build_ts_wheel.sh` (new)

### 2.2 Write CST→AST converter

**New file:** `prove-py/src/prove/cst_converter.py`

This is the largest piece of work. For each of the 52 AST node types, write
a conversion function that maps from tree-sitter CST nodes to the existing
`ast_nodes.py` classes.

Structure:

```python
class CSTConverter:
    """Convert tree-sitter CST to Prove AST."""

    def __init__(self, source: str, tree: Tree, filename: str = ""):
        self.source = source
        self.tree = tree
        self.filename = filename

    def convert(self) -> Module:
        """Convert root node to Module AST."""
        ...

    def _convert_function_def(self, node: Node) -> FunctionDef:
        ...

    def _convert_type_def(self, node: Node) -> TypeDef:
        ...

    # ... one method per AST node type
```

Key mappings (CST node type → AST class):

| CST node | AST class | Notes |
|----------|-----------|-------|
| `source_file` | `Module` | Root container |
| `module_declaration` | `ModuleDecl` | |
| `function_definition` | `FunctionDef` | Extract verb, name, params, body |
| `main_definition` | `MainDef` | |
| `type_definition` | `TypeDef` | Dispatch on type body kind |
| `algebraic_type_body` | `AlgebraicTypeDef` | |
| `record_type_body` | `RecordTypeDef` | |
| `refinement_type_body` | `RefinementTypeDef` | |
| `binary_type_body` | `BinaryDef` | |
| `lookup_type_body` | `LookupTypeDef` | |
| `variable_declaration` | `VarDecl` | |
| `assignment` | `Assignment` | |
| `match_expression` | `MatchExpr` | |
| `match_arm` | `MatchArm` | |
| `binary_expression` | `BinaryExpr` | |
| `unary_expression` | `UnaryExpr` | |
| `call_expression` | `CallExpr` | |
| `pipe_expression` | `PipeExpr` | |
| `field_expression` | `FieldExpr` | |
| `string_literal` | `StringLit` / `StringInterp` | Check for interpolation children |
| `integer_literal` | `IntegerLit` | |
| `decimal_literal` | `DecimalLit` | |
| `list_literal` | `ListLiteral` | |
| `lambda_expression` | `LambdaExpr` | |
| `import_declaration` | `ImportDecl` | |
| `constant_definition` | `ConstantDef` | |
| `foreign_block` | `ForeignBlock` | |
| `comptime_block` | `ComptimeExpr` | |
| `invariant_network` | `InvariantNetwork` | |
| `variant_pattern` | `VariantPattern` | |
| `wildcard_pattern` | `WildcardPattern` | |
| `lookup_pattern` | `LookupPattern` | |
| `doc_comment_block` | doc_comment field | Attach to next declaration |
| `ensures_clause` | ensures field on FunctionDef | |
| `requires_clause` | requires field on FunctionDef | |
| `explain_annotation` | `ExplainBlock` | |
| `valid_expression` | `ValidExpr` | |
| `fail_propagation` | `FailPropExpr` | |
| `lookup_access_expression` | `LookupAccessExpr` | |
| ... | ... | ~52 total mappings |

**Span mapping:** tree-sitter provides `start_point` (row, column) and
`end_point` (row, column). Convert to the existing
`Span(file, start_line, start_col, end_line, end_col)` format. Note:
tree-sitter rows are 0-based, Prove spans are 1-based — add 1.

**Error recovery — full parity required:** tree-sitter produces `ERROR` and
`MISSING` nodes for invalid syntax. The old parser has ~30 custom error
messages with `E1xx` codes. **Every existing error code must be reproduced**
by the tree-sitter path — no generic fallbacks.

Strategy:
1. **Catalog all E1xx codes** from parser.py — extract every `self._error()`
   call with its trigger condition and message text.
2. **Write error inference in CSTConverter** — after tree-sitter parsing,
   walk `ERROR`/`MISSING` nodes and infer which E1xx code applies based on:
   - Position context (inside `from` block? after type definition?)
   - The `MISSING` node type (missing `from` → E102, missing `)` → E105, etc.)
   - Parent node type and siblings
3. **Test error parity** — in step 2.7, parse every intentionally-broken
   fixture file with both parsers and assert identical error codes.

This is significant work (~300-500 lines of error inference logic) but
ensures users see the same diagnostics after migration.

### 2.3 Write intent file converter

The Python compiler currently uses `intent_parser.py` for `.intent` files.
tree-sitter-prove already handles `.intent` syntax (`intent_file`,
`intent_project`, `intent_vocabulary`, etc.).

**New file:** `prove-py/src/prove/cst_intent_converter.py`

Converts tree-sitter CST of `.intent` files to the existing `IntentProject`
AST from `intent_parser.py`. Must produce identical output to the current
`intent_parser.py` for all `.intent` files in the repo.

### 2.4 Provide drop-in `parse()` function

**New file:** `prove-py/src/prove/parse.py` (note: `parse.py`, not `parser.py`)

```python
from prove.cst_converter import CSTConverter
from prove.tree_sitter_setup import ts_parse
from prove.ast_nodes import Module

def parse(source: str, filename: str = "") -> Module:
    """Parse Prove source to AST via tree-sitter."""
    tree = ts_parse(source)
    return CSTConverter(source, tree, filename).convert()
```

This replaces the old `Lexer(source).tokenize()` → `Parser(tokens).parse()`
two-step. Every consumer switches to a single `parse(source, filename)` call.

### 2.5 Migrate all consumer files

**Complete list of files that import `Parser` and/or `Lexer`:**

| File | Import | Usage pattern |
|------|--------|---------------|
| `_check_runner.py` | Both (5 sites) | `Lexer(src, f).tokenize()` → `Parser(toks, f).parse()` |
| `_build_runner.py` | Both | Same pattern |
| `_format_runner.py` | Both (3 sites) | Same pattern |
| `_test_runner.py` | Both | Same pattern |
| `builder.py` | Both | Top-level import |
| `c_emitter.py` | Both (2 sites each) | Inline re-parse of stdlib snippets |
| `cli.py` | Both | Top-level import |
| `intent_generator.py` | Both | Parse generated .prv source |
| `lsp.py` | Both | Parse on every keystroke (see LSP section) |
| `module_resolver.py` | Both | Parse sibling modules |
| `stdlib_loader.py` | Both | Parse stdlib .prv files |
| `store_binary.py` | Both | Parse for store validation |
| `tests/helpers.py` | Both | `check()` helper used by ~30 test files |

Each site changes from:
```python
from prove.lexer import Lexer
from prove.parser import Parser
tokens = Lexer(source, filename).tokenize()
module = Parser(tokens, filename).parse()
```
to:
```python
from prove.parse import parse
module = parse(source, filename)
```

### 2.6 Handle tokens.py consumers separately

**tokens.py cannot be deleted.** These consumers need token-level APIs:

| Consumer | What it needs from tokens.py |
|----------|----------------------------|
| `lsp.py` | `Token`, `TokenKind`, `KEYWORDS` — for completion context detection, token-at-cursor |
| `export.py` | `TokenKind`, `KEYWORDS` — for grammar validation (Phase 1) |
| `scripts/ml_extract.py` | `Token`, `TokenKind` — n-gram training on token sequences |
| `tests/test_lexer.py` | `TokenKind` — lexer tests (deleted with lexer) |
| `tests/test_ml_pipeline.py` | `TokenKind` — ML pipeline tests |

**Decision:** Keep `tokens.py` as a shared vocabulary file. Delete `lexer.py`.
Write a `tokenize()` function in `parse.py` that parses via tree-sitter and
extracts leaf nodes as `Token` objects. The token kinds map from tree-sitter
node type names to `TokenKind` enum values. This eliminates the lexer
completely — one tokenization path, backed by the same grammar.

### 2.7 Parallel test phase

Before deleting the old parser, run both parsers in parallel on the full
test suite + all `.prv` files in the repo:

```python
# test_cst_parity.py
def test_parity(prv_file):
    old_ast = old_parse(source)
    new_ast = cst_parse(source)
    assert ast_equal(old_ast, new_ast)
```

Write an `ast_equal()` deep comparison that ignores span differences (byte
offsets may differ slightly between the two parsers). Run on:
- All `prove-py/tests/fixtures/` files
- All `examples/` files
- All `proof/src/stdlib/` files
- All `benchmarks/` files

Also compare error diagnostics: parse intentionally broken files with both
parsers and verify error codes match.

**New file:** `prove-py/tests/test_cst_parity.py`

### 2.8 Delete old parser and lexer

Once parity is confirmed and all tests pass:

- Delete `prove-py/src/prove/parser.py` (2,874 lines)
- Delete `prove-py/src/prove/lexer.py` (702 lines)
- Delete `prove-py/src/prove/intent_parser.py` (replaced by CST converter)
- Delete `prove-py/tests/test_lexer.py` (lexer-specific tests)
- Delete `prove-py/tests/test_cst_parity.py` (no longer needed)
- Keep `prove-py/src/prove/tokens.py` — validated against grammar.js

**Net change:** Remove ~3,600 lines of parser/lexer, add ~1,500 lines of
CST converter + ~200 lines of tokenizer + ~100 lines of setup. Significant
simplification.

### 2.9 Update LSP for incremental parsing

The LSP (`lsp.py`) currently re-parses the entire file on every keystroke.
tree-sitter supports incremental parsing — edit a syntax tree without
re-parsing the whole file.

Changes:
- Cache the `TSTree` per open document
- On text change, call `tree.edit()` + `parser.parse(new_source, old_tree)`
- Convert only the changed subtree to AST (optimization, not required for v1)
- Replace direct `Lexer` usage for token-at-cursor with tree-sitter node
  lookup (which is O(log n) vs O(n) re-lex)

**Files changed:**
- `prove-py/src/prove/lsp.py`

### 2.10 Update test infrastructure

`prove-py/tests/helpers.py` provides `check()`, `check_fails()`,
`check_warns()` — used by ~30 test files. These call `Lexer` + `Parser`
internally. Update to use `parse()`.

`prove-py/tests/conftest.py` may also need updates if it references
parser/lexer fixtures.

**Files changed:**
- `prove-py/tests/helpers.py`
- `prove-py/tests/conftest.py` (if needed)

## Risks

- **High: CST→AST converter size.** ~1,500 lines of careful mapping work.
  Each of the 60 old parse methods must have a corresponding converter method
  that produces identical AST output. The parallel test phase (2.7) is the
  safety net.
- **High: Error message parity.** Every E1xx code must be reproduced from
  tree-sitter ERROR/MISSING nodes. tree-sitter's error recovery is
  fundamentally different (marks nodes vs throwing) — the error inference
  layer (~300-500 lines) must reverse-engineer the original diagnostic from
  tree-sitter's partial parse output. Some cases may require heuristics.
- **Medium: LSP disruption.** The LSP uses both token-level and AST-level
  APIs. The token extraction (2.6) and incremental parsing (2.9) are
  significant changes. Budget extra time.
- **Low: ML pipeline.** The n-gram models are trained on token sequences.
  If the tree-sitter tokenizer produces slightly different token boundaries,
  the models need retraining. This is a one-time cost.
- **Low: Formatter.** `ProveFormatter` operates on AST nodes (not tokens or
  parser internals). It's called by `_format_runner.py` which does the
  parsing. Once `_format_runner.py` switches to `parse()`, the formatter
  works unchanged.

## Completion Criteria

- [ ] `py-tree-sitter` parses all `.prv` files in the repo
- [ ] CST→AST converter produces identical ASTs to old parser (parity tests)
- [ ] All 13+ consumer files migrated to `parse()`
- [ ] `tokenize()` function provides token-level API for LSP/ML
- [ ] All unit tests pass with new parser backend
- [ ] All e2e tests pass
- [ ] `parser.py`, `lexer.py`, `intent_parser.py` deleted
- [ ] `tokens.py` retained, validated against grammar.js
- [ ] LSP uses tree-sitter incremental parsing
- [ ] `tests/helpers.py` updated
- [ ] All ~30 E1xx error codes reproduced from tree-sitter path
