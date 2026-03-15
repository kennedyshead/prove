"""Tests for the PDAT-backed NLP data stores (nlp_store.py)."""

from __future__ import annotations

from pathlib import Path
from unittest import mock

import pytest

from prove.nlp_store import (
    _reset,
    build_semantic_features,
    build_similarity_matrix,
    build_stdlib_index,
    load_semantic_features,
    load_similarity_matrix,
    load_stdlib_index,
    load_synonym_cache,
    load_verb_groups,
    load_verb_synonyms,
)
from prove.store_binary import read_pdat, write_pdat


@pytest.fixture(autouse=True)
def _reset_store_state():
    """Reset cached store data between tests."""
    _reset()
    yield
    _reset()


# ── Verb synonym store ───────────────────────────────────────────


class TestLoadVerbSynonyms:
    def test_returns_dict(self) -> None:
        result = load_verb_synonyms()
        assert isinstance(result, dict)

    def test_all_canonical_verbs_present(self) -> None:
        result = load_verb_synonyms()
        expected_verbs = {
            "transforms", "validates", "reads", "creates", "matches",
            "outputs", "inputs", "listens", "detached", "attached", "streams",
        }
        actual_verbs = set(result.values())
        assert expected_verbs == actual_verbs

    def test_known_synonyms(self) -> None:
        result = load_verb_synonyms()
        assert result["convert"] == "transforms"
        assert result["check"] == "validates"
        assert result["fetch"] == "reads"
        assert result["build"] == "creates"
        assert result["compare"] == "matches"
        assert result["write"] == "outputs"
        assert result["receive"] == "inputs"
        assert result["monitor"] == "listens"
        assert result["spawn"] == "detached"
        assert result["await"] == "attached"
        assert result["poll"] == "streams"

    def test_caches_result(self) -> None:
        first = load_verb_synonyms()
        second = load_verb_synonyms()
        assert first is second

    def test_canonical_forms_map_to_self(self) -> None:
        result = load_verb_synonyms()
        for verb in ["transforms", "validates", "reads", "creates"]:
            assert result[verb] == verb


class TestLoadVerbGroups:
    def test_returns_dict(self) -> None:
        result = load_verb_groups()
        assert isinstance(result, dict)

    def test_all_verbs_have_synonyms(self) -> None:
        result = load_verb_groups()
        for verb, syns in result.items():
            assert len(syns) >= 2, f"{verb} should have at least 2 synonyms"

    def test_transforms_group(self) -> None:
        result = load_verb_groups()
        assert "transforms" in result
        syns = result["transforms"]
        assert "convert" in syns
        assert "compute" in syns


# ── Stdlib index store ───────────────────────────────────────────


class TestBuildStdlibIndex:
    def test_creates_dat_file(self, tmp_path) -> None:
        prove_dir = tmp_path / ".prove"
        prove_dir.mkdir()
        out = build_stdlib_index(tmp_path)
        assert out.exists()
        assert out.name == "stdlib_index.dat"

    def test_dat_readable(self, tmp_path) -> None:
        prove_dir = tmp_path / ".prove"
        prove_dir.mkdir()
        out = build_stdlib_index(tmp_path)
        data = read_pdat(out)
        assert data["columns"] == ["String", "String", "String"]
        assert len(data["variants"]) > 0

    def test_contains_known_functions(self, tmp_path) -> None:
        prove_dir = tmp_path / ".prove"
        prove_dir.mkdir()
        out = build_stdlib_index(tmp_path)
        data = read_pdat(out)
        keys = {v[0] for v in data["variants"]}
        # Known stdlib functions
        assert "hash.sha256" in keys or "hash.sha512" in keys
        assert "text.length" in keys or "text.split" in keys

    def test_creates_prove_dir_if_missing(self, tmp_path) -> None:
        out = build_stdlib_index(tmp_path)
        assert out.exists()
        assert (tmp_path / ".prove").is_dir()


