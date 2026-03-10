# LSP ML PoC — Store-Backed Completion Model

## What This Is

The Prove LSP (`prove-py/src/prove/lsp.py`) already provides diagnostics, hover,
go-to-definition, and basic keyword/symbol completions. Those completions are purely
structural — they know what symbols exist but not which ones are likely given the
current context.

This PoC adds **context-aware completions** by training a statistical model on `.prv`
source code and serving it directly from the LSP. The model is stored as Prove
`:[Lookup]` tables (impl02) managed by the Store stdlib (impl03), which makes this
also a real-world exercise of those two features.

The approach is **n-gram statistics**, not neural networks. Given the last 1–2 tokens
before the cursor, the model returns the tokens most frequently seen next in the
corpus. For a small DSL this works well and is fast enough to query inline in the LSP
without a separate process.

## Background Reading

Before starting, read these in order:

1. `future/store/impl02-binary-lookup.md` — `:[Lookup]` types and how they compile to C arrays
2. `future/store/impl03-store-stdlib.md` — Store stdlib: versioned table storage, diffs, merges
3. `prove-py/src/prove/lsp.py` — existing LSP, especially the completion handler near the bottom

## Two Index Sources

The LSP maintains two separate indexes, merged at completion time:

| Source | Scope | Location | Who builds it |
|--------|-------|----------|---------------|
| **Global model** | stdlib + all `.prv` corpus | `data/lsp-ml-store/` (committed) | Offline training scripts, rebuilt manually when corpus grows |
| **Project index** | current workspace `.prv` files | `<project-root>/.prove_cache/` | LSP itself, incrementally on every file open/save |

The global model knows Prove idioms from the full codebase. The project index knows
the specific symbols, types, and patterns in the workspace the developer is editing.
At completion time, project suggestions are ranked above global ones.

## Architecture

```
OFFLINE (run once, output committed to repo)
────────────────────────────────────────────
stdlib + examples + tests .prv files
        │
        ▼  scripts/ml_extract.py
           Uses Lexer + Parser to walk all .prv files.
           Outputs token sequences as data/completions_raw.json.
        │
        ▼  scripts/ml_train.py
           Builds (prev2, prev1) → [(next_token, count)] frequency tables.
           Outputs data/completions_model.json + data/bigrams_model.json.
        │
        ▼  scripts/ml_store.py  (Python bridge, see Phase 3)
           Writes trained tables into Store format.
           Output committed at data/lsp-ml-store/.

ONLINE (runs inside the LSP process)
─────────────────────────────────────
On workspace open:
  LSP loads data/lsp-ml-store/ → _MLCompletionProvider (global model)
  LSP detects project root → loads .prove_cache/ → _ProjectIndexer

On textDocument/didOpen, textDocument/didSave:
  _ProjectIndexer re-indexes changed file → updates .prove_cache/

On textDocument/completion:
  global_suggestions  ← global model query (prev2, prev1, prefix)
  project_suggestions ← project index query (prev2, prev1, prefix)
  final items ← merge(symbol_items, keyword_items,
                       project_suggestions, global_suggestions)
```

## Prerequisites

| Requirement | Status | Notes |
|------------|--------|-------|
| `:[Lookup]` types (impl02) | Mostly done | `binary` keyword restriction (E397) pending — not blocking for PoC |
| Store stdlib (impl03) | Mostly done | `merges` + tests remaining — Phase 3 needs `loads`/`saves`/`compiles` only |
| Process execution (impl04) | Done | Not needed until Phase 3 Prove program |
| Async verbs (impl01) | Not required | Phases 1–5 are all synchronous |

**Phases 1–2 can start immediately** (Python only, no compiler changes needed).
Phase 3 in Prove unblocks once impl03 `loads`/`saves` tests pass.

## Phases

### Phase 1 — Data Extraction

**New file:** `scripts/ml_extract.py`

Walks all `.prv` source using the existing `Lexer` and `Parser` (already in
`prove-py/src/prove/`) and produces a JSON training dataset.

For each token in each file, record:
- The 2 preceding tokens as context (`prev2`, `prev1`)
- The current token as the label (`next`)
- The file and line number (for debugging bad training data)

