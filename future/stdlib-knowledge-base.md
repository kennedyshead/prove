# Stdlib Knowledge Base — Docstrings as Training Data

Prove's standard library (18 modules: Character, Text, Table, System, Parse, Math,
Types, List, Path, Pattern, Format, Error, Random, Time, Bytes, Hash, Log, Network)
has `///` doc comments on every function and type. These docstrings are natural
language descriptions of what each function does — effectively the stdlib's version
of `explain` (step-by-step documentation of a function's behavior), `intent` (why a
function exists), and `chosen` (which approach was taken). These are Prove-specific
prose annotation blocks that the compiler parses and verifies against the code.

Today these docstrings are **discarded during ML training** — the extraction script
(`ml_extract.py`) explicitly skips `DOC_COMMENT` tokens. The ML model that powers
LSP code completions learns token sequences (what code follows what code) but not
their meaning (what the code is for).

This document describes how to make stdlib docstrings the foundation of the
entire generation and intent system. This is cross-cutting work that feeds Phase 1
(verb-prose mapping), Phase 2 (body generation from stdlib knowledge), and Phase 3
(the `.intent` file LSP, which suggests stdlib capabilities as you type).

---

## Problem: the model is blind to meaning

Today's training pipeline:

```
stdlib .prv files → ml_extract.py → completions_raw.json → ml_train.py → ml_store.py
                         │
                    skips DOC_COMMENT ← !!
```

The model learns token sequences:
```
("creates", "sha256") → ("(", "data", "ByteArray", ")")
```

But it doesn't learn the semantic bridge:
```
"Hash a byte array to SHA-256 digest" → creates sha256(data ByteArray) ByteArray
```

This means:
- `_nl_intent.py` can map "hash" → `creates` via `_PROSE_STEMS`, but it can't
  know that `sha256` is the specific function for hashing
- The `.intent` LSP can't suggest "sha256" when someone writes "creates ... hash"
- Phase 2 body generation can't match "hash using sha-256" to `Hash.sha256()`

The docstrings are the missing link between natural language (declarations,
narratives, intent) and concrete code (stdlib functions).

---

## What stdlib docstrings look like today

Every stdlib function has a `///` doc comment. They are consistently structured:

```prove
/// Hash a byte array to SHA-256 digest
creates sha256(data ByteArray) ByteArray

/// Check if a string contains a substring
validates contains(text String, substring String)

/// Split a string by a separator
transforms split(text String, separator String) List<String>

/// Get the length of a string
reads length(text String) Integer

/// Create a new string builder
creates builder() StringBuilder:[Mutable]
```

Pattern: **`Verb phrase describing what the function does`**

These are short (one line), action-oriented, and always start with a verb
(English verb, not necessarily a Prove verb keyword). They are exactly the
kind of text that maps to `.intent` verb phrases.

---

## What to build

### Part 1 — Docstring extraction in ml_extract.py

**File:** `scripts/ml_extract.py`

Currently the extraction produces two record types: `ngram` and `function_triple`.
Add a third: `docstring_mapping`.

```python
# In extract_file(), after building triples:
for decl in module.declarations:
    if not isinstance(decl, FunctionDef):
        continue
    if not decl.doc_comment:
        continue
    # Extract the doc comment text (strip /// prefix)
    doc_text = decl.doc_comment.strip()

    all_records.append({
        "kind": "docstring_mapping",
        "verb": decl.verb,
        "name": decl.name,
        "doc": doc_text,
        "module": module_name,
        "first_param_type": first_param_type,
        "return_type": return_type,
        "file": rel_path,
    })
```

This captures the semantic bridge: natural language ↔ function identity.

### Part 2 — Docstring-aware training in ml_train.py

**File:** `scripts/ml_train.py`

Add a new model: the **docstring index**. For each docstring, extract:

- **Action words** — the English verbs ("Hash", "Check", "Split", "Get", "Create")
- **Object words** — the nouns ("byte array", "string", "substring", "separator")
- **Qualifier words** — modifiers ("SHA-256", "lowercase", "whitespace")

Map these to the function identity (module, name, verb, signature).

```python
def build_docstring_index(records: list[dict]) -> dict:
    """Build word → function mapping from docstring_mapping records.

    Returns: {
        "hash": [{"module": "Hash", "name": "sha256", "verb": "creates", ...}, ...],
        "string": [{"module": "Text", "name": "length", ...}, ...],
        ...
    }
    """
    index: dict[str, list[dict]] = defaultdict(list)
    for rec in records:
        if rec["kind"] != "docstring_mapping":
            continue
        words = set(re.findall(r"[a-zA-Z]{3,}", rec["doc"].lower()))
        entry = {
            "module": rec["module"],
            "name": rec["name"],
            "verb": rec["verb"],
            "doc": rec["doc"],
            "first_param_type": rec.get("first_param_type"),
            "return_type": rec.get("return_type"),
        }
        for word in words:
            index[word].append(entry)
    return dict(index)
```

