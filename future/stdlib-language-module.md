# stdlib/Language.prv — Native NLP Module

## Goal

Add a `Language` stdlib module providing fundamental NLP primitives implemented
in C, with zero Python dependency at runtime.  Covers tokenization, stemming,
string similarity, n-grams, and basic sentence segmentation — the operations
that are feasible to implement well in pure C and that cover the most common
NLP needs for a systems language.

---

## Background: How Prove Stdlib Modules Work

Prove is an intent-first language that compiles `.prv` source → C → native
binary via gcc/clang.  The Python bootstrap compiler lives at
`prove-py/src/prove/`.

Each stdlib module has four pieces:

1. **`.prv` declaration file** (`prove-py/src/prove/stdlib/<name>.prv`) —
   Declares the module's types and function signatures using Prove syntax.
   Functions marked `binary` have no Prove body; their implementation lives
   in C.  Example from `stdlib/text.prv`:
   ```prove
   module Text
     narrative: """String operations and construction."""

   /// Get the length of a string
   reads length(text String) Integer
   binary
   ```
   Every type and function must have a `///` doc comment.  Verbs are from the
   fixed set: `transforms`, `validates`, `reads`, `creates`, `matches`
   (pure family) and `inputs`, `outputs` (IO family).

2. **C runtime file** (`prove-py/src/prove/runtime/prove_<name>.c` + `.h`) —
   Implements the binary functions.  C function names follow the pattern
   `prove_<module>_<name>` (e.g., `prove_text_length`).  Functions operate on
   Prove's C runtime types:
   - `Prove_String *` — heap-allocated string (len + data)
   - `Prove_List *` — dynamic array of `Prove_Value` (tagged union)
   - `Prove_Table *` — hash map (string keys → `Prove_Value`)
   - `Prove_Option` — tagged union: `{.tag = PROVE_SOME/PROVE_NONE, .value}`
   - `Prove_Result` — tagged union: `{.tag = PROVE_OK/PROVE_ERR, .value/.error}`
   - `int64_t` for Integer, `double` for Float, `bool` for Boolean, `char` for Character
   Memory is managed via `prove_region_*` (arena allocator) — allocate into
   the current region, freed in bulk when the region exits.  Use
   `prove_gc_alloc()` for allocations that escape the region.

3. **Loader registration** (`prove-py/src/prove/stdlib_loader.py`) —
   A `_register_module()` call that maps the module name to its `.prv` file
   and provides a `c_map` dictionary mapping `(verb, function_name)` tuples
   to C function names.  Example from the Text module registration:
   ```python
   _register_module(
       "text",
       display="Text",
       prv_file="text.prv",
       c_map={
           ("reads", "length"):    "prove_text_length",
           ("transforms", "slice"): "prove_text_slice",
           ("validates", "starts"): "prove_text_starts_with",
           # ... etc
       },
   )
   ```

4. **Runtime metadata** (`prove-py/src/prove/c_runtime.py`) — Two registries:
   - `STDLIB_RUNTIME_LIBS`: maps module name → set of C runtime file stems
     needed at link time.  E.g., `"text": {"prove_text", "prove_string"}`.
   - `_RUNTIME_FUNCTIONS`: maps C function name → signature metadata (param
     types, return type, nullable, etc.) used by the emitter for type
     checking and call generation.

   Optionally, `_CORE_FILES` lists runtime files included in every build
   (e.g., `prove_string`, `prove_core`).  Module-specific files like
   `prove_language` should NOT be in `_CORE_FILES` — they're pulled in only
   when the module is imported.

### Test patterns

- **C runtime unit tests** (`prove-py/tests/test_<name>_runtime_c.py`) use
  the `compile_and_run(code, runtime_dir)` helper from `tests/runtime_helpers.py`.
  This compiles a C source string with the runtime headers, links the
  relevant `.c` files, runs the binary, and returns stdout.  Tests use the
  `needs_cc` pytest fixture (skips if no C compiler available).

