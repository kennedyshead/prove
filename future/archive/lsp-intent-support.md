# Plan: LSP .intent File Support

## Context

The intent parser and generator work from the CLI (`prove intent`), but the
LSP does not yet recognize `.intent` files. This plan adds language server
support for `.intent` files including completions, diagnostics, and code
actions.

## Scope

### 1. Language ID registration

- Register `.intent` as a recognized language ID in `lsp.py`
- Handle `textDocument/didOpen`, `didChange`, `didClose` for `.intent` files
- Parse on change using `intent_parser.parse_intent()`

### 2. Diagnostics

Surface existing intent parser diagnostics as LSP diagnostics:

| Code | Severity | Description |
|------|----------|-------------|
| E601 | error | Missing `project` declaration |
| E602 | error | Missing `purpose:` field |
| W601 | warning | Unrecognized verb in module block |
| W602 | warning | Vocabulary term defined but never referenced |
| W603 | warning | Flow references undefined module |

### 3. Completions

- **Verb completions** in module blocks: suggest `validates`, `transforms`,
  `reads`, `creates`, `matches`, `inputs`, `outputs`
- **Noun suggestions** from stdlib docstring index when typing after a verb
- **Vocabulary name completions** in constraint blocks when referencing
  defined vocabulary terms
- **Module name completions** in flow blocks from defined modules

### 4. Code actions

- **Generate .prv from intent**: quick action on module blocks that runs
  `generate_module_source()` and creates/updates the corresponding .prv file
- **Add missing import**: when a flow references a module not yet in the
  generated source, offer to add `use` import

### 5. Grammar updates

- **tree-sitter-prove**: add `.intent` file grammar rules
- **pygments-prove**: add `.intent` token types for syntax highlighting
- **chroma-lexer-prove**: add `.intent` support for Gitea/Hugo rendering

## Dependencies

- Intent parser (`intent_parser.py`) — already implemented
- Intent generator (`intent_generator.py`) — already implemented
- Stdlib docstring index (`data/lsp-ml-store/`) — already available

## Estimated effort

Medium — primarily LSP wiring and grammar additions. No new compiler
features required.
