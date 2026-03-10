# LSP ML — Context-Aware Completion PoC

Statistical n-gram completion model integrated into the Prove LSP. Trained on
`.prv` source, served inline from the LSP process. No neural networks, no
separate daemon.

## Status

All 5 phases implemented and passing. Python bridge active; full Prove path
blocked on impl03 `loads`/`saves`.

## What Was Built

| Phase | File(s) | Description |
|-------|---------|-------------|
| 1 | `scripts/ml_extract.py` | Walks stdlib/examples/fixtures → token ngrams + FunctionDef triples |
| 2 | `scripts/ml_train.py` | Bigram (3,447 contexts) + unigram (1,114) frequency tables |
| 3 | `scripts/ml_store.py` | Python bridge: writes models as `:[Lookup]` `.prv` files into `data/lsp-ml-store/` |
| 3 | `tools/lsp-ml/store_model.prv` | Prove target (stub, expected to fail until impl03 stable) |
| 4 | `prove-py/src/prove/lsp.py` — `_ProjectIndexer` | Project root detection, per-file incremental indexing, `.prove_cache/` persistence, `did_save` hook |
| 5 | `prove-py/src/prove/lsp.py` — `_ml_completions` | Context extraction, project + global model merge, auto-import, signature + docstring |

## Running the Training Pipeline

```bash
# From repo root — run once, outputs committed to data/
python scripts/ml_extract.py       # → data/completions_raw.json
python scripts/ml_train.py         # → data/completions_model.json, data/bigrams_model.json
python scripts/ml_store.py         # → data/lsp-ml-store/
```

Restart the LSP (reload window in editor) after retraining.

## How It Works at Runtime

**On `textDocument/didOpen`** (first `.prv` file in a session):
- `_ProjectIndexer.for_uri()` walks up to `prove.toml` to find project root
- `index_all_files()` scans all `.prv` files, builds in-memory bigram + symbol tables
- Writes `.prove_cache/bigrams/current.prv` and `.prove_cache/completions/current.prv`

**On `textDocument/didSave`**:
- `patch_file()` removes old per-file contributions, re-parses the saved file, rebuilds tables (incremental — only the changed file is re-parsed)

**On `textDocument/completion`**:
1. Lex source up to cursor → extract `(prev2, prev1)` context tokens
2. Query project bigrams → fall back to project unigram if no match
3. Query global model from `data/lsp-ml-store/` (lazy-loaded once)
4. Surface project symbols (functions/types/constants) filtered by context:
   - After a verb keyword (`transforms`, `validates`, …) → show functions
   - After `as`/`is`/`type` → show types
   - With a typed prefix → show matching symbols of any kind
5. Merge, deduplicate, prepend as `CompletionItem` with `sort_text="\x00p_..."` so they rank first
6. Each project symbol carries full signature, docstring, and `additional_text_edits` for auto-import

## Completion Item Quality

Project symbol completions match stdlib completion quality:

```
label:         set_email
detail:        Example                        ← module name
label_details: verb=transforms, module=Example
documentation: ```prove
               transforms set_email(user User, email Option<Email>) User
               ```
               ---
               <docstring if present>
auto-import:   inserts "  Example transforms set_email" in module header
```

## Difference from Full Prove Version

The architecture is already Prove-shaped — model lives in `:[Lookup]` `.prv` files
matching impl03's Store format. What remains:

| Part | Current | Full Prove |
|------|---------|-----------|
| Extract tokens | `ml_extract.py` (Python) | Prove program using Path + Lexer |
| Train frequencies | `ml_train.py` (Python) | Prove program using Table |
| Write to Store | `ml_store.py` (Python bridge) | `store_model.prv` (blocked on impl03) |
| Query at completion | Parse `.prv` text, dict lookup | Compiled `:[Lookup]` → C array, O(1) |

The LSP itself stays Python (pygls dependency) regardless. The Prove path is
specifically the offline training → Store → compiled binary pipeline.

## File Map

```
tools/lsp-ml/
    README.md               ← this file
    store_model.prv         ← Prove training program (stub, expected to fail: build)

scripts/
    ml_extract.py           ← Phase 1: token extraction
    ml_train.py             ← Phase 2: frequency table training
    ml_store.py             ← Phase 3: write to Store format

data/
    completions_raw.json    ← Phase 1 output (9,107 ngrams + 339 triples)
    completions_model.json  ← Phase 2 bigram model
    bigrams_model.json      ← Phase 2 unigram fallback
    lsp-ml-store/
        bigrams/
            current.prv     ← unigram (prev1, next) → count
            versions/
        completions/
            current.prv     ← bigram (prev2, prev1) → pipe-separated ranked list
            versions/

prove-py/src/prove/lsp.py   ← _ProjectIndexer, _ml_completions, _global_model_complete
                               _ast_type_str, _ast_sig_str, _extract_context_tokens
```

## Unblocking Full Prove Path

1. impl03 `loads`/`saves` tests pass → implement `store_model.prv`
2. `prove build tools/lsp-ml/store_model.prv` → native binary
3. LSP calls binary via subprocess (impl04, already done) instead of Python bridge
4. `:[Lookup]` tables compiled to C arrays → O(1) query, zero parse overhead at startup