class TestLoadStdlibIndex:
    def test_returns_word_index(self, tmp_path) -> None:
        build_stdlib_index(tmp_path)
        index = load_stdlib_index(tmp_path)
        assert isinstance(index, dict)
        assert len(index) > 0

    def test_word_lookup_returns_entries(self, tmp_path) -> None:
        build_stdlib_index(tmp_path)
        index = load_stdlib_index(tmp_path)
        # "sha256" should be indexed
        if "sha256" in index:
            entries = index["sha256"]
            assert len(entries) >= 1
            assert entries[0]["module"] == "hash"
            assert "name" in entries[0]
            assert "verb" in entries[0]
            assert "doc" in entries[0]

    def test_fallback_without_dat(self, tmp_path) -> None:
        # No .prove/stdlib_index.dat — should fall back to in-memory build
        index = load_stdlib_index(tmp_path)
        assert isinstance(index, dict)
        assert len(index) > 0


# ── Fallback behavior ────────────────────────────────────────────


class TestFallback:
    def test_verb_synonyms_fallback_when_dat_missing(self) -> None:
        import prove.nlp_store as store_mod

        _reset()
        # Monkeypatch _data_path to return a non-existent file
        with mock.patch.object(
            store_mod,
            "_data_path",
            return_value=Path("/nonexistent/verb_synonyms.dat"),
        ):
            result = load_verb_synonyms()
            assert isinstance(result, dict)
            assert result["convert"] == "transforms"

    def test_verb_groups_fallback(self) -> None:
        import prove.nlp_store as store_mod

        _reset()
        with mock.patch.object(
            store_mod,
            "_data_path",
            return_value=Path("/nonexistent/verb_synonyms.dat"),
        ):
            result = load_verb_groups()
            assert isinstance(result, dict)
            assert "transforms" in result


# ── Synonym cache store ─────────────────────────────────────────


class TestSynonymCache:
    def test_write_and_read_round_trip(self, tmp_path) -> None:
        """Write a synonym cache PDAT, then read it back."""
        dat = tmp_path / "synonym_cache.dat"
        variants = [
            ("transform", ["convert|change|alter|modify"]),
            ("validate", ["check|verify|ensure"]),
        ]
        write_pdat(dat, "SynonymCache", ["String"], variants)

        import prove.nlp_store as store_mod

        _reset()
        with mock.patch.object(store_mod, "_data_path", return_value=dat):
            result = load_synonym_cache()
            assert isinstance(result, dict)
            assert "transform" in result
            assert "convert" in result["transform"]
            assert "change" in result["transform"]
            assert "alter" in result["transform"]
            assert "modify" in result["transform"]
            assert "check" in result["validate"]

    def test_caches_result(self, tmp_path) -> None:
        dat = tmp_path / "synonym_cache.dat"
        write_pdat(dat, "SynonymCache", ["String"], [
            ("test", ["example|sample"]),
        ])

        import prove.nlp_store as store_mod

        _reset()
        with mock.patch.object(store_mod, "_data_path", return_value=dat):
            first = load_synonym_cache()
            second = load_synonym_cache()
            assert first is second

    def test_fallback_to_empty_dict(self) -> None:
        import prove.nlp_store as store_mod

        _reset()
        with mock.patch.object(
            store_mod,
            "_data_path",
            return_value=Path("/nonexistent/synonym_cache.dat"),
        ):
            result = load_synonym_cache()
            assert isinstance(result, dict)
            assert len(result) == 0

    def test_empty_synonym_list(self, tmp_path) -> None:
        dat = tmp_path / "synonym_cache.dat"
        write_pdat(dat, "SynonymCache", ["String"], [
            ("lonely", [""]),
        ])

        import prove.nlp_store as store_mod

        _reset()
        with mock.patch.object(store_mod, "_data_path", return_value=dat):
            result = load_synonym_cache()
            assert "lonely" in result
            assert result["lonely"] == []


