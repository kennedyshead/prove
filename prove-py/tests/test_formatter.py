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
        source = 'main()\nfrom\n    println("hello")\n'
        assert _roundtrip(source) == source

    def test_main_with_return_type(self):
        source = 'main() Result<Unit, Error>!\nfrom\n    println("hello")\n'
        assert _roundtrip(source) == source

    def test_doc_comment(self):
        source = (
            "/// Adds two numbers.\ntransforms add(a Integer, b Integer) Integer\nfrom\n    a + b\n"
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
        source = "module M\n\n  type Product is\n    name String\n    price Integer\n"
        assert _roundtrip(source) == source

    def test_algebraic_type(self):
        source = "module M\n\n  type Route is Get(path String)\n    | Post(path String)\n"
        assert _roundtrip(source) == source

    def test_unit_variants(self):
        source = "module M\n  type Status is Pending | Active | Done\n"
        result = _parse_format(source)
        assert "Pending" in result
        assert "Active" in result
        assert "Done" in result

    def test_binary_type(self):
        source = "module M\n\n  type Table<Value> is binary\n"
        assert _roundtrip(source) == source

    def test_generic_type(self):
        source = "transforms identity(x List<Integer>) List<Integer>\nfrom\n    x\n"
        assert _roundtrip(source) == source


class TestFormatterExpressions:
    def test_binary_expr(self):
        source = "transforms add(a Integer, b Integer) Integer\nfrom\n    a + b\n"
        assert _roundtrip(source) == source

    def test_call_expr(self):
        source = "main()\nfrom\n    println(to_string(42))\n"
        assert _roundtrip(source) == source

    def test_pipe_expr(self):
        source = 'main()\nfrom\n    "hello" |> println\n'
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
            "transforms doubled(xs List<Integer>) List<Integer>\nfrom\n    map(xs, |x| x * 2)\n"
        )
        assert _roundtrip(source) == source

    def test_list_literal(self):
        source = "main()\nfrom\n    println(to_string([1, 2, 3]))\n"
        assert _roundtrip(source) == source

    def test_fail_propagation(self):
        source = "inputs load(path String) String!\nfrom\n    read_file(path)!\n"
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
        source = "module M\n  MAX as Integer = 100\n"
        result = _parse_format(source)
        assert "MAX" in result
        assert "100" in result


_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


class TestFormatterRoundTrip:
    """Test round-trip formatting on the example .prv files."""

    @pytest.fixture(
        params=[
            "examples/hello/src/main.prv",
            "examples/math/src/main.prv",
        ]
    )
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
        assert first == second, f"Formatter is not idempotent on {example_file.name}"


class TestFormatterVarDecl:
    def test_var_decl_with_type(self):
        source = "main()\nfrom\n    x as Integer = 42\n    println(to_string(x))\n"
        assert _roundtrip(source) == source

    def test_var_decl_without_type(self):
        source = "main()\nfrom\n    x = 42\n    println(to_string(x))\n"
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
        source = "transforms show(n Integer) String\nfrom\n    s as = to_string(n)\n    s\n"
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

    def test_identifier_rhs_infers_type(self):
        """Identifier RHS infers type from parameter context."""
        source = "transforms id(n Integer) Integer\nfrom\n    x as = n\n    x\n"
        result = _format_with_types(source)
        # n is Integer param, so x gets inferred as Integer
        assert "x as Integer = n" in result

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

    def test_assignment_with_identifier_promotes_to_var_decl(self):
        """Assignment with identifier RHS promotes to var decl."""
        source = "transforms id(n Integer) Integer\nfrom\n    x = n\n    x\n"
        result = _format_with_types(source)
        # n is Integer param, so x gets promoted to typed var decl
        assert "x as Integer = n" in result

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

    def test_mutable_type_inferred_from_call(self):
        """Auto-typed variable should include :[Mutable] modifier."""
        source = (
            "module Main\n"
            '  narrative: """test"""\n'
            "\n"
            "  type User:[Mutable] is\n"
            "    id Integer\n"
            "    name String\n"
            "\n"
            "transforms make_user(id Integer, name String) User:[Mutable]\n"
            "from\n"
            "    User(id, name)\n"
            "\n"
            "transforms test_it(id Integer) User:[Mutable]\n"
            "from\n"
            '    u as = make_user(id, "test")\n'
            "    u\n"
        )
        result = _format_with_types(source)
        assert 'u as User:[Mutable] = make_user(id, "test")' in result

    def test_mutable_type_preserved_when_already_annotated(self):
        """Existing User:[Mutable] annotation must not be stripped."""
        source = (
            "module Main\n"
            '  narrative: """test"""\n'
            "\n"
            "  type User:[Mutable] is\n"
            "    id Integer\n"
            "    name String\n"
            "\n"
            "transforms make_user(id Integer, name String) User:[Mutable]\n"
            "from\n"
            "    User(id, name)\n"
            "\n"
            "transforms test_it(id Integer) User:[Mutable]\n"
            "from\n"
            '    u as User:[Mutable] = make_user(id, "test")\n'
            "    u\n"
        )
        result = _format_with_types(source)
        assert 'u as User:[Mutable] = make_user(id, "test")' in result

    def test_mutable_type_roundtrip_stable(self):
        """Formatting twice with mutable type inference is stable."""
        source = (
            "module Main\n"
            '  narrative: """test"""\n'
            "\n"
            "  type User:[Mutable] is\n"
            "    id Integer\n"
            "    name String\n"
            "\n"
            "transforms make_user(id Integer, name String) User:[Mutable]\n"
            "from\n"
            "    User(id, name)\n"
            "\n"
            "transforms test_it(id Integer) User:[Mutable]\n"
            "from\n"
            '    u as = make_user(id, "test")\n'
            "    u\n"
        )
        first = _format_with_types(source)
        second = _format_with_types(first)
        assert first == second