- **E2e tests** (`tests/e2e/<name>/`) are `.prv` files compiled and executed
  by `scripts/test_e2e.py`.  Each test has a `narrative:` block declaring
  expected behavior.  Expected failures are declared with
  `Expected to fail: check, build.` in the narrative.

---

## Scope: What Goes In vs What Doesn't

### In scope (implementable in C, no trained models)
| Category | Functions |
|----------|-----------|
| **Tokenization** | `words`, `sentences`, `tokens` |
| **Stemming** | `stem` (Porter stemmer), `root` (simple suffix strip) |
| **Similarity** | `distance` (Levenshtein), `similarity` (normalized 0.0–1.0), `soundex`, `metaphone` |
| **N-grams** | `ngrams`, `bigrams` |
| **Normalization** | `normalize` (Unicode NFKC→ASCII folding + lowercase), `transliterate` |
| **Stopwords** | `stopwords` (returns default list), `without_stopwords` (filters) |
| **Frequency** | `frequency` (word→count table), `keywords` (top-N by TF) |

### Out of scope (needs trained models or massive data)
- POS tagging, NER, dependency parsing
- Word embeddings / word vectors
- Sentiment analysis, text classification
- Language detection (statistical model needed)
- Machine translation

---

## API Design (Prove syntax)

```prove
module Language
  narrative: """Natural language processing primitives."""

  /// Token is
  ///   text String
  ///   start Integer
  ///   end Integer
  ///   kind TokenKind
  type Token is binary

  /// TokenKind is
  ///   Word
  ///   Punctuation
  ///   Whitespace
  ///   Number
  type TokenKind is
    Word
    Punctuation
    Whitespace
    Number

// ── Tokenization ───────────────────────────────────────────────

/// Split text into word tokens (Unicode-aware, strips punctuation)
transforms words(text String) List<String>
binary

/// Split text into sentences using punctuation heuristics
transforms sentences(text String) List<String>
binary

/// Split text into classified tokens with positions
transforms tokens(text String) List<Token>
binary

// ── Stemming ───────────────────────────────────────────────────

/// Reduce a word to its stem using the Porter stemming algorithm
transforms stem(word String) String
binary

/// Simple suffix-based root extraction (faster, less accurate)
transforms root(word String) String
binary

// ── String similarity ──────────────────────────────────────────

/// Compute Levenshtein edit distance between two strings
reads distance(left String, right String) Integer
binary

/// Normalized similarity score (0.0 = no match, 1.0 = identical)
reads similarity(left String, right String) Float
binary

/// Compute Soundex phonetic code for a word
transforms soundex(word String) String
binary

/// Compute Double Metaphone phonetic code for a word
transforms metaphone(word String) String
binary

// ── N-grams ────────────────────────────────────────────────────

/// Generate character or word n-grams of size n
transforms ngrams(text String, size Integer) List<String>
binary

/// Generate word bigrams (convenience for ngrams with size 2)
transforms bigrams(text String) List<String>
binary

// ── Normalization ──────────────────────────────────────────────

/// Normalize text: lowercase, fold Unicode to ASCII, strip accents
transforms normalize(text String) String
binary

/// Transliterate Unicode to closest ASCII equivalent
transforms transliterate(text String) String
binary

// ── Stopwords ──────────────────────────────────────────────────

/// Get the default English stopword list
reads stopwords() List<String>
binary

/// Remove stopwords from a list of words
transforms without_stopwords(input List<String>) List<String>
binary

// ── Frequency analysis ─────────────────────────────────────────

/// Count word frequencies in text
reads frequency(text String) Table<String, Integer>
binary

/// Extract top-N keywords by term frequency
reads keywords(text String, count Integer) List<String>
binary
```

---

## Implementation Plan

### Phase 1: C Runtime — `prove_language.h`

**File:** `prove-py/src/prove/runtime/prove_language.h`