Also extract structured triples from `FunctionDef` AST nodes:
- `(verb, first_param_type, return_type)` — for type-aware completions after a verb

Source files to walk:
- `prove-py/src/prove/stdlib/` — highest signal, idiomatic Prove
- `examples/` — user-facing patterns
- `prove-py/tests/` fixture `.prv` snippets — broad coverage

Output: `data/completions_raw.json`

```json
[
  {"prev2": "transforms", "prev1": "run", "next": "(", "file": "stdlib/text.prv", "line": 12},
  {"prev2": "run", "prev1": "(", "next": "input", "file": "stdlib/text.prv", "line": 12},
  ...
]
```

**Exit criteria:**
- [ ] Script runs without error against the full repo
- [ ] Output covers stdlib, examples, and test fixtures
- [ ] `data/completions_raw.json` committed (or generated as part of build)

---

### Phase 2 — Model Training

**New file:** `scripts/ml_train.py`

Reads `data/completions_raw.json` and builds frequency tables.

Algorithm:
1. Group records by `(prev2, prev1)` context key
2. Count occurrences of each `next` token per context
3. Sort by count descending, keep top 10 per context (configurable via `K`)
4. Repeat for unigram fallback: group by `prev1` only (used when `prev2` is unknown)

Output:
- `data/completions_model.json` — bigram model `{context_key: [(token, count), ...]}`
- `data/bigrams_model.json` — unigram fallback `{prev1: [(token, count), ...]}`

No probabilities needed at this stage — relative counts are enough for ranking.

**Exit criteria:**
- [ ] Script produces both output files without error
- [ ] Top completions for common contexts are sensible (manual spot-check)
- [ ] Both output files committed alongside extraction output

---

### Phase 3 — Model Storage via Store Stdlib

**New files:**
- `scripts/ml_store.py` — Python bridge (immediate)
- `tools/lsp-ml/store_model.prv` — Prove program (later, when impl03 is stable)

#### Python bridge (use first)

`scripts/ml_store.py` reads the trained JSON and writes Store-format `.prv` files
directly. The Store format for a lookup table is a `.prv` file containing a
`:[Lookup]` type definition — the same format impl03 reads and writes internally.

Store layout at `data/lsp-ml-store/`:

```
data/lsp-ml-store/
    bigrams/
        current.prv     ← bigram model as :[Lookup] table
        versions/
    completions/
        current.prv     ← completion contexts as :[Lookup] table
        versions/
```

Table schemas:

```prove
// bigrams/current.prv
// (prev_token, next_token) → frequency count
type Bigram:[Lookup] is String String Integer where
    transforms_run    | "transforms" | "run"    | 142
    run_open_paren    | "run"        | "("      | 138
    ...

// completions/current.prv
// (prev2, prev1) → top completion as pipe-separated ranked list
type Completion:[Lookup] is String String String where
    transforms_name   | "transforms" | "name"  | "(|String|Integer"
    ...
```

The pipe-separated completion string is a simple encoding for top-K results within
the lookup table value constraints. The LSP splits on `|` to recover the ranked list.

#### Prove program (target state)

`tools/lsp-ml/store_model.prv` — a Prove program that reads the JSON produced by
Phase 2 and writes it into the Store. Mark with `Expected to fail: build.` in its
`narrative:` until impl03 tests are passing.

**Exit criteria:**
- [ ] `scripts/ml_store.py` writes valid Store tables at `data/lsp-ml-store/`
- [ ] Tables load correctly in a manual Python REPL test
- [ ] `tools/lsp-ml/store_model.prv` stub exists (even if failing)

---

### Phase 4 — Project Indexer in LSP

**Modified file:** `prove-py/src/prove/lsp.py`

Add `_ProjectIndexer` class. This runs inside the LSP process — no subprocess.

**Project root detection** (called when any `.prv` file is opened):

Walk up from the opened file's directory until finding:
1. A `prove.toml` file, or
2. A directory that is the workspace root reported by the LSP client

Fall back to the directory of the opened file if neither is found.

