# Plan: Function Name Synonym Analysis

## Problem

Prove's prose coherence checks (W501, W502) and intent coverage matching
compare prose text against function names using exact or crude 4-character
prefix matching (`prose_overlaps()`). This produces false positives when:

- Narrative says "hashing passwords" but function is `hash_password`
- Narrative says "credentials" but param/function uses "credential"
- Explain block says "authentication" but body calls `authenticate`

The verb synonym map (VERB_SYNONYMS in `_nl_intent.py`) solved this for
verbs. Function names need equivalent treatment, but as an open set they
require a different strategy.

## Approach

Two composable layers, no external dependencies.

### Phase 1: Morphological Normalizer

Add `normalize_noun(word: str) -> str` to `_nl_intent.py`. Strips common
English suffixes to produce a comparison root:

```
"credentials"      -> "credential"
"hashing"          -> "hash"
"authentication"   -> "authenticat"
"sessions"         -> "session"
"validated"        -> "validat"
"passwords"        -> "password"
"entries"          -> "entry"
"processing"       -> "process"
```

Ordered suffix rules (applied first match):
1. `-ation` / `-tion` -> strip
2. `-ment` / `-ments` -> strip
3. `-ness` -> strip
4. `-ing` -> strip (but keep if root < 3 chars)
5. `-ies` -> `-y`
6. `-es` -> strip (if root ends in s/x/z/sh/ch)
7. `-ed` -> strip (but keep if root < 3 chars)
8. `-s` -> strip (but not `-ss`)

This is intentionally conservative — better to miss a normalization than
to produce a wrong root.

### Phase 2: Compound Name Decomposition

Split snake_case identifiers into word parts before comparison:

```python
def split_name(name: str) -> list[str]:
    """Split a snake_case name into lowercase word parts."""
    return [p for p in name.lower().split("_") if p]
```

`hash_password` -> `["hash", "password"]`
`session_token` -> `["session", "token"]`

### Integration Points

**`prose_overlaps()` in `_nl_intent.py`:**
Currently compares raw words with 4-char prefix heuristic. Replace with:
1. Split snake_case tokens into parts
2. Normalize both prose words and token parts
3. Compare normalized forms

```python
def prose_overlaps(prose: str, tokens: set[str]) -> bool:
    prose_words = {normalize_noun(w.lower())
                   for w in re.findall(r"[a-zA-Z_][a-zA-Z0-9_]*", prose)}
    token_roots: set[str] = set()
    for t in tokens:
        for part in split_name(t):
            token_roots.add(normalize_noun(part))
    return bool(prose_words & token_roots)
```

**`extract_nouns()` in `_nl_intent.py`:**
Return normalized forms so downstream consumers get consistent roots.

**W502 (explain/body coherence) in `_check_contracts.py`:**
Already calls `prose_overlaps()` — benefits automatically.

**`check_intent_coverage()` in `intent_generator.py`:**
When matching intent noun phrases to generated function names, normalize
both sides before comparison.

## Phase 3 (follow-up): Vocabulary-Aware Matching

The `.intent` vocabulary section declares domain terms:

```
Credential is a user identity paired with a secret
Session is a time-limited access token
```

Build a vocabulary synonym ring from these declarations:
- `"Credential"` <-> `"credential"` <-> `"credentials"`
- Description words become weak associations for scoring

This requires a `VocabularyIndex` that `prose_overlaps()` and
`check_intent_coverage()` can query. Deferred until phases 1+2 prove
their value.

## Files to Modify

| File | Change |
|------|--------|
| `src/prove/_nl_intent.py` | Add `normalize_noun()`, `split_name()`. Rewrite `prose_overlaps()`. |
| `src/prove/intent_generator.py` | Use `normalize_noun()` + `split_name()` in coverage matching. |
| `tests/test_nl_intent.py` | Tests for `normalize_noun()`, `split_name()`, updated `prose_overlaps()`. |

No changes needed to `_check_contracts.py` — it calls `prose_overlaps()`
which gets the improvement for free.

## Verification

1. `python -m pytest tests/test_nl_intent.py tests/test_checker_contracts.py -v`
2. `python -m pytest tests/ -v` (full suite)
3. `prove check proof/`
