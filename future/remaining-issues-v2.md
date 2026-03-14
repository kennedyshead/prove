# Remaining Issues v2 — Post-Implementation

Issues and potential improvements discovered during implementation of
function name synonyms and LSP .intent support.

---

## 1. Phase 3 vocabulary-aware matching (deferred)

`function-name-synonyms.md` Phase 3 proposes a `VocabularyIndex` that
builds synonym rings from `.intent` vocabulary definitions. This would
let `prose_overlaps()` match "Credential" ↔ "credentials" ↔ "user
identity" via vocabulary descriptions.

**Status:** Deferred until Phases 1+2 prove their value in practice.

## 2. Intent LSP noun suggestions from docstring index

The plan calls for suggesting stdlib nouns from `get_docstring_index()`
when typing after a verb in `.intent` module blocks. Currently only verb
keyword completions are provided; noun suggestions require loading the
docstring model at intent-completion time, which adds latency.

**Status:** Deferred — verb completions are the higher-value feature.

## 3. Tree-sitter .intent grammar conflicts

The `.intent` grammar was added as a `choice()` in `source_file`. This
means tree-sitter will attempt to parse `.intent` syntax for `.prv`
files and vice versa. A cleaner approach would be a separate grammar
(`tree-sitter-prove-intent`) or external scanner-based file detection.
Current approach works for highlighting but may produce spurious parse
errors in editor integrations that use tree-sitter for error detection.

**Status:** Works for highlighting; revisit if editor issues arise.

## 4. Intent code action uses CreateFile

The "Generate .prv from intent" code action uses `CreateFile` +
`TextDocumentEdit` document changes. Some editors may not support the
`CreateFile` resource operation. A fallback approach using
`workspace/applyEdit` with `createFile` could improve compatibility.

**Status:** Works in VS Code and editors supporting LSP 3.16+.

## 5. Chroma lexer IntentLexer not registered in entry point

The `IntentLexer` was added to `prove/lexer.go` but Chroma's lexer
registry uses `init()` functions or explicit registration. The new
`IntentLexer` variable exists but may need explicit registration
depending on how the lexer is consumed by Gitea/Hugo.

**Status:** Variable exported; registration depends on consumer.
