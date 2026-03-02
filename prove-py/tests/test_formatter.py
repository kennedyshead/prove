"""Tests for the Prove formatter (AST pretty-printer)."""

from __future__ import annotations

from pathlib import Path

import pytest

from prove.checker import Checker
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


def _format_with_types(source: str) -> str:
    """Parse, check, and format with type inference.

    Always passes symbols to the formatter — function signatures from
    pass 1 are useful even when pass 2 finds errors.
    """
    tokens = Lexer(source, "<test>").lex()
    module = Parser(tokens, "<test>").parse()
    checker = Checker()
    symbols = checker.check(module)
    return ProveFormatter(symbols=symbols).format(module)


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

    def test_binary_type(self):
        source = (
            "module M\n"
            "\n"
            "  type Table<V> is binary\n"
        )
        assert _roundtrip(source) == source

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
        source = "module Foo\n  InputOutput outputs console\n"
        assert _roundtrip(source) == source

    def test_import_verb_groups(self):
        source = "module Foo\n  InputOutput outputs console, inputs file\n"
        assert _roundtrip(source) == source

    def test_import_types_verb(self):
        source = "module Foo\n  InputOutput inputs console file\n"
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


class TestFormatterTypeInference:
    """v0.8: Type inference for untyped variable declarations."""

    def test_unqualified_call_infers_type(self):
        """len(items) → count as Integer = len(items)"""
        source = (
            "transforms size(items List<Integer>) Integer\n"
            "from\n"
            "    count as = len(items)\n"
            "    count\n"
        )
        result = _format_with_types(source)
        assert "count as Integer = len(items)" in result

    def test_unqualified_call_to_string(self):
        """to_string(x) → s as String = to_string(x)"""
        source = (
            "transforms show(n Integer) String\n"
            "from\n"
            "    s as = to_string(n)\n"
            "    s\n"
        )
        result = _format_with_types(source)
        assert "s as String = to_string(n)" in result

    def test_existing_annotation_preserved(self):
        """Never overwrite an existing type annotation."""
        source = (
            "transforms size(items List<Integer>) Integer\n"
            "from\n"
            "    count as Integer = len(items)\n"
            "    count\n"
        )
        result = _format_with_types(source)
        assert "count as Integer = len(items)" in result

    def test_no_inference_for_literals(self):
        """Literal RHS: no type inferred (out of scope)."""
        source = (
            "transforms id(n Integer) Integer\n"
            "from\n"
            "    x as = n\n"
            "    x\n"
        )
        result = _format_with_types(source)
        # No call on RHS, so no type inference — stays bare
        assert "x as = n" in result

    def test_no_symbols_no_inference(self):
        """Without symbols, formatter skips type inference."""
        source = (
            "transforms size(items List<Integer>) Integer\n"
            "from\n"
            "    count as = len(items)\n"
            "    count\n"
        )
        # Use formatter without symbols
        tokens = Lexer(source, "<test>").lex()
        module = Parser(tokens, "<test>").parse()
        result = ProveFormatter().format(module)
        assert "count as = len(items)" in result

    def test_user_defined_function_infers_type(self):
        """User-defined function return type is inferred."""
        source = (
            "transforms double(n Integer) Integer\n"
            "from\n"
            "    n * 2\n"
            "\n"
            "transforms test_it(x Integer) Integer\n"
            "from\n"
            "    result as = double(x)\n"
            "    result\n"
        )
        result = _format_with_types(source)
        assert "result as Integer = double(x)" in result

    def test_assignment_promoted_to_var_decl(self):
        """Assignment with call RHS becomes a typed VarDecl."""
        source = (
            "transforms size(items List<Integer>) Integer\n"
            "from\n"
            "    count = len(items)\n"
            "    count\n"
        )
        result = _format_with_types(source)
        assert "count as Integer = len(items)" in result

    def test_assignment_without_call_unchanged(self):
        """Assignment with non-call RHS stays as assignment."""
        source = (
            "transforms id(n Integer) Integer\n"
            "from\n"
            "    x = n\n"
            "    x\n"
        )
        result = _format_with_types(source)
        assert "x = n" in result
        assert "x as" not in result

    def test_failprop_assignment_infers_result_type(self):
        """FailProp call assignment gets Result type annotation."""
        source = (
            "module Main\n"
            '  narrative: """test"""\n'
            "  InputOutput inputs file, outputs console\n"
            "  Parse creates text object, reads toml text, types Value\n"
            "  Table reads keys get, types Table, validates has\n"
            "  Text transforms join\n"
            "\n"
            "main() Result<Unit, Error>!\n"
            "from\n"
            '    source as String = file("config.toml")!\n'
            "    doc = toml(source)!\n"
            "    root as Table<Value> = object(doc)\n"
            "    names as List<String> = keys(root)\n"
            '    console("done")\n'
        )
        result = _format_with_types(source)
        assert "doc as Value = toml(source)!" in result

    def test_roundtrip_stable_with_types(self):
        """Formatting twice with type inference produces identical output."""
        source = (
            "transforms size(items List<Integer>) Integer\n"
            "from\n"
            "    count as = len(items)\n"
            "    count\n"
        )
        first = _format_with_types(source)
        second = _format_with_types(first)
        assert first == second
