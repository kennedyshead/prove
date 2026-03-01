"""Tests for the Prove formatter (AST pretty-printer)."""

from __future__ import annotations

from pathlib import Path

import pytest

from prove.formatter import ProveFormatter
from prove.lexer import Lexer
from prove.parser import Parser


def _roundtrip(source: str) -> str:
    """Parse source and format back to text."""
    tokens = Lexer(source, "<test>").lex()
    module = Parser(tokens, "<test>").parse()
    return ProveFormatter().format(module)


def _parse_format(source: str) -> str:
    """Parse and format, stripping trailing whitespace for comparison."""
    return _roundtrip(source).rstrip("\n")


class TestFormatterBasic:
    def test_simple_function(self):
        source = (
            "transforms add(a Integer, b Integer) Integer\n"
            "  ensures result == a + b\n"
            "from\n"
            "    a + b\n"
        )
        assert _roundtrip(source) == source

    def test_main_function(self):
        source = (
            "main()\n"
            "from\n"
            '    println("hello")\n'
        )
        assert _roundtrip(source) == source

    def test_main_with_return_type(self):
        source = (
            "main() Result<Unit, Error>!\n"
            "from\n"
            '    println("hello")\n'
        )
        assert _roundtrip(source) == source

    def test_doc_comment(self):
        source = (
            "/// Adds two numbers.\n"
            "transforms add(a Integer, b Integer) Integer\n"
            "from\n"
            "    a + b\n"
        )
        assert _roundtrip(source) == source

    def test_doc_comment_with_examples(self):
        source = (
            "/// add(1, 2) == 3\n"
            "/// add(0, 0) == 0\n"
            "transforms add(a Integer, b Integer) Integer\n"
            "from\n"
            "    a + b\n"
        )
        assert _roundtrip(source) == source


class TestFormatterTypes:
    def test_record_type(self):
        source = (
            "module M\n"
            "\n"
            "  type Product is\n"
            "    name String\n"
            "    price Integer\n"
        )
        assert _roundtrip(source) == source

    def test_algebraic_type(self):
        source = (
            "module M\n"
            "\n"
            "  type Route is Get(path String)\n"
            "    | Post(path String)\n"
        )
        assert _roundtrip(source) == source

    def test_unit_variants(self):
        source = (
            "module M\n"
            "  type Status is Pending | Active | Done\n"
        )
        result = _parse_format(source)
        assert "Pending" in result
        assert "Active" in result
        assert "Done" in result

    def test_generic_type(self):
        source = (
            "transforms identity(x List<Integer>) List<Integer>\n"
            "from\n"
            "    x\n"
        )
        assert _roundtrip(source) == source


class TestFormatterExpressions:
    def test_binary_expr(self):
        source = (
            "transforms add(a Integer, b Integer) Integer\n"
            "from\n"
            "    a + b\n"
        )
        assert _roundtrip(source) == source

    def test_call_expr(self):
        source = (
            "main()\n"
            "from\n"
            "    println(to_string(42))\n"
        )
        assert _roundtrip(source) == source

    def test_pipe_expr(self):
        source = (
            "main()\n"
            "from\n"
            '    "hello" |> println\n'
        )
        assert _roundtrip(source) == source

    def test_match_expr(self):
        source = (
            "transforms handle(route Route) String\n"
            "from\n"
            "    match route\n"
            '        Get(path) => "GET " + path\n'
            '        Post(path) => "POST " + path\n'
        )
        assert _roundtrip(source) == source

    def test_lambda_expr(self):
        source = (
            "transforms doubled(xs List<Integer>) List<Integer>\n"
            "from\n"
            "    map(xs, |x| x * 2)\n"
        )
        assert _roundtrip(source) == source

    def test_list_literal(self):
        source = (
            "main()\n"
            "from\n"
            "    println(to_string([1, 2, 3]))\n"
        )
        assert _roundtrip(source) == source

    def test_fail_propagation(self):
        source = (
            "inputs load(path String) String!\n"
            "from\n"
            "    read_file(path)!\n"
        )
        assert _roundtrip(source) == source


class TestFormatterAnnotations:
    def test_ensures(self):
        source = (
            "transforms add(a Integer, b Integer) Integer\n"
            "  ensures result == a + b\n"
            "from\n"
            "    a + b\n"
        )
        assert _roundtrip(source) == source

    def test_requires(self):
        source = (
            "transforms safe_div(a Integer, b Integer) Integer\n"
            "  requires b != 0\n"
            "from\n"
            "    a / b\n"
        )
        assert _roundtrip(source) == source

    def test_believe(self):
        source = (
            "transforms abs_val(n Integer) Integer\n"
            "  ensures result >= 0\n"
            "  believe: result >= 0\n"
            "from\n"
            "    match n >= 0\n"
            "        true => n\n"
            "        false => 0 - n\n"
        )
        assert _roundtrip(source) == source


class TestFormatterImports:
    def test_import(self):
        source = "module Foo\n  InputOutput outputs standard\n"
        assert _roundtrip(source) == source

    def test_import_verb_groups(self):
        source = "module Foo\n  InputOutput outputs standard, inputs file\n"
        assert _roundtrip(source) == source

    def test_import_types_verb(self):
        source = "module Foo\n  InputOutput inputs standard file\n"
        assert _roundtrip(source) == source


class TestFormatterConstants:
    def test_simple_constant(self):
        source = (
            "module M\n"
            "  MAX as Integer = 100\n"
        )
        result = _parse_format(source)
        assert "MAX" in result
        assert "100" in result


_PROJECT_ROOT = Path(__file__).resolve().parent.parent


class TestFormatterRoundTrip:
    """Test round-trip formatting on the example .prv files."""

    @pytest.fixture(params=[
        "examples/hello/src/main.prv",
        "examples/math/src/main.prv",
    ])
    def example_file(self, request: pytest.FixtureRequest) -> Path:
        path = _PROJECT_ROOT / request.param
        if not path.exists():
            pytest.skip(f"{request.param} not found")
        return path

    def test_roundtrip_stable(self, example_file: Path):
        """Formatting a file twice should produce the same result."""
        source = example_file.read_text()
        first = _roundtrip(source)
        second = _roundtrip(first)
        assert first == second, (
            f"Formatter is not idempotent on {example_file.name}"
        )


class TestFormatterVarDecl:
    def test_var_decl_with_type(self):
        source = (
            "main()\n"
            "from\n"
            "    x as Integer = 42\n"
            "    println(to_string(x))\n"
        )
        assert _roundtrip(source) == source

    def test_var_decl_without_type(self):
        source = (
            "main()\n"
            "from\n"
            "    x = 42\n"
            "    println(to_string(x))\n"
        )
        result = _parse_format(source)
        assert "x" in result
        assert "42" in result