def _format_with_fixes(source: str) -> str:
    """Parse, check, and format with diagnostics for auto-fixes."""
    tokens = Lexer(source, "<test>").lex()
    module = Parser(tokens, "<test>").parse()
    checker = Checker()
    checker.check(module)
    return ProveFormatter(
        symbols=checker.symbols,
        diagnostics=checker.diagnostics,
    ).format(module)


class TestFormatterAutoFixes:
    """Auto-fix tests: formatter resolves info-level diagnostics."""

    def test_e360_strips_validates_return_type(self):
        """E360: validates has implicit Boolean return — strip explicit type."""
        source = "validates is_positive(x Integer) Boolean\nfrom\n    x > 0\n"
        result = _roundtrip(source)
        assert "validates is_positive(x Integer)\n" in result
        assert "Boolean" not in result

    def test_e360_preserves_non_validates_return_type(self):
        """Return types on non-validates verbs are preserved."""
        source = "transforms double(x Integer) Integer\nfrom\n    x * 2\n"
        result = _roundtrip(source)
        assert "Integer" in result

    def test_w301_drops_unreachable_arms(self):
        """W301: arms after wildcard are dropped."""
        source = (
            "module M\n"
            "  type Color is Red | Green\n"
            "\n"
            "  transforms name(c Color) String\n"
            "  from\n"
            "      match c\n"
            '          _ => "any"\n'
            '          Red => "red"\n'
        )
        result = _roundtrip(source)
        assert '_ => "any"' in result
        assert "Red =>" not in result

    def test_w301_preserves_arms_before_wildcard(self):
        """Arms before wildcard are kept."""
        source = (
            "module M\n"
            "  type Color is Red | Green\n"
            "\n"
            "  transforms name(c Color) String\n"
            "  from\n"
            "      match c\n"
            '          Red => "red"\n'
            '          _ => "other"\n'
        )
        result = _roundtrip(source)
        assert "Red =>" in result
        assert '_ => "other"' in result

    def test_w303_drops_unused_type(self):
        """W303: unused type definition is removed."""
        source = (
            "module M\n  type Unused is\n    x Integer\n\ntransforms one() Integer\nfrom\n    1\n"
        )
        result = _format_with_fixes(source)
        assert "Unused" not in result
        assert "transforms one() Integer" in result

    def test_w303_keeps_used_type(self):
        """Used type definitions are preserved."""
        source = (
            "module M\n"
            "  type Point is\n"
            "    x Integer\n"
            "    y Integer\n"
            "\n"
            "transforms origin() Point\n"
            "from\n"
            "    Point(0, 0)\n"
        )
        result = _format_with_fixes(source)
        assert "type Point is" in result

    def test_w300_prefixes_unused_var(self):
        """W300: formatter prefixes unused variable names with _."""
        from prove.errors import Diagnostic, DiagnosticLabel, Severity

        source = "transforms one() Integer\nfrom\n    unused as Integer = 42\n    1\n"
        tokens = Lexer(source, "<test>").lex()
        module = Parser(tokens, "<test>").parse()
        # The VarDecl for 'unused' is on line 3.  Build a synthetic W300.
        var_decl = module.declarations[0].body[0]
        diag = Diagnostic(
            severity=Severity.NOTE,
            code="I300",
            message="unused variable 'unused'",
            labels=[DiagnosticLabel(span=var_decl.span, message="")],
        )
        result = ProveFormatter(diagnostics=[diag]).format(module)
        assert "_unused as Integer = 42" in result

    def test_w300_skips_already_prefixed(self):
        """Variable already starting with _ is not double-prefixed."""
        from prove.errors import Diagnostic, DiagnosticLabel, Severity

        source = "transforms one() Integer\nfrom\n    _ignored as Integer = 42\n    1\n"
        tokens = Lexer(source, "<test>").lex()
        module = Parser(tokens, "<test>").parse()
        var_decl = module.declarations[0].body[0]
        diag = Diagnostic(
            severity=Severity.NOTE,
            code="I300",
            message="unused variable '_ignored'",
            labels=[DiagnosticLabel(span=var_decl.span, message="")],
        )
        result = ProveFormatter(diagnostics=[diag]).format(module)
        assert "_ignored" in result
        assert "__ignored" not in result

    def test_w302_drops_unused_import_item(self):
        """W302: unused import items are removed."""
        source = (
            "module Main\n"
            "  Text transforms trim upper\n"
            "\n"
            "transforms clean(s String) String\n"
            "from\n"
            "    Text.trim(s)\n"
        )
        result = _format_with_fixes(source)
        assert "trim" in result
        assert "upper" not in result

    def test_w302_drops_entire_import_line(self):
        """W302: when all items unused, entire import line is dropped."""
        source = (
            "module Main\n"
            "  Text transforms trim\n"
            "\n"
            "transforms greet(name String) String\n"
            "from\n"
            "    name\n"
        )
        result = _format_with_fixes(source)
        assert "Text" not in result

    def test_w302_keeps_used_imports(self):
        """Used imports are preserved."""
        source = (
            "module Main\n"
            "  Text transforms trim\n"
            "\n"
            "transforms clean(s String) String\n"
            "from\n"
            "    Text.trim(s)\n"
        )
        result = _format_with_fixes(source)
        assert "Text transforms trim" in result

    def test_autofix_roundtrip_stable(self):
        """Formatting twice with auto-fixes produces identical output."""
        source = "validates is_positive(x Integer) Boolean\nfrom\n    x > 0\n"
        first = _format_with_fixes(source)
        second = _format_with_fixes(first)
        assert first == second
