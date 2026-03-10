# LSP ML PoC — Store-Backed Completion Model

## Overview

A completion model for the LSP trained on `.prv` source, where the model lives as
Store `:[Lookup]` tables and is compiled to binary for fast inference. Dogfoods
impl02 (binary lookup) + impl03 (Store stdlib) while delivering real LSP value.

## Prerequisites

| Requirement | Status |
|------------|--------|
| `:[Lookup]` types (impl02) | Mostly done — `binary` keyword restriction pending |
| Store stdlib (impl03) | Mostly done — `merges` + tests remaining |
| Process execution (impl04) | Done |
| Async verbs (impl01) | Not required for Phase 1–4 |

Phases 1–2 can start today (Python only). Phase 3 in Prove unblocks once impl03
tests pass.

## Two Index Sources

The LSP maintains two separate indexes, merged at completion time:

| Source | Scope | Location |
|--------|-------|----------|
| **Global model** | stdlib + all known `.prv` corpus | `data/lsp-ml-store/` (ships with tool) |
| **Project index** | current workspace `.prv` files | `<project-root>/.prove_cache/` |

The project index is built and updated by the LSP itself, incrementally, as files are
opened and saved. It captures local symbols, types, and usage patterns specific to the
project — things the global model cannot know.

## Architecture

```
stdlib + corpus .prv files          local project .prv files
        │                                    │
        ▼  [scripts/ml_extract.py]           ▼  [LSP: on open/save]
  token n-gram data (JSON)          symbol + usage index
        │                                    │
        ▼  [scripts/ml_train.py]             ▼  [LSP: _ProjectIndexer]
  Store tables (global model)       .prove_cache/
    data/lsp-ml-store/                index/current.prv   (symbols, types)
      completions/current.prv         bigrams/current.prv (local n-grams)
      bigrams/current.prv
        │                                    │
        └──────────────┬─────────────────────┘
                       ▼  [lsp.py completion handler]
              merged ranked completions
```

## Phases

### Phase 1 — Data Extraction (Python)

`scripts/ml_extract.py`

- Walk all `.prv` files (stdlib, examples, test fixtures) using existing `Lexer` + `Parser`
- Extract completion contexts: for each token position, record preceding 2–3 tokens
  as context and current token as label
- Extract `(verb, param-type, return-type)` triples from `FunctionDef` nodes for
  type suggestions
- Output: `data/completions_raw.json`

### Phase 2 — Model Training (Python)

`scripts/ml_train.py`

- Read `completions_raw.json`
- Build frequency tables: `(tok_n-2, tok_n-1) → [(tok_n, count)]`
- Normalize to probabilities, keep top-K per context (K=10)
- Output: `data/completions_model.json` + `data/bigrams_model.json`

N-gram statistics over a DSL work very well and fit naturally into `:[Lookup]` tables.
No neural nets needed for v1.

### Phase 3 — Model Storage in Prove (Store stdlib)

`tools/lsp-ml/store_model.prv`

```prove
import Store
import InputOutput

inputs store_model(data_path String, store_path String)!
from
    db as Store = store(store_path)!
    // load JSON, populate StoreTable, save
```

Until Prove IO is fully stable, a thin Python bridge (`scripts/ml_store.py`) writes
the Store tables directly using the same `.prv` file format.

Store layout:

```
data/lsp-ml-store/
    completions/current.prv   # context → completion entries
    bigrams/current.prv       # bigram frequency table
```

Tables use `:[Lookup]` types:

```prove
type Bigram:[Lookup] is String String Integer where
    ...  // (prev_token, next_token, count)
```

### Phase 4 — Project Indexer in LSP (Python, `lsp.py`)

Add `_ProjectIndexer` class that runs inside the LSP process:

- **Root detection**: walk up from the opened file to find the project root (directory
  containing `prove.toml` or the first `.prv` file at root level)
- **Cache location**: `<project-root>/.prove_cache/` — created on first index
- **Triggers**: index on `textDocument/didOpen`, `textDocument/didSave`; full re-index
  on workspace open
- **What is indexed**:
  - All symbol names (functions, types, constants) defined in project `.prv` files
  - Local bigrams extracted from project source
  - Per-file symbol tables for go-to-definition / hover
- **Storage**: same Store table format as the global model — `:[Lookup]` tables in
  `.prove_cache/index/` and `.prove_cache/bigrams/`
- **Invalidation**: each table carries a version hash; stale entries are patched via
  `diffs`/`patches` (Store optimistic concurrency handles concurrent editor saves)

```
<project-root>/
    .prove_cache/
        index/
            current.prv      # symbol table: name → file, line, kind, signature
            versions/
        bigrams/
            current.prv      # local n-gram frequencies
            versions/
```

`.prove_cache/` should be added to the project's `.gitignore`.

### Phase 5 — Merged Completion Handler (Python, `lsp.py`)

Add `_MLCompletionProvider` class that merges both sources:
- Loads global model tables from `data/lsp-ml-store/` at server startup
- Loads project index from `.prove_cache/` when a workspace is opened
- In completion handler: query both, score and merge, deduplicate

```python
# In lsp.py completion handler:
global_suggestions  = global_model.complete(context_tokens, prefix)
project_suggestions = project_index.complete(context_tokens, prefix)
items = merge_completions(symbol_items, keyword_items,
                          project_suggestions, global_suggestions)
```

Project suggestions are ranked above global ones for the same prefix — local
context beats corpus frequency.

## File Map

| File | Language | Notes |
|------|----------|-------|
| `scripts/ml_extract.py` | Python | New |
| `scripts/ml_train.py` | Python | New |
| `scripts/ml_store.py` | Python | New — bridge until Prove IO is ready |
| `tools/lsp-ml/store_model.prv` | Prove | New — PoC, expected to fail until impl03 done |
| `prove-py/src/prove/lsp.py` | Python | Add `_ProjectIndexer` + `_MLCompletionProvider` |

## What This Demonstrates

- Store stdlib storing real structured data (ML weights as lookup tables)
- `:[Lookup]` binary tables for fast O(1) inference in the LSP
- Project-local indexing with `.prove_cache/` for workspace-aware completions
- Feedback loop: as more `.prv` code is written, the model can be retrained and
  Store tables updated with `diffs`/`patches` — no full rewrite needed
- Store optimistic concurrency naturally handles concurrent LSP saves without locking
