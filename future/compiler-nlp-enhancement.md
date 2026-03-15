# Compiler NLP Enhancement — Store-First, Self-Hosting-Aligned

## Goal

Improve the intent system's NLP quality (prose-to-code matching, stub
generation, intent parsing) while **aligning every decision with V2.0
self-hosting**.

**Core principle:** If Prove supports a feature, the tooling uses it.  All
persisted NLP data lives in `.pdat` files via the Store module.  spaCy and NLTK
are acceptable *temporary* compute engines until the Language stdlib module
(pure C) replaces them.  No rebuild is needed as long as storage goes through
the Store.

---

## Design Rules

1. **Storage is always `.pdat`.**  Every piece of NLP data the compiler
   persists — synonym tables, stdlib indexes, similarity caches, ML features —
   is written and read via `store_binary.py` (`write_pdat` / `read_pdat`).
   Never pickle, JSON, or SQLite.

2. **spaCy/NLTK are bridge dependencies.**  They improve NLP *compute* quality
   today.  When the Language stdlib module lands (plan 3), its C functions
   (Porter stemmer, Levenshtein, stopwords, normalize) replace spaCy/NLTK
   one-for-one.  The `.pdat` layer stays untouched.

3. **Fallback is always available.**  Every NLP function has three tiers:
   spaCy/NLTK (best) > hand-rolled Python (`_nl_intent.py`) > no-op.  The
   compiler never *requires* optional deps.

4. **`build_stores.py` is the generation entry point.**  Any new NLP data store
   gets a builder function there.  `prove advanced setup-nlp` calls it after downloading
   models.  Pre-built `.dat` files ship as package data.

---

## Current State (What's Done)

### Phase 1 — Optional Dependency Setup (COMPLETE)

- `pyproject.toml` has `[nlp]` optional dep group (spaCy + NLTK)
- `src/prove/nlp.py` exists with lazy backend detection, 6 public functions
- `prove advanced setup-nlp` CLI command in `cli.py`

### Phase 2 — Core NLP Functions (COMPLETE)

All six functions implemented in `nlp.py` with spaCy/NLTK path + fallback:

| Function | spaCy/NLTK path | Fallback |
|----------|----------------|----------|
| `lemmatize(word)` | `token.lemma_` | `normalize_noun()` suffix strip |
| `extract_parts(text)` | POS tagger (NOUN/VERB) | `extract_nouns()` + `implied_verbs()` |
| `synonyms(word, pos)` | WordNet synsets | `VERB_SYNONYMS` dict |
| `text_similarity(a, b)` | Word vectors cosine | Jaccard index |
| `parse_intent_phrase(text)` | Dependency parse | Regex + implied_verbs |
| `match_stdlib_function(query)` | Lemma + synonym + vector | Verb match + noun substring |

### Phase 2.5 — PDAT Store Layer (COMPLETE)

- `nlp_store.py` reads verb synonyms from `verb_synonyms.dat` (`.pdat`)
- `nlp_store.py` builds/reads `stdlib_index.dat` (`.pdat`) for docstring index
- `build_stores.py` generates `verb_synonyms.dat` from `VERB_SYNONYMS`
- `_nl_intent.py` loads synonyms via `nlp_store.load_verb_synonyms()`
- `cli.py` calls `build_stdlib_index()` during project cache update

### Unit Tests (COMPLETE)

- `test_nlp.py` — TestLemmatize, TestExtractParts, TestSynonyms,
  TestTextSimilarity, TestParseIntentPhrase, TestFallbackMode, TestHasNlpBackend
- `test_nlp_store.py` — store load/reset tests
- `test_store_binary.py` — PDAT format, round-trip, error handling

---

## Remaining Work

### Phase 3: Integration — Wire `nlp.py` Into the Compiler (COMPLETE)

All four integration points are wired.  Each function tries `nlp.py` first
and falls through to the original hand-rolled logic when backends are absent.
Circular fallback between `nlp.py` ↔ `_nl_intent.py` is broken by having
`nlp.py` fallbacks import `_*_fallback` variants directly.

#### 3a. `_nl_intent.py` — Delegate to `nlp.py` (DONE)

Four functions renamed to `_*_fallback`, wrappers delegate to `nlp.py`:
- `normalize_noun` → `nlp.lemmatize`
- `implied_verbs` → `nlp.extract_parts` + verb normalization
- `extract_nouns` → `nlp.extract_parts`
- `prose_overlaps` → `nlp.text_similarity` (threshold 0.2)

#### 3b. `_body_gen.py` — Better stdlib matching (DONE)

