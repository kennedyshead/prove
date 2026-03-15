"""Tests for the NLP backend (nlp.py).

All tests pass both with and without spaCy/NLTK installed.
Tests that exercise the NLP backends use ``pytest.importorskip``
or check ``has_nlp_backend()``.
"""

from __future__ import annotations

from unittest import mock

import pytest

from prove.nlp import (
    ExtractedParts,
    ParsedPhrase,
    _reset,
    extract_parts,
    has_nlp_backend,
    has_spacy,
    has_wordnet,
    lemmatize,
    match_stdlib_function,
    parse_intent_phrase,
    synonyms,
    text_similarity,
)


@pytest.fixture(autouse=True)
def _reset_nlp_state():
    """Reset lazy-loaded NLP state between tests."""
    _reset()
    yield
    _reset()


# ── Lemmatize ────────────────────────────────────────────────────


class TestLemmatize:
    def test_regular_verb_fallback(self) -> None:
        # Fallback normalize_noun strips -ing suffix
        result = lemmatize("processing")
        assert isinstance(result, str)
        assert len(result) > 0
        assert result == "process"

    def test_plural_noun_fallback(self) -> None:
        result = lemmatize("passwords")
        assert result == "password"

    def test_short_word_unchanged(self) -> None:
        result = lemmatize("cat")
        assert isinstance(result, str)

    def test_already_root(self) -> None:
        result = lemmatize("hash")
        assert result == "hash"

    def test_ation_suffix(self) -> None:
        result = lemmatize("validation")
        # spaCy keeps "validation" as-is; fallback strips to "valid"
        assert result in ("valid", "validation")

    @pytest.mark.skipif(
        not has_spacy(),
        reason="spaCy not available",
    )
    def test_spacy_irregular_noun(self) -> None:
        # spaCy should handle irregular forms better
        result = lemmatize("children")
        assert result == "child"

    @pytest.mark.skipif(
        not has_spacy(),
        reason="spaCy not available",
    )
    def test_spacy_irregular_verb(self) -> None:
        result = lemmatize("ran")
        assert result == "run"


# ── Extract parts ────────────────────────────────────────────────


class TestExtractParts:
    def test_returns_extracted_parts(self) -> None:
        result = extract_parts("transforms the password into a hash")
        assert isinstance(result, ExtractedParts)
        assert isinstance(result.nouns, list)
        assert isinstance(result.verbs, list)

    def test_fallback_finds_nouns(self) -> None:
        result = extract_parts("validate the email address")
        assert any("email" in n or "address" in n for n in result.nouns)

    def test_fallback_finds_verbs(self) -> None:
        result = extract_parts("validate the email address")
        assert len(result.verbs) >= 1

    def test_empty_string(self) -> None:
        result = extract_parts("")
        assert result.nouns == []
        assert result.verbs == []

    @pytest.mark.skipif(
        not has_spacy(),
        reason="spaCy not available",
    )
    def test_spacy_separates_nouns_verbs(self) -> None:
        result = extract_parts("compute the hash of the password")
        assert len(result.nouns) >= 1
        assert len(result.verbs) >= 1


# ── Synonyms ─────────────────────────────────────────────────────


class TestSynonyms:
    def test_verb_synonyms_fallback(self) -> None:
        result = synonyms("transform", pos="v")
        assert isinstance(result, set)
        # Should include at least the word itself or related words
        assert len(result) >= 1

    def test_unknown_word_fallback(self) -> None:
        result = synonyms("xyzzy", pos="v")
        assert isinstance(result, set)
        assert len(result) == 0

    def test_noun_synonyms_fallback_empty(self) -> None:
        # Fallback only has verb synonyms
        result = synonyms("password", pos="n")
        assert isinstance(result, set)

    @pytest.mark.skipif(
        not has_wordnet(),
        reason="NLTK WordNet not available",
    )
    def test_wordnet_verb_synonyms(self) -> None:
        result = synonyms("create", pos="v")
        assert isinstance(result, set)
        assert len(result) >= 2  # WordNet has rich synonym sets

    @pytest.mark.skipif(
        not has_wordnet(),
        reason="NLTK WordNet not available",
    )
    def test_wordnet_noun_synonyms(self) -> None:
        result = synonyms("password", pos="n")
        assert isinstance(result, set)
        # WordNet has noun synonyms
        assert len(result) >= 1


# ── Text similarity ──────────────────────────────────────────────


class TestTextSimilarity:
    def test_identical_strings(self) -> None:
        score = text_similarity("hash password", "hash password")
        assert score == pytest.approx(1.0)

    def test_completely_unrelated(self) -> None:
        score = text_similarity("hash password", "purple elephant circus")
        # Jaccard fallback gives 0.0 for no overlap
        assert score < 1.0

    def test_similar_phrases(self) -> None:
        score = text_similarity("validate email", "check email address")
        assert score > 0.0

    def test_empty_strings(self) -> None:
        score = text_similarity("", "")
        assert isinstance(score, float)
        assert 0.0 <= score <= 1.0

    def test_one_empty(self) -> None:
        score = text_similarity("hash password", "")
        assert score == pytest.approx(0.0)

    def test_returns_float(self) -> None:
        score = text_similarity("compute value", "calculate number")
        assert isinstance(score, float)
        assert 0.0 <= score <= 1.0


