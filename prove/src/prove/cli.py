"""Prove compiler CLI."""

from __future__ import annotations

from pathlib import Path

import click

from prove import __version__
from prove.checker import Checker
from prove.config import find_config, load_config
from prove.errors import CompileError, DiagnosticRenderer, Severity
from prove.lexer import Lexer
from prove.parser import Parser
from prove.project import scaffold


def _compile_project(project_path: Path, *, check_only: bool = False) -> bool:
    """Lex, parse, and check all .prv files under src/. Returns True if OK."""
    src_dir = project_path / "src"
    if not src_dir.is_dir():
        src_dir = project_path  # fallback to project root

    prv_files = sorted(src_dir.rglob("*.prv"))
    if not prv_files:
        click.echo("warning: no .prv files found", err=True)
        return True

    renderer = DiagnosticRenderer(color=True)
    had_errors = False

    for prv_file in prv_files:
        source = prv_file.read_text()
        filename = str(prv_file)

        try:
            tokens = Lexer(source, filename).lex()
            module = Parser(tokens, filename).parse()
        except CompileError as e:
            had_errors = True
            for diag in e.diagnostics:
                click.echo(renderer.render(diag), err=True)
            continue

        checker = Checker()
        checker.check(module)

        for diag in checker.diagnostics:
            click.echo(renderer.render(diag), err=True)
            if diag.severity == Severity.ERROR:
                had_errors = True

    return not had_errors


@click.group()
@click.version_option(__version__, prog_name="prove")
def main() -> None:
    """The Prove programming language compiler."""


@main.command()
@click.argument("path", default=".", type=click.Path(exists=True))
@click.option("--mutate", is_flag=True, help="Enable mutation testing.")
def build(path: str, mutate: bool) -> None:
    """Compile a Prove project."""
    from prove.builder import build_project

    try:
        config_path = find_config(Path(path))
        config = load_config(config_path)
        click.echo(f"building {config.package.name}...")
        project_dir = config_path.parent

        renderer = DiagnosticRenderer(color=True)
        result = build_project(project_dir, config)

        for diag in result.diagnostics:
            click.echo(renderer.render(diag), err=True)

        if not result.ok:
            if result.c_error:
                click.echo(f"error: {result.c_error}", err=True)
            raise SystemExit(1)

        if mutate:
            click.echo("(mutation testing not yet implemented)")
        click.echo(f"built {config.package.name} -> {result.binary}")
    except FileNotFoundError:
        click.echo("error: no prove.toml found", err=True)
        raise SystemExit(1)


@main.command()
@click.argument("path", default=".", type=click.Path(exists=True))
def check(path: str) -> None:
    """Type-check a Prove project without compiling."""
    try:
        config_path = find_config(Path(path))
        config = load_config(config_path)
        click.echo(f"checking {config.package.name}...")
        project_dir = config_path.parent
        ok = _compile_project(project_dir, check_only=True)
        if ok:
            click.echo(f"checked {config.package.name} — no errors")
        else:
            raise SystemExit(1)
    except FileNotFoundError:
        click.echo("error: no prove.toml found", err=True)
        raise SystemExit(1)


@main.command()
@click.argument("path", default=".", type=click.Path(exists=True))
@click.option("--property-rounds", type=int, default=None, help="Override property test rounds.")
def test(path: str, property_rounds: int | None) -> None:
    """Run tests for a Prove project."""
    from prove.testing import run_tests

    try:
        config_path = find_config(Path(path))
        config = load_config(config_path)
        rounds = property_rounds or config.test.property_rounds
        project_dir = config_path.parent
        click.echo(f"testing {config.package.name} (property rounds: {rounds})...")

        # Parse and check all modules
        src_dir = project_dir / "src"
        if not src_dir.is_dir():
            src_dir = project_dir

        prv_files = sorted(src_dir.rglob("*.prv"))
        if not prv_files:
            click.echo("warning: no .prv files found", err=True)
            return

        renderer = DiagnosticRenderer(color=True)
        modules = []
        had_errors = False

        for prv_file in prv_files:
            source = prv_file.read_text()
            filename = str(prv_file)
            try:
                tokens = Lexer(source, filename).lex()
                module = Parser(tokens, filename).parse()
            except CompileError as e:
                had_errors = True
                for diag in e.diagnostics:
                    click.echo(renderer.render(diag), err=True)
                continue

            checker = Checker()
            symbols = checker.check(module)
            for diag in checker.diagnostics:
                click.echo(renderer.render(diag), err=True)
                if diag.severity == Severity.ERROR:
                    had_errors = True

            if not checker.has_errors():
                modules.append((module, symbols))

        if had_errors:
            raise SystemExit(1)

        result = run_tests(
            project_dir, modules, property_rounds=rounds,
        )

        if result.output:
            click.echo(result.output)

        if result.c_error:
            click.echo(f"error: {result.c_error}", err=True)
            raise SystemExit(1)

        if result.ok:
            click.echo(
                f"tested {config.package.name} — "
                f"{result.tests_run} tests, "
                f"{result.tests_passed} passed"
            )
        else:
            click.echo(
                f"tested {config.package.name} — "
                f"{result.tests_failed} FAILED",
                err=True,
            )
            raise SystemExit(1)
    except FileNotFoundError:
        click.echo("error: no prove.toml found", err=True)
        raise SystemExit(1)


