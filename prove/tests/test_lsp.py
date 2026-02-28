"""Tests for the Prove LSP server."""

from __future__ import annotations

from lsprotocol import types as lsp

from prove.errors import Severity
from prove.lsp import (
    _SEVERITY_MAP,
    DocumentState,
    _analyze,
    _get_word_at,
    _types_display,
    span_to_range,
)
from prove.source import Span
from prove.symbols import FunctionSignature


class TestSpanConversion:
    def test_span_to_range_basic(self):
        span = Span("test.prv", 1, 1, 1, 5)
        r = span_to_range(span)
        assert r.start.line == 0
        assert r.start.character == 0
        assert r.end.line == 0
        assert r.end.character == 5

    def test_span_to_range_multiline(self):
        span = Span("test.prv", 5, 3, 7, 10)
        r = span_to_range(span)
        assert r.start.line == 4
        assert r.start.character == 2
        assert r.end.line == 6
        assert r.end.character == 10

    def test_span_to_range_single_char(self):
        span = Span("test.prv", 10, 5, 10, 5)
        r = span_to_range(span)
        assert r.start.line == 9
        assert r.start.character == 4
        assert r.end.line == 9
        assert r.end.character == 5


class TestSeverityMap:
    def test_error_maps(self):
        assert _SEVERITY_MAP[Severity.ERROR] == lsp.DiagnosticSeverity.Error

    def test_warning_maps(self):
        assert _SEVERITY_MAP[Severity.WARNING] == lsp.DiagnosticSeverity.Warning

    def test_note_maps(self):
        assert _SEVERITY_MAP[Severity.NOTE] == lsp.DiagnosticSeverity.Information


class TestGetWordAt:
    def test_word_middle(self):
        assert _get_word_at("hello world", 0, 2) == "hello"

    def test_word_end(self):
        assert _get_word_at("hello world", 0, 5) == "hello"

    def test_word_start(self):
        assert _get_word_at("hello world", 0, 0) == "hello"

    def test_second_word(self):
        assert _get_word_at("hello world", 0, 8) == "world"

    def test_underscore_word(self):
        assert _get_word_at("my_var = 42", 0, 3) == "my_var"

    def test_empty(self):
        assert _get_word_at("", 0, 0) == ""

    def test_out_of_range(self):
        assert _get_word_at("hello", 5, 0) == ""


class TestTypesDisplay:
    def test_simple_function(self):
        from prove.types import INTEGER
        dummy = Span("<test>", 0, 0, 0, 0)
        sig = FunctionSignature(
            verb="transforms", name="add",
            param_names=["a", "b"],
            param_types=[INTEGER, INTEGER],
            return_type=INTEGER,
            can_fail=False,
            span=dummy,
        )
        result = _types_display(sig)
        assert "transforms" in result
        assert "add" in result
        assert "Integer" in result

    def test_failable_function(self):
        from prove.types import STRING
        dummy = Span("<test>", 0, 0, 0, 0)
        sig = FunctionSignature(
            verb="inputs", name="load",
            param_names=["path"],
            param_types=[STRING],
            return_type=STRING,
            can_fail=True,
            span=dummy,
        )
        result = _types_display(sig)
        assert result.endswith("!")


class TestAnalyze:
    def test_analyze_valid_source(self):
        source = (
            "transforms add(a Integer, b Integer) Integer\n"
            "from\n"
            "    a + b\n"
        )
        ds = _analyze("file:///test.prv", source)
        assert ds.module is not None
        assert ds.symbols is not None
        assert len(ds.diagnostics) == 0

    def test_analyze_with_errors(self):
        source = (
            "transforms add(a Integer, b Integer) Integer\n"
            "from\n"
            "    unknown_var\n"
        )
        ds = _analyze("file:///test.prv", source)
        assert ds.module is not None
        assert len(ds.diagnostics) > 0
        assert any("E310" in d.message for d in ds.diagnostics)

    def test_analyze_lex_error(self):
        source = "@@@ invalid tokens\n"
        ds = _analyze("file:///test.prv", source)
        assert len(ds.diagnostics) > 0

    def test_analyze_caches_state(self):
        from prove.lsp import _state
        source = "main()\nfrom\n    println(\"hi\")\n"
        uri = "file:///cache_test.prv"
        ds = _analyze(uri, source)
        assert _state.get(uri) is ds
        # Clean up
        _state.pop(uri, None)


class TestDocumentState:
    def test_default_state(self):
        ds = DocumentState()
        assert ds.source == ""
        assert ds.tokens == []
        assert ds.module is None
        assert ds.symbols is None
        assert ds.diagnostics == []