`find_stdlib_matches` delegates to `nlp.match_stdlib_function` when backend
available.  `_nlp_active` guard prevents infinite recursion since
`match_stdlib_function` calls back into `find_stdlib_matches`.

#### 3c. `intent_parser.py` — Smarter phrase parsing (DONE)

`_parse_verb_phrase` tries `nlp.parse_intent_phrase` first, builds VerbPhrase
from structured parse.  Falls through to existing regex logic.

#### 3d. `intent_generator.py` — Better parameter inference (DONE)

`_infer_params_from_vocab` uses `nlp.text_similarity` for fuzzy vocabulary
matching (threshold 0.3) when backend available, exact substring match otherwise.

### Phase 4: Expand PDAT Stores (COMPLETE)

All new NLP-derived data persists as `.pdat`.  This phase adds stores beyond
the existing verb synonyms and stdlib index.

#### 4a. Synonym expansion store — `synonym_cache.dat` (DONE)

When NLTK WordNet discovers synonyms beyond `VERB_SYNONYMS`, cache them:

```python
# In nlp_store.py
def cache_expanded_synonyms(expansions: dict[str, list[str]]) -> Path:
    """Write WordNet-expanded synonyms to PDAT."""
    variants = [(word, syns) for word, syns in expansions.items()]
    out = _data_path("synonym_cache.dat")
    write_pdat(out, "SynonymCache", ["String"] * max_cols, variants)
    return out
```

Add a builder to `build_stores.py` that runs WordNet expansion once and ships
the result as package data.  No WordNet needed at runtime — just the `.pdat`.

#### 4b. Similarity matrix store — `similarity_matrix.dat` (DONE)

Pre-compute pairwise similarity scores for ~200 stdlib functions:

```python
def build_similarity_matrix(stdlib_index) -> Path:
    """Pre-compute function×function similarity as PDAT."""
    # Uses spaCy vectors during build, stored as PDAT for runtime
    ...
```

Used by `_body_gen.py` to rank alternative matches without loading spaCy at
compile time.

#### 4c. Semantic features store — `semantic_features.dat` (DONE)

For the ML pipeline, extract lemmatized keywords and (optionally) doc vectors
per stdlib function:

```python
# In build_stores.py
def build_semantic_features() -> None:
    """Extract NLP features from stdlib docstrings into PDAT."""
    # variant = "module.function", columns = [lemmatized_keywords, ...]
    ...
```

This replaces the JSON output from `ml_extract.py` for semantic features.

#### 4d. Update `build_stores.py` (DONE)

```python
if __name__ == "__main__":
    build_verb_synonyms()      # existing
    build_synonym_cache()       # 4a — requires NLTK
    build_similarity_matrix()   # 4b — requires spaCy
    build_semantic_features()   # 4c — requires spaCy
    build_stdlib_index()        # existing, moved here from cli.py cache
```

All builders are idempotent.  `prove advanced setup-nlp` calls `build_stores.py` after
downloading models.  The resulting `.dat` files ship as package data so
end users never need spaCy/NLTK installed.

### Phase 5: Tests

#### 5a. Integration tests for delegation (Phase 3) — COMPLETE

`test_nl_intent.py` and `test_body_gen.py` continue to pass (151 tests,
6 skipped).  Full suite: 1401 passed, 6 skipped.  Delegation is transparent
in fallback mode.

#### 5b. Store round-trip tests (Phase 4) — COMPLETE

Each new `.pdat` store gets a test in `test_nlp_store.py`:
- Write store → read store → verify data integrity
- Missing file → graceful fallback to in-memory construction

#### 5c. End-to-end integration test

`.intent` file -> `prove advanced generate project.intent` -> valid `.prv` ->
`prove check` passes.  Run both with and without NLP backends.

### Phase 6: CLI Flags (COMPLETE)

- **6a. `prove advanced setup-nlp`** — COMPLETE.  Downloads models + rebuilds stores.
- **6b. `prove advanced generate --nlp` / `--no-nlp`** — COMPLETE.  Explicitly control NLP use.
- **6c. `prove advanced intent --nlp` / `--no-nlp`** — COMPLETE.  Force NLP for coverage checking.
- **6d. `prove check --nlp-status`** — COMPLETE.  Reports backend and `.pdat` store availability.

---

## Transition Path