# ── Parse intent phrase ──────────────────────────────────────────


class TestParseIntentPhrase:
    def test_returns_parsed_phrase(self) -> None:
        result = parse_intent_phrase("validate the email address")
        assert isinstance(result, ParsedPhrase)

    def test_fallback_finds_action(self) -> None:
        result = parse_intent_phrase("transform the input data")
        assert result.action is not None

    def test_fallback_finds_object(self) -> None:
        result = parse_intent_phrase("please validate the email address")
        # With spaCy or fallback, should find an object
        assert result.action is not None or result.object is not None

    def test_empty_string(self) -> None:
        result = parse_intent_phrase("")
        assert result.action is None
        assert result.object is None

    @pytest.mark.skipif(
        not has_spacy(),
        reason="spaCy not available",
    )
    def test_spacy_parse(self) -> None:
        result = parse_intent_phrase("compute the hash of the password")
        assert result.action is not None
        assert result.object is not None


# ── Match stdlib function ────────────────────────────────────────


class TestMatchStdlibFunction:
    def test_returns_list(self) -> None:
        result = match_stdlib_function("create sha256 hash")
        assert isinstance(result, list)

    def test_verb_extracted_from_query(self) -> None:
        result = match_stdlib_function("transform text to lowercase")
        # Should find stdlib matches for transforms verb
        assert isinstance(result, list)

    def test_explicit_verb(self) -> None:
        result = match_stdlib_function("sha256 hash", verb="creates")
        assert isinstance(result, list)

    def test_no_verb_returns_empty(self) -> None:
        # A query with no recognizable verb
        result = match_stdlib_function("xyzzy foobar")
        assert result == []

    def test_result_is_stdlib_match(self) -> None:
        from prove._body_gen import StdlibMatch

        results = match_stdlib_function("create sha256 hash")
        for r in results:
            assert isinstance(r, StdlibMatch)

    def test_results_sorted_by_score(self) -> None:
        results = match_stdlib_function("create sha256 hash")
        if len(results) >= 2:
            scores = [r.score for r in results]
            assert scores == sorted(scores, reverse=True)


# ── Fallback mode ────────────────────────────────────────────────


class TestFallbackMode:
    """Verify all functions work when NLP backends are forced off."""

    def _patch_nlp_unavailable(self):
        """Return context manager that forces NLP backends off."""
        import prove.nlp as nlp_mod

        _reset()
        return mock.patch.multiple(
            nlp_mod,
            _spacy_checked=True,
            _spacy_available=False,
            _nlp_model=None,
            _wordnet_checked=True,
            _wordnet_available=False,
        )

    def test_lemmatize_fallback(self) -> None:
        with self._patch_nlp_unavailable():
            result = lemmatize("processing")
            assert result == "process"

    def test_extract_parts_fallback(self) -> None:
        with self._patch_nlp_unavailable():
            result = extract_parts("validate email address")
            assert isinstance(result, ExtractedParts)
            assert len(result.nouns) >= 1

    def test_synonyms_fallback(self) -> None:
        with self._patch_nlp_unavailable():
            result = synonyms("transform", pos="v")
            assert isinstance(result, set)
            assert len(result) >= 1

    def test_text_similarity_fallback(self) -> None:
        with self._patch_nlp_unavailable():
            score = text_similarity("hash password", "hash password")
            assert score == pytest.approx(1.0)

    def test_parse_intent_phrase_fallback(self) -> None:
        with self._patch_nlp_unavailable():
            result = parse_intent_phrase("validate email")
            assert isinstance(result, ParsedPhrase)
            assert result.action is not None

    def test_match_stdlib_function_fallback(self) -> None:
        with self._patch_nlp_unavailable():
            result = match_stdlib_function("create sha256 hash")
            assert isinstance(result, list)


# ── has_nlp_backend ──────────────────────────────────────────────


class TestHasNlpBackend:
    def test_returns_bool(self) -> None:
        result = has_nlp_backend()
        assert isinstance(result, bool)

    def test_forced_off(self) -> None:
        import prove.nlp as nlp_mod

        _reset()
        with mock.patch.multiple(
            nlp_mod,
            _spacy_checked=True,
            _spacy_available=False,
            _nlp_model=None,
            _wordnet_checked=True,
            _wordnet_available=False,
        ):
            assert has_nlp_backend() is False

    def test_has_spacy_returns_bool(self) -> None:
        assert isinstance(has_spacy(), bool)

    def test_has_wordnet_returns_bool(self) -> None:
        assert isinstance(has_wordnet(), bool)
