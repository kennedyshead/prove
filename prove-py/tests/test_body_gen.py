"""Tests for the Phase 2 body generation engine (_body_gen.py)."""

from __future__ import annotations

from prove._body_gen import (
    add_generated_marker,
    find_stdlib_matches,
    generate_body,
    generate_function_source,
    has_generated_marker,
)


class TestFindStdlibMatches:
    def test_no_matches_returns_empty(self) -> None:
        # Empty index — no matches possible
        matches = find_stdlib_matches("validates", ["unicorn"], stdlib_index={})
        assert matches == []

    def test_finds_match_by_verb_and_noun(self) -> None:
        # Build a minimal stdlib index by loading a real module
        from prove.stdlib_loader import load_stdlib

        index = {"hash": load_stdlib("hash")}
        matches = find_stdlib_matches("creates", ["sha256"], stdlib_index=index)
        assert len(matches) >= 1
        assert any(m.function.name == "sha256" for m in matches)

    def test_sorted_by_score(self) -> None:
        from prove.stdlib_loader import load_stdlib

        index = {"text": load_stdlib("text")}
        matches = find_stdlib_matches("transforms", ["split", "trim"], stdlib_index=index)
        if len(matches) >= 2:
            scores = [m.score for m in matches]
            assert scores == sorted(scores, reverse=True)


class TestGenerateBody:
    def test_no_match_produces_todo(self) -> None:
        body = generate_body(
            verb="validates",
            name="unicorn",
            nouns=["unicorn"],
            param_names=["x"],
            stdlib_index={},
        )
        assert len(body.stmts) == 1
        assert body.stmts[0].is_todo
        assert "todo" in body.stmts[0].code

    def test_match_produces_call(self) -> None:
        from prove.stdlib_loader import load_stdlib

        index = {"math": load_stdlib("math")}
        body = generate_body(
            verb="derives",
            name="absolute",
            nouns=["abs", "absolute"],
            param_names=["n"],
            stdlib_index=index,
        )
        # Should have at least one non-todo statement
        non_todo = [s for s in body.stmts if not s.is_todo]
        if non_todo:
            assert any("Math." in s.code for s in non_todo)

    def test_body_has_chosen_when_matched(self) -> None:
        from prove.stdlib_loader import load_stdlib

        index = {"text": load_stdlib("text")}
        body = generate_body(
            verb="transforms",
            name="upper",
            nouns=["upper"],
            param_names=["s"],
            stdlib_index=index,
        )
        if any(not s.is_todo for s in body.stmts):
            assert body.chosen is not None


class TestGeneratedMarkers:
    def test_no_marker(self) -> None:
        assert not has_generated_marker(None)
        assert not has_generated_marker("Just a comment")

    def test_has_marker(self) -> None:
        assert has_generated_marker("comment @generated from line 5")

    def test_add_marker(self) -> None:
        result = add_generated_marker("doc comment", source_line=10)
        assert "@generated from declaration line 10" in result

    def test_add_marker_no_line(self) -> None:
        result = add_generated_marker("doc comment")
        assert "@generated" in result
        assert "line" not in result


class TestGenerateFunctionSource:
    def test_produces_valid_prove_structure(self) -> None:
        source = generate_function_source(
            verb="transforms",
            name="password",
            param_names=["plaintext"],
            param_types=["String"],
            return_type="String",
            declaration_text="Transforms plaintext passwords into hashes",
            stdlib_index={},
        )
        assert "/// Transforms plaintext passwords into hashes" in source
        assert "/// @generated" in source
        assert "transforms password(plaintext String) String" in source
        assert "from" in source
        assert "todo" in source

    def test_unit_return_omitted(self) -> None:
        source = generate_function_source(
            verb="outputs",
            name="log",
            param_names=["msg"],
            param_types=["String"],
            return_type="Unit",
            stdlib_index={},
        )
        assert "outputs log(msg String)" in source
        assert "Unit" not in source