```
                    Storage (survives every transition)
                    ┌─────────────────────────────┐
                    │  .pdat files via Store module │
                    └──────────────┬──────────────┘
                                   │
        ┌──────────────────────────┼──────────────────────────┐
        │                          │                          │
   Now (V1.0)               Later (V1.x)              V2.0 Self-Host
   ┌──────────┐           ┌──────────────┐           ┌──────────────┐
   │ spaCy    │  replace  │ Language      │  same     │ Language      │
   │ NLTK     │ ───────>  │ stdlib (C)    │ ───────>  │ stdlib (Prove)│
   │ (Python) │           │ Porter stem   │           │ import        │
   │          │           │ Levenshtein   │           │ Language      │
   │          │           │ stopwords     │           │               │
   │          │           │ normalize     │           │               │
   └──────────┘           └──────────────┘           └──────────────┘
        │                        │                          │
        └────────────────────────┴──────────────────────────┘
                                 │
                    All read/write the same .pdat files
```

**What survives each transition:**
- `.pdat` stores — always (the contract)
- `nlp_store.py` API — always (Python reads `.pdat` until V2.0)
- `nlp.py` function signatures — always (callers don't change)
- spaCy/NLTK — dropped when Language stdlib replaces them
- Hand-rolled `_nl_intent.py` fallbacks — dropped when Language stdlib lands

**What changes:**
- Compute backend swaps (spaCy -> Language C -> Language Prove)
- `build_stores.py` generators may switch from spaCy to Language C calls
- V2.0 compiler reads `.pdat` directly via `Store` module (no Python)

---

## Graceful Degradation

| Function | Tier 1: spaCy/NLTK | Tier 2: Hand-rolled | Tier 3: Future (Language C) |
|----------|-------------------|--------------------|-----------------------------|
| `lemmatize()` | `token.lemma_` | 8 suffix-strip rules | `Language.stem()` / `Language.root()` |
| `extract_parts()` | POS tagger | stopword filter + synonym table | `Language.words()` + POS heuristic |
| `synonyms()` | WordNet synsets (~150K) | `VERB_SYNONYMS` (~60) | Pre-built `.pdat` from WordNet (static) |
| `text_similarity()` | Word vectors (cosine) | Jaccard index | `Language.similarity()` (Levenshtein-based) |
| `parse_intent_phrase()` | Dependency parse | Regex patterns | `Language.words()` + verb table lookup |
| `match_stdlib_function()` | Lemma + vector + synonym | Verb match + noun substr | Stem + similarity + `.pdat` matrix |

Tier 2 is always available (no deps).  Tier 3 replaces Tier 1 when Language
stdlib is implemented — same quality or better, zero Python deps.

---

## File Summary

| File | Action | Status |
|------|--------|--------|
| `pyproject.toml` | `[nlp]` optional dep group | DONE |
| `src/prove/nlp.py` | NLP backend with fallback | DONE |
| `src/prove/nlp_store.py` | PDAT-backed verb synonyms + stdlib index | DONE |
| `src/prove/cli.py` | `prove advanced setup-nlp` command | DONE |
| `scripts/build_stores.py` | PDAT generator for verb synonyms | DONE |
| `tests/test_nlp.py` | Unit tests for `nlp.py` | DONE |
| `tests/test_nlp_store.py` | Store round-trip tests | DONE |
| `src/prove/_nl_intent.py` | Delegate to `nlp.py` | DONE (Phase 3a) |
| `src/prove/_body_gen.py` | Delegate `find_stdlib_matches` | DONE (Phase 3b) |
| `src/prove/intent_parser.py` | Delegate `_parse_verb_phrase` | DONE (Phase 3c) |
| `src/prove/intent_generator.py` | Delegate `_infer_params_from_vocab` | DONE (Phase 3d) |
| `src/prove/nlp_store.py` | Add synonym cache + similarity matrix + semantic features | DONE (Phase 4a-c) |
| `scripts/build_stores.py` | Add builders for new stores | DONE (Phase 4d) |
| `src/prove/_body_gen.py` | Similarity matrix score blending | DONE (Phase 4b) |
| `src/prove/cli.py` | `--nlp/--no-nlp`, `--nlp-status` flags | DONE (Phase 6b-d) |
| `tests/test_nlp_store.py` | Round-trip tests for all stores | DONE (Phase 5b) |

---

## Priority Order

1. ~~**Phase 3a-b: Wire `_nl_intent.py` + `_body_gen.py`**~~ — DONE
2. ~~**Phase 3c-d: Wire intent parser + generator**~~ — DONE
3. ~~**Phase 5a: Integration tests for delegation**~~ — DONE (1401 pass)
4. ~~**Phase 4a: Synonym expansion store**~~ — DONE
5. ~~**Phase 4b: Similarity matrix store**~~ — DONE
6. ~~**Phase 5b: Store round-trip tests**~~ — DONE (1444 pass)
7. ~~**Phase 6b-d: CLI flags**~~ — DONE
8. ~~**Phase 4c: ML semantic features**~~ — DONE
9. **Phase 5c: End-to-end integration test** — `.intent` → generate → check (both with/without NLP)