```c
#ifndef PROVE_LANGUAGE_H
#define PROVE_LANGUAGE_H

#include "prove_core.h"
#include "prove_string.h"
#include "prove_list.h"
#include "prove_table.h"

// ── Token type ─────────────────────────────────────────────────
typedef enum {
    PROVE_TOKEN_WORD = 0,
    PROVE_TOKEN_PUNCTUATION = 1,
    PROVE_TOKEN_WHITESPACE = 2,
    PROVE_TOKEN_NUMBER = 3,
} Prove_TokenKind;

typedef struct {
    Prove_String *text;
    int64_t start;
    int64_t end;
    Prove_TokenKind kind;
} Prove_Language_Token;

// ── Tokenization ───────────────────────────────────────────────
Prove_List *prove_language_words(Prove_String *text);
Prove_List *prove_language_sentences(Prove_String *text);
Prove_List *prove_language_tokens(Prove_String *text);

// ── Stemming ───────────────────────────────────────────────────
Prove_String *prove_language_stem(Prove_String *word);
Prove_String *prove_language_root(Prove_String *word);

// ── Similarity ─────────────────────────────────────────────────
int64_t prove_language_distance(Prove_String *a, Prove_String *b);
double prove_language_similarity(Prove_String *a, Prove_String *b);
Prove_String *prove_language_soundex(Prove_String *word);
Prove_String *prove_language_metaphone(Prove_String *word);

// ── N-grams ────────────────────────────────────────────────────
Prove_List *prove_language_ngrams(Prove_String *text, int64_t size);
Prove_List *prove_language_bigrams(Prove_String *text);

// ── Normalization ──────────────────────────────────────────────
Prove_String *prove_language_normalize(Prove_String *text);
Prove_String *prove_language_transliterate(Prove_String *text);

// ── Stopwords ──────────────────────────────────────────────────
Prove_List *prove_language_stopwords(void);
Prove_List *prove_language_without_stopwords(Prove_List *words);

// ── Frequency ──────────────────────────────────────────────────
Prove_Table *prove_language_frequency(Prove_String *text);
Prove_List *prove_language_keywords(Prove_String *text, int64_t count);

#endif
```

### Phase 2: C Runtime — `prove_language.c`

**File:** `prove-py/src/prove/runtime/prove_language.c`

Implementation notes for each group:

1. **Tokenizer** — State-machine UTF-8 walker.  Classify each byte/codepoint
   as alphabetic / digit / punctuation / whitespace using Unicode category
   lookup.  Emit `Prove_Language_Token` structs with start/end byte offsets.
   `words()` filters to `PROVE_TOKEN_WORD` and `PROVE_TOKEN_NUMBER` only,
   returning `List<String>`.  `tokens()` returns all tokens as a
   `List<Token>` (the Token algebraic type maps to the C struct).

2. **Sentence splitter** — Heuristic: split on `.!?` followed by whitespace +
   uppercase or end-of-string.  Handle abbreviations (`Mr.`, `Dr.`, `U.S.`,
   `etc.`) via a small static `const char *[]` exception list (~30 entries).
   Returns `Prove_List *` of `Prove_String *`.

3. **Porter stemmer** — Direct C port of the classic Martin Porter algorithm.
   Five steps (1a, 1b, 1c, 2, 3, 4, 5a, 5b) operating on a mutable char
   buffer.  ~200 LOC.  Operates on ASCII lowercase; for Unicode input, the
   caller should `normalize()` first.  Reference:
   https://tartarus.org/martin/PorterStemmer/

4. **Root** — Simplified suffix strip.  Ordered rules (first match wins):
   `-ation`/`-tion` → strip, `-ment`/`-ments` → strip, `-ness` → strip,
   `-ing` → strip (keep if root < 3), `-ies` → `y`, `-es` → strip (if root
   ends in s/x/z/sh/ch), `-ed` → strip (keep if root < 3), `-s` → strip
   (not `-ss`).  This is the same logic as `normalize_noun()` in the Python
   compiler's `_nl_intent.py`, ported to C.  ~60 LOC.

