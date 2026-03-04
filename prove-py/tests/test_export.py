"""Tests for the prove export tool."""

from __future__ import annotations

import pytest

from prove.export import (
    _chroma_regex_line,
    _pygments_verbs,
    _ts_grammar_literals,
    _ts_grammar_verbs,
    _ts_highlights_builtin_types,
    _ts_highlights_contract,
    _ts_highlights_keywords,
    _ts_highlights_verbs,
    read_canonical_lists,
    replace_sentinel_section,
)


# ── Canonical lists ────────────────────────────────────────────────


@pytest.fixture
def lists():
    return read_canonical_lists()


@pytest.fixture
def grammar_lits():
    from pathlib import Path

    grammar = Path(__file__).resolve().parent.parent.parent / "tree-sitter-prove" / "grammar.js"
    if grammar.exists():
        return _ts_grammar_literals(grammar)
    # Fallback: all verbs + core grammar keywords
    return frozenset(
        {
            "transforms",
            "inputs",
            "outputs",
            "validates",
            "reads",
            "creates",
            "matches",
            "types",
            "module",
            "type",
            "is",
            "as",
            "from",
            "where",
            "match",
            "comptime",
            "valid",
            "main",
            "binary",
            "ensures",
            "requires",
            "explain",
            "terminates",
            "trusted",
            "intent",
            "narrative",
            "why_not",
            "chosen",
            "near_miss",
            "know",
            "assume",
            "believe",
            "temporal",
            "satisfies",
            "invariant_network",
        }
    )


def test_canonical_lists_complete(lists):
    """All expected categories are present and non-empty."""
    expected = {
        "verbs",
        "keywords",
        "contract_keywords",
        "ai_keywords",
        "builtin_types",
        "generic_types",
        "builtin_functions",
        "literals",
    }
    assert set(lists.keys()) == expected
    for key in expected:
        assert len(lists[key]) > 0, f"{key} is empty"


def test_no_stale_proof_keyword(lists):
    """'proof' does not appear in any canonical list."""
    for key, items in lists.items():
        assert "proof" not in items, f"'proof' found in {key}"


def test_no_stale_saves_keyword(lists):
    """'saves' does not appear in any canonical list."""
    for key, items in lists.items():
        assert "saves" not in items, f"'saves' found in {key}"


def test_explain_present(lists):
    """'explain' appears in contract keywords."""
    assert "explain" in lists["contract_keywords"]


def test_matches_present(lists):
    """'matches' appears in verb list."""
    assert "matches" in lists["verbs"]


def test_verbs_complete(lists):
    """All 7 verbs are present."""
    expected = {
        "transforms",
        "inputs",
        "outputs",
        "validates",
        "reads",
        "creates",
        "matches",
    }
    assert set(lists["verbs"]) == expected


def test_builtin_types_include_primitives(lists):
    """Primitive types are in builtin_types."""
    for t in ["Integer", "String", "Boolean", "Decimal", "Float", "Character", "Byte"]:
        assert t in lists["builtin_types"], f"{t} missing from builtin_types"


def test_generic_types_present(lists):
    """Generic types like List, Option, Result are present."""
    for t in ["List", "Option", "Result", "Error", "Table"]:
        assert t in lists["generic_types"], f"{t} missing from generic_types"


def test_literals(lists):
    """Boolean literals are present."""
    assert lists["literals"] == ["true", "false"]


def test_lists_are_sorted(lists):
    """All lists should be sorted for stable output."""
    for key, items in lists.items():
        if key == "literals":
            continue  # true/false has conventional order
        assert items == sorted(items), f"{key} is not sorted"


# ── Sentinel replacement ──────────────────────────────────────────


def test_sentinel_replacement():
    """replace_sentinel_section correctly replaces content between markers."""
    content = (
        "before\n// PROVE-EXPORT-BEGIN: verbs\nold content\n// PROVE-EXPORT-END: verbs\nafter\n"
    )
    result = replace_sentinel_section(content, "verbs", "new content\n")
    assert "new content" in result
    assert "old content" not in result
    assert "before\n" in result
    assert "after\n" in result
    assert "PROVE-EXPORT-BEGIN: verbs" in result
    assert "PROVE-EXPORT-END: verbs" in result