@main.command()
@click.argument("name")
def new(name: str) -> None:
    """Create a new Prove project."""
    try:
        project_dir = scaffold(name)
        click.echo(f"created project '{name}' at {project_dir}")
    except FileExistsError as e:
        click.echo(f"error: {e}", err=True)
        raise SystemExit(1)


@main.command(name="format")
@click.argument("path", default=".", type=click.Path(exists=True))
@click.option("--check", is_flag=True, help="Check formatting without modifying files.")
@click.option("--stdin", "use_stdin", is_flag=True, help="Read from stdin, write to stdout.")
def format_cmd(path: str, check: bool, use_stdin: bool) -> None:
    """Format Prove source files."""
    import sys

    from prove.formatter import ProveFormatter

    formatter = ProveFormatter()

    if use_stdin:
        source = sys.stdin.read()
        try:
            tokens = Lexer(source, "<stdin>").lex()
            module = Parser(tokens, "<stdin>").parse()
        except CompileError as e:
            renderer = DiagnosticRenderer(color=True)
            for diag in e.diagnostics:
                click.echo(renderer.render(diag), err=True)
            raise SystemExit(1)
        formatted = formatter.format(module)
        if check:
            if formatted != source:
                raise SystemExit(1)
        else:
            sys.stdout.write(formatted)
        return

    target = Path(path)
    prv_files = sorted(target.rglob("*.prv")) if target.is_dir() else [target]

    if not prv_files:
        click.echo("no .prv files found", err=True)
        return

    needs_formatting = False
    for prv_file in prv_files:
        source = prv_file.read_text()
        filename = str(prv_file)
        try:
            tokens = Lexer(source, filename).lex()
            module = Parser(tokens, filename).parse()
        except CompileError as e:
            renderer = DiagnosticRenderer(color=True)
            for diag in e.diagnostics:
                click.echo(renderer.render(diag), err=True)
            continue

        formatted = formatter.format(module)
        if formatted != source:
            if check:
                click.echo(f"would reformat {filename}")
                needs_formatting = True
            else:
                prv_file.write_text(formatted)
                click.echo(f"formatted {filename}")

    if check and needs_formatting:
        raise SystemExit(1)


@main.command()
def lsp() -> None:
    """Start the Prove language server."""
    from prove.lsp import main as lsp_main

    lsp_main()


@main.command()
@click.argument("file", type=click.Path(exists=True))
def view(file: str) -> None:
    """View the AST of a Prove source file."""
    source = Path(file).read_text()
    filename = str(file)

    try:
        tokens = Lexer(source, filename).lex()
        module = Parser(tokens, filename).parse()
    except CompileError as e:
        renderer = DiagnosticRenderer(color=True)
        for diag in e.diagnostics:
            click.echo(renderer.render(diag), err=True)
        raise SystemExit(1)

    _dump_ast(module, 0)


def _dump_ast(node: object, depth: int) -> None:
    """Print a readable AST dump."""
    indent = "  " * depth
    name = type(node).__name__

    if hasattr(node, "__dataclass_fields__"):
        fields = node.__dataclass_fields__  # type: ignore[union-attr]
        click.echo(f"{indent}{name}")
        for field_name in fields:
            if field_name == "span":
                continue
            value = getattr(node, field_name)
            if isinstance(value, list):
                if value:
                    click.echo(f"{indent}  {field_name}:")
                    for item in value:
                        _dump_ast(item, depth + 2)
                else:
                    click.echo(f"{indent}  {field_name}: []")
            elif hasattr(value, "__dataclass_fields__"):
                click.echo(f"{indent}  {field_name}:")
                _dump_ast(value, depth + 2)
            elif value is not None:
                click.echo(f"{indent}  {field_name}: {value!r}")
    else:
        click.echo(f"{indent}{name}: {node!r}")