5. **Levenshtein** — Standard DP with single-row optimization.  Allocate a
   `int64_t` buffer of `min(len_a, len_b) + 1` on the stack (or heap for
   very long strings).  O(n*m) time, O(min(n,m)) space.

6. **Similarity** — `1.0 - ((double)distance / (double)max(len_a, len_b))`.
   Returns 1.0 for identical strings, 0.0 for completely different.

7. **Soundex** — Classic 4-character American Soundex.  Lookup table mapping
   each letter to its Soundex digit (BFPV→1, CGJKQSXZ→2, DT→3, L→4, MN→5,
   R→6, AEIOUHWY→0).  Pad with zeros to length 4.  ~40 LOC.

8. **Double Metaphone** — Lawrence Philips algorithm.  Produces primary and
   secondary phonetic codes.  Large switch/case on letter pairs.  ~400 LOC.
   Reference: https://en.wikipedia.org/wiki/Metaphone#Double_Metaphone
   For simplicity, `metaphone()` returns only the primary code as a String.

9. **N-grams** — Always word-level.  Tokenize into words using the internal
   tokenizer, then slide a window of size `n` across the word list.  Each
   n-gram is the words joined by space.  `bigrams()` calls `ngrams(text, 2)`.
   Returns `Prove_List *` of `Prove_String *`.

10. **Normalize** — Walk UTF-8 byte sequence.  For each codepoint:
    (a) Look up in a static Unicode folding table (lowercase mapping),
    (b) If codepoint is a combining mark (Unicode category Mn), skip it,
    (c) If codepoint maps to an ASCII equivalent via the transliteration
    table, emit the ASCII byte.
    The folding table covers Latin Extended (À-ÿ), Greek, Cyrillic — ~8 KB
    static `const` array.  For codepoints outside the table, pass through
    unchanged.

11. **Transliterate** — Subset of normalize: only the accent-to-ASCII mapping
    without case folding.  à→a, ñ→n, ü→u, ø→o, etc.  ~200 entries in a
    sorted lookup table, searched via binary search.

12. **Stopwords** — Static `const char * const STOPWORDS[]` array of ~175
    English stopwords (the, a, an, is, are, was, were, ...).  At first call,
    build a `Prove_Table` (hash set) for O(1) lookup.  `without_stopwords()`
    iterates the input list, checks each word against the hash set, returns a
    new list with non-stopwords.

13. **Frequency** — Tokenize text into words using the internal tokenizer.
    For each word, look up in a `Prove_Table<String, Integer>`.  If present,
    increment; if not, insert with count 1.  `keywords()` copies the table
    entries into an array, sorts by count descending, returns the first
    `count` keys as a `Prove_List *`.

### Phase 3: Compiler Integration

**3a. Module declaration — `prove-py/src/prove/stdlib/language.prv`**

The `.prv` file from the API Design section above.  Place in the `stdlib/`
directory alongside `text.prv`, `pattern.prv`, etc.

**3b. Loader registration — `prove-py/src/prove/stdlib_loader.py`**

Add a `_register_module()` call:

```python
_register_module(
    "language",
    display="Language",
    prv_file="language.prv",
    c_map={
        ("transforms", "words"):              "prove_language_words",
        ("transforms", "sentences"):          "prove_language_sentences",
        ("transforms", "tokens"):             "prove_language_tokens",
        ("transforms", "stem"):               "prove_language_stem",
        ("transforms", "root"):               "prove_language_root",
        ("reads", "distance"):                "prove_language_distance",
        ("reads", "similarity"):              "prove_language_similarity",
        ("transforms", "soundex"):            "prove_language_soundex",
        ("transforms", "metaphone"):          "prove_language_metaphone",
        ("transforms", "ngrams"):             "prove_language_ngrams",
        ("transforms", "bigrams"):            "prove_language_bigrams",
        ("transforms", "normalize"):          "prove_language_normalize",
        ("transforms", "transliterate"):      "prove_language_transliterate",
        ("reads", "stopwords"):               "prove_language_stopwords",
        ("transforms", "without_stopwords"):  "prove_language_without_stopwords",
        ("reads", "frequency"):               "prove_language_frequency",
        ("reads", "keywords"):                "prove_language_keywords",
    },
)
```