def test_sentinel_python_comments():
    """Sentinel works with # comment syntax."""
    content = (
        "before\n# PROVE-EXPORT-BEGIN: keywords\nold stuff\n# PROVE-EXPORT-END: keywords\nafter\n"
    )
    result = replace_sentinel_section(content, "keywords", "new stuff\n")
    assert "new stuff" in result
    assert "old stuff" not in result


def test_sentinel_scheme_comments():
    """Sentinel works with ; comment syntax."""
    content = (
        "before\n"
        "; PROVE-EXPORT-BEGIN: contract-keywords\n"
        "old\n"
        "; PROVE-EXPORT-END: contract-keywords\n"
        "after\n"
    )
    result = replace_sentinel_section(
        content,
        "contract-keywords",
        "new\n",
    )
    assert "new" in result
    assert result.count("old") == 0


def test_sentinel_missing_raises():
    """Missing sentinel pair raises clear error."""
    content = "no sentinels here"
    with pytest.raises(ValueError, match="not found"):
        replace_sentinel_section(content, "verbs", "replacement")


def test_sentinel_preserves_surrounding():
    """Replacement preserves all content outside sentinel markers."""
    content = (
        "line1\nline2\n; PROVE-EXPORT-BEGIN: test\nold\n; PROVE-EXPORT-END: test\nline3\nline4\n"
    )
    result = replace_sentinel_section(content, "test", "new\n")
    assert result.startswith("line1\nline2\n")
    assert result.endswith("line3\nline4\n")


# ── Generator output validation ──────────────────────────────────


def test_treesitter_verbs_output(lists, grammar_lits):
    """Generated tree-sitter highlights verb content contains expected keywords."""
    output = _ts_highlights_verbs(lists, grammar_lits)
    assert '"transforms"' in output
    assert '"matches"' in output
    assert '"types"' in output  # extra verb-like keyword
    assert "@keyword.function" in output


def test_treesitter_contract_output(lists, grammar_lits):
    """Generated tree-sitter contract keywords are correct."""
    output = _ts_highlights_contract(lists, grammar_lits)
    assert '"ensures"' in output
    assert '"explain"' in output
    assert '"terminates"' in output
    assert '"proof"' not in output
    # trusted is handled separately
    assert '"trusted"' not in output
    assert '"when"' in output
    assert "@keyword.control" in output


def test_treesitter_keywords_no_phantom_literals(lists, grammar_lits):
    """Keywords not in grammar.js are excluded from highlights."""
    output = _ts_highlights_keywords(lists, grammar_lits)
    # These exist in the compiler but not as grammar literals
    # when and domain are not grammar literals
    assert '"when"' not in output
    assert '"domain"' not in output
    # These should be present (they are grammar literals)
    assert '"from"' in output
    assert '"type"' in output
    assert '"module"' in output
    assert '"foreign"' in output


def test_treesitter_builtin_types_output(lists):
    """Generated tree-sitter builtin types contain expected types."""
    output = _ts_highlights_builtin_types(lists)
    assert '"Integer"' in output
    assert '"String"' in output
    assert '"List"' in output
    assert '"Table"' in output
    assert "@type.builtin" in output


def test_treesitter_grammar_verbs_output(lists):
    """Generated tree-sitter grammar.js verb choice is correct."""
    output = _ts_grammar_verbs(lists)
    assert "'transforms'," in output
    assert "'matches'," in output
    assert "choice(" in output


def test_pygments_output_valid(lists):
    """Generated Pygments content contains expected keywords."""
    output = _pygments_verbs(lists)
    assert '"transforms"' in output
    assert '"matches"' in output
    assert "Keyword.Declaration" in output


def test_chroma_output_valid(lists):
    """Generated Chroma content contains expected keywords."""
    output = _chroma_regex_line(lists["verbs"], "KeywordDeclaration")
    assert "transforms" in output
    assert "matches" in output
    assert "chroma.KeywordDeclaration" in output
    assert "\\b(" in output