Output: `data/docstring_index.json`

### Part 3 — Docstring model in ml_store.py

**File:** `scripts/ml_store.py`

Write a new lookup table alongside bigrams and completions:

```
data/lsp-ml-store/
    bigrams/current.prv        ← existing
    completions/current.prv    ← existing
    docstrings/current.prv     ← NEW
```

Format:
```prove
type DocstringMap:[Lookup] is String String String String String where
    r00000 | "hash" | "Hash" | "sha256" | "creates" | "Hash a byte array to SHA-256 digest"
    r00001 | "hash" | "Hash" | "sha512" | "creates" | "Hash a byte array to SHA-512 digest"
    r00002 | "hash" | "Hash" | "blake3" | "creates" | "Hash a byte array to BLAKE3 digest"
    r00003 | "split" | "Text" | "split" | "transforms" | "Split a string by a separator"
    ...
```

Columns: `keyword | module | function | verb | docstring`

### Part 4 — Load docstring model in LSP

**File:** `prove-py/src/prove/lsp.py`

Add `_load_docstring_model()` alongside `_load_global_model()`:

```python
_docstring_index: dict[str, list[dict]] | None = None

def _load_docstring_model() -> None:
    global _docstring_index
    if _docstring_index is not None:
        return
    _docstring_index = defaultdict(list)
    doc_path = _GLOBAL_MODEL_DIR / "docstrings" / "current.prv"
    for row in _parse_lookup_rows(doc_path):
        if len(row) >= 5:
            keyword, module, name, verb, doc = row[0], row[1], row[2], row[3], row[4]
            _docstring_index[str(keyword)].append({
                "module": str(module),
                "name": str(name),
                "verb": str(verb),
                "doc": str(doc),
            })
```

### Part 5 — Use docstring index in _nl_intent.py

**File:** `prove-py/src/prove/_nl_intent.py` (extends Phase 1 module)

`implied_verbs()` already maps prose words to Prove verbs via `_PROSE_STEMS`.
Add a parallel function that maps prose words to specific stdlib functions:

```python
def implied_functions(
    text: str,
    docstring_index: dict[str, list[dict]] | None = None,
) -> list[dict]:
    """Return stdlib functions implied by words in prose text.

    Each result: {"module": "Hash", "name": "sha256", "verb": "creates",
                  "doc": "Hash a byte array to SHA-256 digest", "score": 0.8}

    Score is based on word overlap between text and function docstring.
    """
    if docstring_index is None:
        return []
    words = set(re.findall(r"[a-z]{3,}", text.lower()))
    candidates: dict[tuple[str, str], dict] = {}  # (module, name) → best entry

    for word in words:
        for entry in docstring_index.get(word, []):
            key = (entry["module"], entry["name"])
            if key not in candidates:
                candidates[key] = {**entry, "matched_words": set()}
            candidates[key]["matched_words"].add(word)

    results = []
    for key, entry in candidates.items():
        # Score: fraction of text words that matched this function's docstring
        doc_words = set(re.findall(r"[a-z]{3,}", entry["doc"].lower()))
        overlap = entry["matched_words"] & doc_words
        score = len(overlap) / max(len(words), 1)
        results.append({
            "module": entry["module"],
            "name": entry["name"],
            "verb": entry["verb"],
            "doc": entry["doc"],
            "score": score,
        })

    return sorted(results, key=lambda r: -r["score"])
```

This is the function that Phase 2 body generation and Phase 3 `.intent` LSP
both call to resolve natural language to concrete stdlib functions.

---

## Impact on Each Phase

### Phase 1 — `_nl_intent.py` gets `implied_functions()`

Today (planned): `implied_verbs("hash a byte array")` → `{"creates", "transforms"}`
With docstrings: `implied_functions("hash a byte array")` →
```python
[
    {"module": "Hash", "name": "sha256", "verb": "creates", "score": 0.8},
    {"module": "Hash", "name": "sha512", "verb": "creates", "score": 0.8},
    {"module": "Hash", "name": "blake3", "verb": "creates", "score": 0.6},
]
```

The verb mapping goes from abstract ("some kind of creates") to concrete
("specifically Hash.sha256").

### Phase 2 — Body generation resolves to stdlib calls

The `_find_stdlib_matches()` function from phase2 uses `implied_functions()`
instead of scanning all stdlib signatures manually:

```python
# Before (Phase 2 without docstrings):
# Must iterate all stdlib modules and all functions, matching by verb + noun
# This is slow and imprecise — "hash" might match many things

# After (Phase 2 with docstrings):
matches = implied_functions("hash a byte array", docstring_index)
# Directly returns Hash.sha256 with high confidence
```

### Phase 3 — `.intent` LSP knows what's possible

When the user types in a module block of a `.intent` file:

```
  module Auth
    creates |
```

The LSP queries the docstring index for all `creates` functions:

```
creates sha256      — Hash a byte array to SHA-256 digest       [Hash]
creates sha512      — Hash a byte array to SHA-512 digest       [Hash]
creates blake3      — Hash a byte array to BLAKE3 digest        [Hash]
creates hmac        — Create an HMAC-SHA256 signature           [Hash]
creates builder     — Create a new string builder               [Text]
creates byte        — ...                                       [Bytes]
```

After typing more context:

```
  module Auth
    creates ... hash|
```

The LSP filters to docstrings containing "hash":

```
creates sha256      — Hash a byte array to SHA-256 digest       [Hash]
creates sha512      — Hash a byte array to SHA-512 digest       [Hash]
creates blake3      — Hash a byte array to BLAKE3 digest        [Hash]
creates hmac        — Create an HMAC-SHA256 signature           [Hash]
```

The user picks one, and the intent line is completed:

```
  module Auth
    creates password hashes using SHA-256
```

The generator now knows this maps to `Hash.sha256()` — it's not guessing.

---

## Enriching stdlib docstrings

Some stdlib docstrings are minimal. For the knowledge base to be effective,
docstrings should be informative enough to match diverse phrasings.

### Current quality

Good — most are clear and action-oriented:
```prove
/// Hash a byte array to SHA-256 digest
/// Check if a string contains a substring
/// Split a string by a separator
/// Replace all occurrences of a substring
```

Could be better — some are too terse:
```prove
/// Get the length of a string
```

Better: `/// Read the character count of a string` — now "character", "count",
and "length" all match.

### Guidelines for stdlib docstrings

Each stdlib `///` doc comment should:

1. **Start with an action verb** that maps to the function's Prove verb
2. **Name the domain concept** (hash, string, file, path, etc.)
3. **Include at least one synonym** for the primary operation
4. **Mention the output** when it's not obvious from the name

Good:
```prove
/// Hash a byte array to produce a SHA-256 digest
creates sha256(data ByteArray) ByteArray
```

"Hash", "byte array", "produce", "SHA-256", "digest" — five matchable terms.

Avoid:
```prove
/// SHA-256
creates sha256(data ByteArray) ByteArray
```

Only one matchable term — useless for the knowledge base.

### Audit pass

Before building the knowledge base, do an audit pass over all stdlib docstrings
to ensure they meet the guidelines. This is a one-time effort that permanently
improves generation quality for every project that uses the stdlib.

---

## Files changed

| File | Change |
|---|---|
| `scripts/ml_extract.py` | Add `docstring_mapping` record type; stop skipping DOC_COMMENT for the new record type (ngrams still skip it) |
| `scripts/ml_train.py` | Add `build_docstring_index()`, output `docstring_index.json` |
| `scripts/ml_store.py` | Add `write_docstring_table()`, output `docstrings/current.prv` |
| `prove-py/src/prove/lsp.py` | Add `_load_docstring_model()`, `_docstring_index` |
| `prove-py/src/prove/_nl_intent.py` | Add `implied_functions()` |
| `prove-py/src/prove/stdlib/*.prv` | Audit and enrich docstrings where needed |
| `data/lsp-ml-store/docstrings/current.prv` | **New** — docstring lookup table |

---

## Dependency

This work sits **between Phase 1 and Phase 2**:

- Phase 1's `_nl_intent.py` provides `implied_verbs()` (abstract verb mapping)
- This adds `implied_functions()` (concrete function mapping via docstrings)
- Phase 2's body generation uses `implied_functions()` to resolve to stdlib calls
- Phase 3's `.intent` LSP uses the docstring index for completions

It can be built incrementally:
1. First: add `docstring_mapping` to extraction (no other changes needed)
2. Then: build the index and store it
3. Then: load it in LSP and `_nl_intent.py`
4. Finally: Phase 2 and 3 consume it

```
Phase 1 foundation
    │
    ▼
Stdlib Knowledge Base  ← this document
    │
    ├──▶ Phase 2 body generation (resolve to stdlib calls)
    │
    └──▶ Phase 3 .intent LSP (suggest from stdlib capabilities)
```
