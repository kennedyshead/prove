"""NLP backend for intent analysis — spaCy/NLTK with fallback.

Provides improved lemmatization, POS tagging, synonym lookup, and
semantic similarity when spaCy and/or NLTK are installed.  Falls
back to the hand-rolled logic in ``_nl_intent`` when they are not.

**Never auto-downloads** models or data.  Users run ``prove setup-nlp``
to install prerequisites.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from prove._body_gen import StdlibMatch

# ── Lazy-loaded globals ──────────────────────────────────────────

_spacy_checked: bool = False
_spacy_available: bool = False
_nlp_model: object | None = None  # spacy.Language when loaded

_wordnet_checked: bool = False
_wordnet_available: bool = False


def _ensure_spacy() -> bool:
    """Lazy-check and load spaCy + en_core_web_sm.  Returns True if available."""
    global _spacy_checked, _spacy_available, _nlp_model
    if _spacy_checked:
        return _spacy_available
    _spacy_checked = True
    try:
        import spacy  # type: ignore[import-untyped]

        _nlp_model = spacy.load("en_core_web_sm")
        _spacy_available = True
    except Exception:
        _spacy_available = False
        _nlp_model = None
    return _spacy_available


def _ensure_wordnet() -> bool:
    """Lazy-check whether NLTK WordNet data is present.  Returns True if usable.

    Does NOT download anything — ``prove setup-nlp`` handles that.
    """
    global _wordnet_checked, _wordnet_available
    if _wordnet_checked:
        return _wordnet_available
    _wordnet_checked = True
    try:
        from nltk.corpus import wordnet  # type: ignore[import-untyped]

        # Probe that data is actually downloaded
        wordnet.synsets("test")
        _wordnet_available = True
    except Exception:
        _wordnet_available = False
    return _wordnet_available


def has_nlp_backend() -> bool:
    """Return True if spaCy or NLTK WordNet is available."""
    return _ensure_spacy() or _ensure_wordnet()


def has_spacy() -> bool:
    """Return True if spaCy with en_core_web_sm is available."""
    return _ensure_spacy()


def has_wordnet() -> bool:
    """Return True if NLTK WordNet data is available."""
    return _ensure_wordnet()


# ── Lemmatization ────────────────────────────────────────────────


def lemmatize(word: str) -> str:
    """Return the lemma (root form) of *word*.

    Uses spaCy lemmatizer when available, otherwise falls back to
    ``_nl_intent.normalize_noun``.
    """
    if _ensure_spacy():
        assert _nlp_model is not None
        doc = _nlp_model(word.lower())  # type: ignore[operator]
        if doc and doc[0].lemma_:
            return doc[0].lemma_
    # Fallback — use _fallback variant to avoid recursion
    from prove._nl_intent import _normalize_noun_fallback

    return _normalize_noun_fallback(word)


# ── Part-of-speech extraction ────────────────────────────────────


@dataclass
class ExtractedParts:
    """Nouns and verbs extracted from a prose string."""

    nouns: list[str] = field(default_factory=list)
    verbs: list[str] = field(default_factory=list)


def extract_parts(text: str) -> ExtractedParts:
    """Separate nouns and verbs from *text* using POS tagging.

    Falls back to ``_nl_intent.extract_nouns`` / ``implied_verbs``.
    """
    if _ensure_spacy():
        assert _nlp_model is not None
        doc = _nlp_model(text)  # type: ignore[operator]
        nouns: list[str] = []
        verbs: list[str] = []
        seen_nouns: set[str] = set()
        seen_verbs: set[str] = set()
        for token in doc:
            lemma = token.lemma_.lower()
            if token.pos_ in ("NOUN", "PROPN") and lemma not in seen_nouns:
                seen_nouns.add(lemma)
                nouns.append(lemma)
            elif token.pos_ == "VERB" and lemma not in seen_verbs:
                seen_verbs.add(lemma)
                verbs.append(lemma)
        return ExtractedParts(nouns=nouns, verbs=verbs)

    # Fallback — use _fallback variants to avoid recursion
    from prove._nl_intent import _extract_nouns_fallback, _implied_verbs_fallback

    return ExtractedParts(
        nouns=_extract_nouns_fallback(text),
        verbs=sorted(_implied_verbs_fallback(text)),
    )


# ── Synonym lookup ───────────────────────────────────────────────


def synonyms(word: str, pos: str = "v") -> set[str]:
    """Return synonyms of *word* via WordNet.

    *pos* is ``"v"`` for verbs, ``"n"`` for nouns (WordNet POS codes).
    Falls back to the synonym cache PDAT, then to ``VERB_SYNONYMS``.
    """
    if _ensure_wordnet():
        from nltk.corpus import wordnet  # type: ignore[import-untyped]

        result: set[str] = set()
        for synset in wordnet.synsets(word, pos=pos):
            for lemma in synset.lemmas():
                result.add(lemma.name().replace("_", " ").lower())
        return result

    # Try pre-computed synonym cache (richer than hardcoded table)
    from prove.nlp_store import load_synonym_cache

    cache = load_synonym_cache()
    if word.lower() in cache:
        return set(cache[word.lower()])

    # Fallback: use the PDAT-backed synonym groups
    from prove.nlp_store import load_verb_groups

    if pos == "v":
        groups = load_verb_groups()
        for canonical, syns in groups.items():
            if word.lower() in syns or word.lower() == canonical:
                return set(syns)
    return set()


# ── Text similarity ──────────────────────────────────────────────


def text_similarity(a: str, b: str) -> float:
    """Return 0.0–1.0 similarity between two text strings.

    Uses spaCy word vectors when available (and the model has vectors),
    otherwise Jaccard index on normalized word sets.
    """
    if _ensure_spacy():
        assert _nlp_model is not None
        doc_a = _nlp_model(a)  # type: ignore[operator]
        doc_b = _nlp_model(b)  # type: ignore[operator]
        # Only use spaCy similarity when model has word vectors and
        # both docs are non-empty — en_core_web_sm has no vectors.
        has_vectors = getattr(_nlp_model.vocab, "vectors_length", 0) > 0  # type: ignore[union-attr]
        if has_vectors and len(doc_a) > 0 and len(doc_b) > 0:
            sim = doc_a.similarity(doc_b)  # type: ignore[union-attr]
            return max(0.0, min(1.0, float(sim)))

    # Fallback: Jaccard on normalized words — use _fallback to avoid recursion
    from prove._nl_intent import _normalize_noun_fallback

    words_a = {_normalize_noun_fallback(w) for w in re.findall(r"[a-z]+", a.lower()) if len(w) >= 3}
    words_b = {_normalize_noun_fallback(w) for w in re.findall(r"[a-z]+", b.lower()) if len(w) >= 3}
    if not words_a or not words_b:
        return 0.0
    intersection = words_a & words_b
    union = words_a | words_b
    return len(intersection) / len(union)


# ── Intent phrase parsing ────────────────────────────────────────


@dataclass
class ParsedPhrase:
    """Structured parse of an intent phrase."""

    action: str | None = None
    object: str | None = None
    modifiers: list[str] = field(default_factory=list)


def parse_intent_phrase(text: str) -> ParsedPhrase:
    """Parse a short intent phrase into action, object, and modifiers.

    Uses spaCy dependency parse when available, otherwise regex fallback.
    """
    if _ensure_spacy():
        assert _nlp_model is not None
        doc = _nlp_model(text)  # type: ignore[operator]
        action: str | None = None
        obj: str | None = None
        modifiers: list[str] = []
        for token in doc:
            if token.pos_ == "VERB" and action is None:
                action = token.lemma_.lower()
            elif token.dep_ in ("dobj", "pobj", "attr") and obj is None:
                obj = token.lemma_.lower()
            elif token.pos_ in ("ADJ", "ADV"):
                modifiers.append(token.lemma_.lower())
        # If no verb found via dep parse, fall through to check first token
        if action is None and doc and doc[0].pos_ == "VERB":
            action = doc[0].lemma_.lower()
        return ParsedPhrase(action=action, object=obj, modifiers=modifiers)

    # Fallback: simple regex-based parsing
    words = re.findall(r"[a-zA-Z]+", text.lower())
    if not words:
        return ParsedPhrase()

    from prove._nl_intent import _SYNONYM_TO_VERB

    action = None
    obj = None
    modifiers = []
    for i, word in enumerate(words):
        if action is None and word in _SYNONYM_TO_VERB:
            action = word
        elif action is not None and obj is None and len(word) >= 3:
            obj = word
        elif action is not None and obj is not None:
            modifiers.append(word)

    return ParsedPhrase(action=action, object=obj, modifiers=modifiers)


# ── Stdlib function matching ─────────────────────────────────────


def match_stdlib_function(
    query: str,
    verb: str | None = None,
    stdlib_index: dict | None = None,
) -> list[StdlibMatch]:
    """Find stdlib functions matching a natural language *query*.

    Uses semantic similarity (spaCy vectors) to improve ranking when
    available.  Falls back to ``_body_gen.find_stdlib_matches``.

    Returns ``StdlibMatch`` objects (same type as ``_body_gen``).
    """
    from prove._body_gen import StdlibMatch as _StdlibMatch
    from prove._body_gen import _build_stdlib_index, find_stdlib_matches
    from prove._nl_intent import extract_nouns, implied_verbs

    if stdlib_index is None:
        stdlib_index = _build_stdlib_index()

    # Determine verb from query if not provided
    if verb is None:
        verbs = implied_verbs(query)
        verb = next(iter(sorted(verbs)), None)

    # Extract nouns from query
    nouns = extract_nouns(query)

    if verb is None:
        # Without a verb we can't match meaningfully
        return []

    # Get base matches from existing logic
    matches = find_stdlib_matches(verb, nouns, stdlib_index=stdlib_index)

    # Enhance scoring with semantic similarity when spaCy has word vectors
    has_vectors = (
        _ensure_spacy()
        and _nlp_model is not None
        and getattr(_nlp_model.vocab, "vectors_length", 0) > 0  # type: ignore[union-attr]
    )
    if has_vectors and matches:
        assert _nlp_model is not None
        query_doc = _nlp_model(query)  # type: ignore[operator]
        enhanced: list[_StdlibMatch] = []
        for m in matches:
            # Build a description from the function
            desc = f"{m.function.verb} {m.function.name}"
            if m.function.doc_comment:
                desc = m.function.doc_comment
            fn_doc = _nlp_model(desc)  # type: ignore[operator]
            sim = query_doc.similarity(fn_doc)  # type: ignore[union-attr]
            # Blend original score with similarity
            blended = (m.score * 0.6) + (max(0.0, float(sim)) * 0.4)
            enhanced.append(_StdlibMatch(
                module=m.module,
                function=m.function,
                overlap=m.overlap,
                score=round(blended, 3),
            ))
        return sorted(enhanced, key=lambda m: -m.score)

    return matches


# ── Reset (for testing) ──────────────────────────────────────────


def _reset() -> None:
    """Reset all lazy-loaded state.  For testing only."""
    global _spacy_checked, _spacy_available, _nlp_model
    global _wordnet_checked, _wordnet_available
    _spacy_checked = False
    _spacy_available = False
    _nlp_model = None
    _wordnet_checked = False
    _wordnet_available = False
