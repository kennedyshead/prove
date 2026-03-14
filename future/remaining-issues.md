# Remaining Issues — Post-Implementation (RESOLVED)

Issues and potential improvements discovered during implementation of
plans 07-11 (stub generation, stdlib knowledge base, body generation,
intent format).

**Status:** All actionable issues resolved. Issue #6 (stdlib docstring
audit) is user work. Issue #7 (LSP .intent support) deferred to
`future/lsp-intent-support.md`.

---

## 1. Body generation parameter inference is basic

`generate_function_source()` in `_body_gen.py` currently defaults to
`(value String) String` for all generated function parameters. The intent
parser should derive parameter names and types from:
- Vocabulary type definitions in `.intent` files
- Stdlib function signatures when a match is found
- Context phrases in verb phrases ("against stored data" → second param)

**Fix:** Extend `intent_generator.py` to thread vocabulary types into
parameter generation. Requires type resolution from VocabularyEntry
descriptions to actual Prove types.

## 2. ML pipeline not auto-run after stdlib changes

The docstring extraction pipeline (`ml_extract.py` → `ml_train.py` →
`ml_store.py`) must be run manually after stdlib `.prv` changes. The
LSP's docstring index (`data/lsp-ml-store/docstrings/current.prv`) goes
stale if stdlib docstrings are updated without re-running the pipeline.

**Fix:** Add a `scripts/ml_rebuild.sh` convenience script, or integrate
the pipeline into `prove export` or a post-install hook.

## 3. Flow declarations not yet wired to import generation

The `.intent` parser correctly parses `flow` sections with `->` arrows,
but `intent_generator.py` does not yet generate `use` import declarations
from flow step dependencies. Module A flowing to Module B should produce
`use B` in Module A's generated source.

**Fix:** In `generate_module_source()`, collect flow step targets that
reference other modules and emit corresponding `use` imports.

## 4. Constraint mapping is limited

Constraint phrases in `.intent` files are parsed and anchored to
vocabulary terms, but only `"failable"` is currently mapped to a code
feature (`can_fail`). The constraint patterns table in plan 11 lists
several more mappings:
- `"must use"` → `chosen:` annotations
- `"have bounded"` → `ensures` contracts with range checks
- `"no ... appears in"` → negative `ensures` contracts
- `"all ... must"` → `requires` contracts

**Fix:** Add constraint pattern matching in `intent_generator.py` that
maps recognized English patterns to specific Prove code features.

## 5. @generated provenance not preserved through formatter

The `@generated` doc comment tag (used by `_body_gen.py` for tracking
generated vs human-written code) is not explicitly handled by the
formatter. The formatter preserves doc comments, but if it ever reformats
them, the `@generated` marker could be lost.

**Fix:** Add explicit `@generated` preservation in the formatter's doc
comment handling.

## 6. Stdlib docstring audit not done

Plan 08 recommends an audit pass over all stdlib `///` docstrings to
ensure they are informative enough for the knowledge base (at least one
synonym, action verb, domain concept). Some docstrings may be too terse
for effective `implied_functions()` matching.

**Fix:** Review all 19 stdlib modules' docstrings against the guidelines
in plan 08. This is a one-time manual effort.

## 7. LSP .intent file support not yet implemented

The intent parser and generator work from CLI, but the LSP does not yet
register `.intent` as a language ID or provide completions, diagnostics,
or code actions for `.intent` files. Plan 11 specifies:
- Verb completions in module blocks
- Noun suggestions from stdlib docstring index
- W601/W602/W603/E601/E602 diagnostics
- Code actions for generating .prv from intent

**Fix:** Add `.intent` mode to `lsp.py` with the above features. Also
needs tree-sitter, Pygments, and Chroma grammar updates.

## 8. prove generate --from-intent not wired

Plan 11 specifies `prove generate --from-intent` as a shorthand for
`prove intent --generate`. Currently these are separate commands. The
`--from-intent` flag on `generate` is not implemented.

**Fix:** Either add `--from-intent` to the generate command or document
that `prove intent --generate` is the canonical way.