# ── Similarity matrix store ─────────────────────────────────────


class TestSimilarityMatrix:
    def test_write_and_read_round_trip(self, tmp_path) -> None:
        """Write a similarity matrix PDAT, then read it back."""
        prove_dir = tmp_path / ".prove"
        prove_dir.mkdir()
        dat = prove_dir / "similarity_matrix.dat"
        variants = [
            ("text.length|text.split", ["0.423"]),
            ("math.add|math.subtract", ["0.891"]),
        ]
        write_pdat(dat, "SimilarityMatrix", ["String"], variants)

        _reset()
        result = load_similarity_matrix(tmp_path)
        assert isinstance(result, dict)
        assert "text.length" in result
        assert "text.split" in result["text.length"]
        assert abs(result["text.length"]["text.split"] - 0.423) < 0.001
        # Symmetric
        assert abs(result["text.split"]["text.length"] - 0.423) < 0.001

    def test_fallback_to_empty_dict(self, tmp_path) -> None:
        _reset()
        result = load_similarity_matrix(tmp_path)
        assert isinstance(result, dict)
        assert len(result) == 0

    def test_none_project_dir_returns_empty(self) -> None:
        _reset()
        result = load_similarity_matrix(None)
        assert isinstance(result, dict)
        assert len(result) == 0

    def test_build_creates_file(self, tmp_path) -> None:
        _reset()
        out = build_similarity_matrix(tmp_path)
        assert out.exists()
        assert out.name == "similarity_matrix.dat"
        data = read_pdat(out)
        assert data["columns"] == ["String"]

    def test_caches_result(self, tmp_path) -> None:
        prove_dir = tmp_path / ".prove"
        prove_dir.mkdir()
        dat = prove_dir / "similarity_matrix.dat"
        write_pdat(dat, "SimilarityMatrix", ["String"], [
            ("a.x|b.y", ["0.5"]),
        ])

        _reset()
        first = load_similarity_matrix(tmp_path)
        second = load_similarity_matrix(tmp_path)
        assert first is second


# ── Semantic features store ─────────────────────────────────────


class TestSemanticFeatures:
    def test_write_and_read_round_trip(self, tmp_path) -> None:
        """Write semantic features PDAT, then read it back."""
        prove_dir = tmp_path / ".prove"
        prove_dir.mkdir()
        dat = prove_dir / "semantic_features.dat"
        variants = [
            ("text.length", ["text", "reads", "length string character count"]),
            ("math.add", ["math", "transforms", "add number sum"]),
        ]
        write_pdat(dat, "SemanticFeatures", ["String", "String", "String"], variants)

        result = load_semantic_features(tmp_path)
        assert isinstance(result, dict)
        assert "text.length" in result
        entry = result["text.length"]
        assert entry["module"] == "text"
        assert entry["verb"] == "reads"
        assert "length" in entry["keywords"]

    def test_fallback_to_empty_dict(self, tmp_path) -> None:
        result = load_semantic_features(tmp_path)
        assert isinstance(result, dict)
        assert len(result) == 0

    def test_none_project_dir_returns_empty(self) -> None:
        result = load_semantic_features(None)
        assert isinstance(result, dict)
        assert len(result) == 0

    def test_build_creates_file(self, tmp_path) -> None:
        out = build_semantic_features(tmp_path)
        assert out.exists()
        assert out.name == "semantic_features.dat"
        data = read_pdat(out)
        assert data["columns"] == ["String", "String", "String"]
        assert len(data["variants"]) > 0

    def test_build_entries_have_keywords(self, tmp_path) -> None:
        build_semantic_features(tmp_path)
        result = load_semantic_features(tmp_path)
        # At least some entries should have keywords
        has_keywords = any(
            entry["keywords"].strip() for entry in result.values()
        )
        assert has_keywords
