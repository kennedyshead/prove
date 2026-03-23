"""Tests for the Prove CLI, config, and error rendering."""

from __future__ import annotations

import pytest
from click.testing import CliRunner

from prove.cli import main
from prove.config import find_config, load_config
from prove.errors import (
    CompileError,
    Diagnostic,
    DiagnosticLabel,
    DiagnosticRenderer,
    Severity,
    Suggestion,
)
from prove.source import SourceFile, Span


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def tmp_project(tmp_path):
    """Create a minimal prove project in a temp dir."""
    toml = tmp_path / "prove.toml"
    toml.write_text(
        '[package]\nname = "testproj"\nversion = "1.0.0"\n'
        '[build]\ntarget = "native"\n'
        "[test]\nproperty_rounds = 500\n"
    )
    src = tmp_path / "src"
    src.mkdir()
    (src / "main.prv").write_text(
        'module Main\n  narrative: """Test project"""\n'
        "  System outputs console\n\n"
        'main() Result<Unit, Error>!\nfrom\n    console("hi")\n'
    )
    return tmp_path


# --- CLI tests ---


class TestCLI:
    def test_help(self, runner):
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "Prove" in result.output
        assert "compiler" in result.output
        assert "export" in result.output
        assert "generate" in result.output
        assert "setup" in result.output
        assert "view" in result.output

    def test_version(self, runner):
        result = runner.invoke(main, ["--version"])
        assert result.exit_code == 0
        assert "1.1.0" in result.output

    def test_view_command(self, runner, tmp_project):
        prv_file = tmp_project / "src" / "main.prv"
        result = runner.invoke(main, ["view", str(prv_file)])
        assert result.exit_code == 0
        assert "Module" in result.output

    def test_export_help(self, runner):
        result = runner.invoke(main, ["export", "--help"])
        assert result.exit_code == 0
        assert "--format" in result.output or "-f" in result.output
        assert "treesitter" in result.output
        assert "pygments" in result.output
        assert "chroma" in result.output

    def test_export_runs(self, runner, tmp_path):
        # Create minimal workspace with stub grammar.js containing sentinels
        ts_dir = tmp_path / "tree-sitter-prove"
        ts_dir.mkdir()
        (ts_dir / "grammar.js").write_text(
            "// PROVE-EXPORT-BEGIN: verbs\n// PROVE-EXPORT-END: verbs\n"
        )
        result = runner.invoke(
            main,
            ["export", "-f", "treesitter", "-w", str(tmp_path)],
        )
        # Should succeed (tree-sitter-prove exists in workspace)
        assert result.exit_code == 0
        assert "tree-sitter-prove" in result.output


# --- Config tests ---


class TestConfig:
    def test_load_config(self, tmp_project):
        config = load_config(tmp_project / "prove.toml")
        assert config.package.name == "testproj"
        assert config.package.version == "1.0.0"
        assert config.build.target == "native"
        assert config.test.property_rounds == 500

    def test_load_config_defaults(self, tmp_path):
        toml = tmp_path / "prove.toml"
        toml.write_text("[package]\n")
        config = load_config(toml)
        assert config.package.name == "untitled"
        assert config.build.target == "native"
        assert config.test.property_rounds == 1000

    def test_find_config(self, tmp_project):
        # find_config from a subdirectory should find prove.toml in parent
        sub = tmp_project / "src"
        found = find_config(sub)
        assert found == tmp_project / "prove.toml"

    def test_find_config_not_found(self, tmp_path):
        empty = tmp_path / "empty"
        empty.mkdir()
        with pytest.raises(FileNotFoundError, match="No prove.toml found"):
            find_config(empty)


# --- Error rendering tests ---