**3c. Runtime metadata — `prove-py/src/prove/c_runtime.py`**

Add to `STDLIB_RUNTIME_LIBS`:
```python
"language": {"prove_language"},
```

The Language module depends only on core runtime types (`prove_string`,
`prove_list`, `prove_table`, `prove_core`) which are already linked for any
program that uses strings, lists, or tables.  The module does NOT depend on
`prove_pattern` — if sentence splitting needs regex, inline a minimal matcher
rather than pulling in the POSIX regex dependency.

Add each C function to `_RUNTIME_FUNCTIONS` with its signature.  Example
entries:

```python
"prove_language_words": {
    "params": [("text", "Prove_String *")],
    "return": "Prove_List *",
    "nullable": False,
},
"prove_language_distance": {
    "params": [("a", "Prove_String *"), ("b", "Prove_String *")],
    "return": "int64_t",
    "nullable": False,
},
"prove_language_similarity": {
    "params": [("a", "Prove_String *"), ("b", "Prove_String *")],
    "return": "double",
    "nullable": False,
},
# ... one entry per function
```

### Phase 4: Tests

**4a. C runtime unit tests — `prove-py/tests/test_language_runtime_c.py`**

Uses `compile_and_run()` from `tests/runtime_helpers.py`.  This helper
compiles a C source string together with the runtime `.c` files, runs the
resulting binary, and captures stdout.  Tests use the `needs_cc` fixture
(skips if `gcc`/`clang` not available) and `runtime_dir` fixture (points to
`src/prove/runtime/`).

Test classes and cases:

```python
class TestLanguageWords:
    def test_basic_sentence(self):
        # "Hello world" → ["Hello", "world"]
    def test_punctuation_stripped(self):
        # "Hello, world!" → ["Hello", "world"]
    def test_empty_string(self):
        # "" → []
    def test_unicode_words(self):
        # "café naïve" → ["café", "naïve"]

class TestLanguageSentences:
    def test_two_sentences(self):
        # "Hello. World." → ["Hello.", "World."]
    def test_abbreviation(self):
        # "Mr. Smith went home." → ["Mr. Smith went home."]
    def test_exclamation_question(self):
        # "Really? Yes!" → ["Really?", "Yes!"]

class TestLanguageStem:
    def test_known_pairs(self):
        # "running" → "run", "flies" → "fli", "caresses" → "caress"
    def test_short_word(self):
        # "is" → "is" (too short to stem)

class TestLanguageRoot:
    def test_suffix_strip(self):
        # "validation" → "valid", "processing" → "process"

class TestLanguageDistance:
    def test_identical(self):
        # distance("abc", "abc") == 0
    def test_known_distance(self):
        # distance("kitten", "sitting") == 3
    def test_empty_strings(self):
        # distance("", "abc") == 3

class TestLanguageSimilarity:
    def test_identical(self):
        # similarity("abc", "abc") == 1.0
    def test_completely_different(self):
        # similarity("abc", "xyz") == 0.0

class TestLanguageSoundex:
    def test_reference_values(self):
        # "Robert" → "R163", "Rupert" → "R163", "Ashcraft" → "A261"

class TestLanguageMetaphone:
    def test_reference_values(self):
        # "Smith" → "SM0", "Schmidt" → "XMT"

class TestLanguageNgrams:
    def test_bigrams(self):
        # "the quick brown" → ["the quick", "quick brown"]
    def test_trigrams(self):
        # "a b c d" → ["a b c", "b c d"]
    def test_n_greater_than_words(self):
        # "hello" with n=3 → []

class TestLanguageNormalize:
    def test_accents_stripped(self):
        # "café" → "cafe"
    def test_uppercase_folded(self):
        # "HELLO" → "hello"

class TestLanguageStopwords:
    def test_returns_list(self):
        # stopwords() returns non-empty list
    def test_filter(self):
        # without_stopwords(["the", "cat", "is"]) → ["cat"]

class TestLanguageFrequency:
    def test_word_counts(self):
        # "the cat and the dog" → {"the": 2, "cat": 1, "and": 1, "dog": 1}

class TestLanguageKeywords:
    def test_top_n(self):
        # "foo foo foo bar bar baz" with count=2 → ["foo", "bar"]
```