**Cache location:** `<project-root>/.prove_cache/` — created on first index run.

**What gets indexed** per project file:
- Every `FunctionDef`: name, verb, param names+types, return type, file, line
- Every `TypeDef` and `ConstantDef`: name, kind, file, line
- Local token bigrams (same format as global model)

**Storage format:** same Store `:[Lookup]` table files as the global model,
written to `.prove_cache/index/current.prv` and `.prove_cache/bigrams/current.prv`.

**Incremental updates:** on `didSave`, re-parse only the changed file and patch
the Store table using `diffs`/`patches`. On full workspace open, re-index everything.
Store's optimistic concurrency (`saves` rejects stale versions) handles the case where
multiple files are saved quickly — the second save reloads and retries automatically.

**Triggers:**
- `workspace/didOpen` → full re-index of all `.prv` files under project root
- `textDocument/didSave` → re-index saved file, patch tables
- `textDocument/didOpen` → re-index if file not yet in cache

Cache layout:

```
<project-root>/
    .prove_cache/
        index/
            current.prv      # symbols: name → file, line, kind, signature
            versions/
        bigrams/
            current.prv      # local n-gram frequencies
            versions/
```

Add `.prove_cache/` to the default `.gitignore` template in `scripts/dev-setup.sh`
and document it in `docs/`.

**Exit criteria:**
- [ ] `_ProjectIndexer` detects project root correctly for stdlib, examples, and a fresh project
- [ ] `.prove_cache/` is created and populated on workspace open
- [ ] Table is updated (not fully rebuilt) on single-file save
- [ ] No LSP errors or crashes when `.prove_cache/` is missing or corrupted

---

### Phase 5 — Merged Completion Handler

**Modified file:** `prove-py/src/prove/lsp.py`

Add `_MLCompletionProvider` that merges global model + project index into the
existing completion response.

Query logic:
1. Extract the 2 tokens immediately before the completion cursor from the document
2. Look up `(prev2, prev1)` in project bigrams → ranked list
3. Look up `(prev2, prev1)` in global bigrams → ranked list
4. Fall back to `(prev1,)` unigram if bigram has no match
5. Merge: project results first, then global results, deduplicate by token value
6. Append existing symbol/keyword completions at the end

```python
# Sketch of the completion handler addition in lsp.py:
context = _extract_context_tokens(doc, params.position, n=2)
project_hits = project_indexer.complete(context, prefix)
global_hits  = global_model.complete(context, prefix)
ml_items = _to_completion_items(project_hits + global_hits, seen=set())
return existing_items + ml_items
```

`_extract_context_tokens` tokenizes the line up to the cursor using the existing
`Lexer`, returning the last N non-whitespace tokens.

**Exit criteria:**
- [ ] Completions include ML suggestions in the VS Code / Neovim LSP client
- [ ] Project-local symbols rank above global suggestions for the same prefix
- [ ] No measurable latency regression on completion requests (target: < 20ms added)
- [ ] Gracefully degrades to existing completions if model files are missing

---

## File Map

| File | Language | Status | Notes |
|------|----------|--------|-------|
| `scripts/ml_extract.py` | Python | New | Phase 1 |
| `scripts/ml_train.py` | Python | New | Phase 2 |
| `scripts/ml_store.py` | Python | New | Phase 3 — Python bridge |
| `data/lsp-ml-store/` | Store `.prv` | New | Phase 3 — committed model artifact |
| `tools/lsp-ml/store_model.prv` | Prove | New | Phase 3 — Prove target, expected to fail initially |
| `prove-py/src/prove/lsp.py` | Python | Modify | Phases 4–5: add `_ProjectIndexer` + `_MLCompletionProvider` |

## What This Demonstrates

- The Store stdlib managing real structured data (statistical model as versioned lookup tables)
- `:[Lookup]` binary tables providing O(1) inference suitable for inline LSP use
- Project-local indexing: the LSP builds and maintains its own workspace cache without
  a separate daemon or database
- Store's `diffs`/`patches` enabling incremental cache updates — only changed files
  are re-indexed, not the whole project
- Store's optimistic concurrency handling concurrent editor saves without file locking
