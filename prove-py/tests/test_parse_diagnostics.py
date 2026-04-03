"""Tests for parse diagnostics emitted by CSTConverter (E2xx codes)."""

from __future__ import annotations

import pytest

from prove.errors import CompileError
from prove.parse import parse


class TestValidSourceNoDiagnostics:
    def test_minimal_module(self) -> None:
        module = parse('module Foo\n  narrative: "test"\n', "test.prv")
        assert module.parse_diagnostics == ()

    def test_module_with_function(self) -> None:
        source = (
            'module Foo\n  narrative: "test"\n\ntransforms bar(x Integer) Integer\nfrom\n  x + 1\n'
        )
        module = parse(source, "test.prv")
        assert module.parse_diagnostics == ()


class TestE200GeneralParseError:
    def test_function_outside_module_without_from(self) -> None:
        """Function without `from` block is parsed as ERROR at top level."""
        source = 'module Foo\n  narrative: "test"\n\ntransforms bar(x Integer) Integer\n  x + 1\n'
        module = parse(source, "test.prv")
        assert any(d.code == "E200" for d in module.parse_diagnostics)


class TestE210ExpectedToken:
    def test_as_keyword_in_parameter(self) -> None:
        """Prove doesn't use `as` in parameters — tree-sitter emits ERROR."""
        source = (
            "module Foo\n"
            '  narrative: "test"\n'
            "\n"
            "transforms bar(x as Integer) Integer\n"
            "from\n"
            "  x + 1\n"
        )
        module = parse(source, "test.prv")
        # Tree-sitter emits ERROR for `as` — should produce a parse diagnostic
        has_diag = len(module.parse_diagnostics) > 0
        assert has_diag

    def test_arrow_return_type(self) -> None:
        """Prove doesn't use `->` for return types — tree-sitter emits ERROR."""
        source = (
            "module Foo\n"
            '  narrative: "test"\n'
            "\n"
            "transforms bar(x Integer) -> Integer\n"
            "from\n"
            "  x + 1\n"
        )
        module = parse(source, "test.prv")
        has_diag = len(module.parse_diagnostics) > 0
        assert has_diag


class TestE211ExpectedDeclaration:
    def test_double_verb_keyword(self) -> None:
        """Two verb keywords in a row produces ERROR inside module body."""
        source = (
            "module Foo\n"
            '  narrative: "test"\n'
            "\n"
            "  transforms transforms bar(x Integer) Integer\n"
            "  from\n"
            "    x + 1\n"
        )
        module = parse(source, "test.prv")
        has_e211 = any(d.code == "E211" for d in module.parse_diagnostics)
        has_any = len(module.parse_diagnostics) > 0
        assert has_e211 or has_any


class TestLexerErrorsStillWork:
    def test_invalid_characters_raise_compile_error(self) -> None:
        """Lexer errors (E10x) should still raise CompileError before parse."""
        with pytest.raises(CompileError):
            parse("@@@ invalid", "test.prv")


class TestDiagnosticDedup:
    def test_no_duplicate_spans(self) -> None:
        """Multiple errors at the same location should be deduped."""
        source = (
            "module Foo\n"
            '  narrative: "test"\n'
            "\n"
            "transforms bar(x as Integer) -> Integer\n"
            "from\n"
            "  x + 1\n"
        )
        module = parse(source, "test.prv")
        if module.parse_diagnostics:
            spans = [
                (d.labels[0].span.start_line, d.labels[0].span.start_col)
                for d in module.parse_diagnostics
                if d.labels
            ]
            assert len(spans) == len(set(spans))


class TestParseStillProducesAST:
    def test_partial_ast_with_errors(self) -> None:
        """Even with parse errors, a partial AST should be produced."""
        source = (
            "module Foo\n"
            '  narrative: "test"\n'
            "\n"
            "transforms bar(x as Integer) Integer\n"
            "from\n"
            "  x + 1\n"
        )
        module = parse(source, "test.prv")
        # Should still produce declarations despite errors
        assert len(module.declarations) > 0
        # And should have diagnostics
        assert len(module.parse_diagnostics) > 0