**4b. E2e tests — `tests/e2e/language/`**

Each is a `.prv` file that imports Language, calls functions, and prints
results.  `test_e2e.py` compiles them and checks stdout.

- `tokenize_basic.prv` — `Language.words("hello world")` → prints each word
- `stem_words.prv` — `Language.stem("running")` → prints "run"
- `similarity.prv` — `Language.distance("kitten", "sitting")` → prints "3"
- `frequency.prv` — `Language.frequency("a a b")` → prints counts

### Phase 5: Documentation

1. **`docs/stdlib/language.md`** — Full function reference with examples for
   each function.  Follow the format of existing stdlib docs.
2. **`docs/stdlib/index.md`** — Add Language to the module list table.

---

## Relation to Existing Modules

| Module | Domain | Overlap with Language |
|--------|--------|---------------------|
| **Text** | String manipulation (split, join, trim, replace, StringBuilder) | `Text.split` splits by separator; `Language.words` splits by word boundaries.  Different intent. |
| **Pattern** | POSIX regex matching (test, search, find_all, replace) | Pattern uses regex; Language uses linguistic rules.  Language does NOT depend on Pattern. |
| **Character** | Single-character queries (is_digit, is_alpha, to_upper) | Language's tokenizer classifies characters internally but doesn't expose per-character API. |
| **Parse** | Structured format parsing (JSON, TOML, CSV, URL) | No overlap.  Parse handles structured formats; Language handles natural language. |

---

## Dependencies

- **No external C libraries.**  Everything is self-contained in `prove_language.c`.
- **Unicode tables:** Embed a minimal subset (~Latin Extended, Greek, Cyrillic)
  as a static C array.  Full ICU is overkill.  The table maps codepoints to
  their lowercase ASCII equivalent (or pass-through).  ~8 KB compiled.
- **Core runtime types:** Uses `Prove_String`, `Prove_List`, `Prove_Table`
  from the existing runtime.  These are already linked for any program that
  uses strings/lists/tables.
- **No dependency on `prove_pattern.c`** — avoid pulling in POSIX regex.
  Sentence splitting uses custom heuristics, not regex.

## Size Estimate

| Component | Approx LOC (C) |
|-----------|----------------|
| Tokenizer + sentence splitter | 300 |
| Porter stemmer | 200 |
| Root (suffix strip) | 60 |
| Levenshtein + similarity | 80 |
| Soundex + Double Metaphone | 450 |
| N-grams | 80 |
| Normalize + transliterate + Unicode tables | 400 |
| Stopwords (data + filter) | 200 |
| Frequency + keywords | 100 |
| Header file | 60 |
| **Total** | **~1,930** |

Plus ~200 LOC for `language.prv` + ~50 LOC loader registration + ~80 LOC
runtime metadata entries.

---

## Future Extensions

If statistical NLP is ever needed, the path forward is:
- Add a `Language.model` channel: load a compact binary model from disk via IO verb
- Inference functions (POS tag, NER, etc.) operate on loaded model
- Models distributed separately from the compiler (not baked into runtime)
- This keeps the base module zero-dependency while allowing opt-in ML