class TestDiagnostics:
    def test_render_error(self):
        span = Span("server.prv", 12, 19, 12, 47)
        diag = Diagnostic(
            severity=Severity.ERROR,
            code="E042",
            message="`port` may exceed type bound",
            labels=[DiagnosticLabel(span=span, message="")],
            notes=["`get_integer` returns Integer, but Port requires 1..65535"],
            suggestions=[
                Suggestion(
                    message="clamp the value",
                    replacement='port as Port = clamp(get_integer(config, "port"), 1, 65535)',
                )
            ],
        )

        renderer = DiagnosticRenderer(color=False)
        output = renderer.render(diag)

        assert "error[E042]" in output
        assert "`port` may exceed type bound" in output
        assert "server.prv:12:19" in output
        assert "note:" in output
        assert "try:" in output

    def test_render_warning(self):
        span = Span("main.prv", 5, 1, 5, 10)
        diag = Diagnostic(
            severity=Severity.WARNING,
            code="W001",
            message="unused variable `x`",
            labels=[DiagnosticLabel(span=span, message="defined here")],
        )

        renderer = DiagnosticRenderer(color=False)
        output = renderer.render(diag)

        assert "warning[W001]" in output
        assert "unused variable `x`" in output

    def test_compile_error(self):
        diags = [
            Diagnostic(Severity.ERROR, "E001", "first error"),
            Diagnostic(Severity.ERROR, "E002", "second error"),
        ]
        err = CompileError(diags)
        assert len(err.diagnostics) == 2
        assert "2 error(s)" in str(err)


# --- Source tests ---


class TestSource:
    def test_source_file(self, tmp_path):
        f = tmp_path / "test.prv"
        f.write_text("line one\nline two\nline three\n")
        sf = SourceFile(f)
        assert sf.line_at(1) == "line one"
        assert sf.line_at(2) == "line two"
        assert sf.line_at(3) == "line three"
        assert sf.line_at(0) == ""
        assert sf.line_at(99) == ""

    def test_span_str(self):
        span = Span("file.prv", 10, 5, 10, 20)
        assert str(span) == "file.prv:10:5"


# --- Diagnostic quality tests (Phase H) ---


class TestDiagnosticNotes:
    def test_undefined_name_did_you_mean(self):
        from prove.checker import Checker
        from prove.lexer import Lexer
        from prove.parser import Parser

        source = (
            "transforms compute(x Integer) Integer\n"
            "    from\n"
            "        y\n"  # typo — should be x
        )
        tokens = Lexer(source, "test.prv").lex()
        module = Parser(tokens, "test.prv").parse()
        checker = Checker()
        checker.check(module)
        renderer = DiagnosticRenderer(color=False)
        rendered = [renderer.render(d) for d in checker.diagnostics]
        assert any("E310" in r for r in rendered)
        assert any("did you mean" in r for r in rendered)

    def test_wrong_arg_count_shows_signature(self):
        from prove.checker import Checker
        from prove.lexer import Lexer
        from prove.parser import Parser

        source = (
            "module Main\n"
            "  System outputs console\n"
            "  Types reads string\n"
            "transforms add(a Integer, b Integer) Integer\n"
            "    from\n"
            "        a + b\n"
            "\n"
            "main()\n"
            "    from\n"
            "        console(string(add(1)))\n"
        )
        tokens = Lexer(source, "test.prv").lex()
        module = Parser(tokens, "test.prv").parse()
        checker = Checker()
        checker.check(module)
        renderer = DiagnosticRenderer(color=False)
        rendered = [renderer.render(d) for d in checker.diagnostics]
        assert any("E330" in r for r in rendered)
        assert any("function signature:" in r for r in rendered)

    def test_source_line_in_render(self, tmp_path):
        """Diagnostics should show the source line from a real file."""
        prv = tmp_path / "test.prv"
        prv.write_text("transforms identity(x Integer) Integer\n    from\n        y\n")
        from prove.checker import Checker
        from prove.lexer import Lexer
        from prove.parser import Parser

        source = prv.read_text()
        tokens = Lexer(source, str(prv)).lex()
        module = Parser(tokens, str(prv)).parse()
        checker = Checker()
        checker.check(module)
        renderer = DiagnosticRenderer(color=False)
        rendered = [renderer.render(d) for d in checker.diagnostics]
        # Should include source line content
        assert any("y" in r and "^" in r for r in rendered)
