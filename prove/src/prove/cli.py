"""Prove compiler CLI."""

from __future__ import annotations

from pathlib import Path

import click

from prove import __version__
from prove.config import find_config, load_config
from prove.project import scaffold


@click.group()
@click.version_option(__version__, prog_name="prove")
def main() -> None:
    """The Prove programming language compiler."""


@main.command()
@click.argument("path", default=".", type=click.Path(exists=True))
@click.option("--mutate", is_flag=True, help="Enable mutation testing.")
def build(path: str, mutate: bool) -> None:
    """Compile a Prove project."""
    try:
        config_path = find_config(Path(path))
        config = load_config(config_path)
        click.echo(f"building {config.package.name}...")
        if mutate:
            click.echo("(mutation testing not yet implemented)")
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
