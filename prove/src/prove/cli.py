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
    try:
        config_path = find_config(Path(path))
        config = load_config(config_path)
        rounds = property_rounds or config.test.property_rounds
        click.echo(f"testing {config.package.name} (property rounds: {rounds})...")
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
def format_cmd(path: str) -> None:
    """Format Prove source files."""
    click.echo("format: not yet implemented")


@main.command()
def lsp() -> None:
    """Start the Prove language server."""
    click.echo("lsp: not yet implemented")


@main.command()
@click.argument("file", type=click.Path(exists=True))
def view(file: str) -> None:
    """View a compiled Prove artifact."""
    click.echo("view: not yet implemented")
