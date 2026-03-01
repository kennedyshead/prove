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


def _compile_project(
    project_path: Path,
) -> tuple[bool, int, int]:
    """Lex, parse, and check all .prv files under src/.

    Returns (ok, checked, errors) tuple.
    """
    src_dir = project_path / "src"
    if not src_dir.is_dir():
        src_dir = project_path  # fallback to project root

    prv_files = sorted(src_dir.rglob("*.prv"))
    if not prv_files:
        click.echo("warning: no .prv files found", err=True)
        return True, 0, 0

    renderer = DiagnosticRenderer(color=True)
    checked = 0
    errors = 0

    for prv_file in prv_files:
        source = prv_file.read_text()
        filename = str(prv_file)

        try:
            tokens = Lexer(source, filename).lex()
            module = Parser(tokens, filename).parse()
        except CompileError as e:
            errors += 1
            for diag in e.diagnostics:
                click.echo(renderer.render(diag), err=True)
            continue

        checked += 1
        checker = Checker()
        checker.check(module)

        for diag in checker.diagnostics:
            click.echo(renderer.render(diag), err=True)
            if diag.severity == Severity.ERROR:
                errors += 1

    return errors == 0, checked, errors


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


def _check_file(filepath: Path) -> bool:
    """Lex, parse, and check a single .prv file. Returns True if OK."""
    source = filepath.read_text()
    filename = str(filepath)
    renderer = DiagnosticRenderer(color=True)

    try:
        tokens = Lexer(source, filename).lex()
        module = Parser(tokens, filename).parse()
    except CompileError as e:
        for diag in e.diagnostics:
            click.echo(renderer.render(diag), err=True)
        return False

    checker = Checker()
    checker.check(module)

    had_errors = False
    for diag in checker.diagnostics:
        click.echo(renderer.render(diag), err=True)
        if diag.severity == Severity.ERROR:
            had_errors = True

    return not had_errors


def _check_md_prove_blocks(md_file: Path) -> tuple[int, int]:
    """Check all ```prove blocks in a markdown file.

    Returns (checked_blocks, error_count).
    """
    import re

    text = md_file.read_text()
    fence_re = re.compile(r"```prove\s*\n(.*?)```", re.DOTALL)
    renderer = DiagnosticRenderer(color=True)
    blocks = 0
    errors = 0

    for match in fence_re.finditer(text):
        code = match.group(1)
        block_line = text[:match.start()].count("\n") + 2
        filename = f"{md_file}:{block_line}"
        blocks += 1

        try:
            tokens = Lexer(code, filename).lex()
            module = Parser(tokens, filename).parse()
        except CompileError as e:
            for diag in e.diagnostics:
                click.echo(renderer.render(diag), err=True)
                errors += 1
            continue

        checker = Checker()
        checker.check(module)
        for diag in checker.diagnostics:
            click.echo(renderer.render(diag), err=True)
            if diag.severity == Severity.ERROR:
                errors += 1

    return blocks, errors


@main.command()
@click.argument("path", default=".", type=click.Path(exists=True))
@click.option("--md", is_flag=True, help="Also check ```prove blocks in .md files.")
def check(path: str, md: bool) -> None:
    """Type-check a Prove project or a single .prv file."""
    target = Path(path)

    if target.is_file() and target.suffix == ".prv":
        click.echo(f"checking {target.name}...")
        ok = _check_file(target)
        if ok:
            click.echo(f"checked {target.name} — no errors")
        else:
            raise SystemExit(1)
        return

    if target.is_file() and target.suffix == ".md":
        click.echo(f"checking {target.name}...")
        blocks, errors = _check_md_prove_blocks(target)
        if errors:
            click.echo(f"checked {target.name} — {blocks} block(s), {errors} error(s)")
            raise SystemExit(1)
        else:
            click.echo(f"checked {target.name} — {blocks} block(s), no errors")
        return

    try:
        config_path = find_config(target)
        config = load_config(config_path)
        click.echo(f"checking {config.package.name}...")
        project_dir = config_path.parent
        ok, checked, errors = _compile_project(project_dir)

        md_blocks = 0
        md_errors = 0
        if md and target.is_dir():
            for md_file in sorted(target.rglob("*.md")):
                b, e = _check_md_prove_blocks(md_file)
                md_blocks += b
                md_errors += e
            errors += md_errors

        parts = [f"{checked} file(s) checked"]
        if md_blocks:
            parts.append(f"{md_blocks} md block(s)")
        if errors:
            parts.append(f"{errors} error(s)")
        if ok and md_errors == 0:
            click.echo(f"checked {config.package.name} — {', '.join(parts)}, no errors")
        else:
            click.echo(f"checked {config.package.name} — {', '.join(parts)}")
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


def _format_source(source: str, filename: str) -> str | None:
    """Parse and format Prove source. Returns None on parse failure."""
    try:
        tokens = Lexer(source, filename).lex()
        module = Parser(tokens, filename).parse()
    except (CompileError, Exception):
        return None
    from prove.formatter import ProveFormatter

    return ProveFormatter().format(module)


def _format_md_prove_blocks(text: str) -> str:
    """Format all ```prove fenced code blocks in markdown text."""
    import re

    def _replace_block(match: re.Match[str]) -> str:
        opener = match.group(1)
        code = match.group(2)
        closer = match.group(3)
        formatted = _format_source(code, "<md-block>")
        if formatted is None:
            return match.group(0)
        return opener + formatted + closer

    return re.sub(r"(```prove\s*\n)(.*?)(```)", _replace_block, text, flags=re.DOTALL)


def _format_excerpt(filename: str, original: str, formatted: str) -> str:
    """Return a short excerpt showing the first formatting difference."""
    orig_lines = original.splitlines()
    fmt_lines = formatted.splitlines()
    # Find first differing line
    first_diff = 0
    for i, (a, b) in enumerate(zip(orig_lines, fmt_lines)):
        if a != b:
            first_diff = i
            break
    else:
        # Lengths differ — difference starts after the shorter one
        first_diff = min(len(orig_lines), len(fmt_lines))

    context = 2
    start = max(0, first_diff - context)
    end = min(len(orig_lines), first_diff + context + 1)

    lines: list[str] = []
    lines.append(f"  --> {filename}:{first_diff + 1}")
    lines.append("  got:")
    for i in range(start, end):
        marker = ">" if i == first_diff else " "
        lines.append(f"  {marker} {i + 1:4d} | {orig_lines[i]}")
    # Show what it should be
    end_fmt = min(len(fmt_lines), first_diff + context + 1)
    start_fmt = max(0, first_diff - context)
    lines.append("  expected:")
    for i in range(start_fmt, end_fmt):
        marker = ">" if i == first_diff else " "
        lines.append(f"  {marker} {i + 1:4d} | {fmt_lines[i]}")
    return "\n".join(lines)


@main.command(name="format")
@click.argument("path", default=".", type=click.Path(exists=True))
@click.option("--check", is_flag=True, help="Check formatting without modifying files.")
@click.option("--stdin", "use_stdin", is_flag=True, help="Read from stdin, write to stdout.")
@click.option("--md", is_flag=True, help="Also format ```prove blocks in .md files.")
def format_cmd(path: str, check: bool, use_stdin: bool, md: bool) -> None:
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

    # --- .prv files ---
    prv_files = sorted(target.rglob("*.prv")) if target.is_dir() else [target]

    changed = 0
    checked = 0
    skipped = 0
    for prv_file in prv_files:
        source = prv_file.read_text()
        filename = str(prv_file)
        try:
            tokens = Lexer(source, filename).lex()
            module = Parser(tokens, filename).parse()
        except CompileError as e:
            skipped += 1
            renderer = DiagnosticRenderer(color=True)
            for diag in e.diagnostics:
                click.echo(renderer.render(diag), err=True)
            continue

        checked += 1
        formatted = formatter.format(module)
        if formatted != source:
            changed += 1
            if check:
                click.echo(f"would reformat {filename}")
            else:
                prv_file.write_text(formatted)
                click.echo(f"formatted {filename}")

    # --- .md files (only with --md) ---
    if md and target.is_dir():
        for md_file in sorted(target.rglob("*.md")):
            original = md_file.read_text()
            result = _format_md_prove_blocks(original)
            checked += 1
            if result != original:
                changed += 1
                filename = str(md_file)
                if check:
                    click.echo(f"would reformat {filename}")
                else:
                    md_file.write_text(result)
                    click.echo(f"formatted {filename}")

    # --- summary ---
    parts = [f"{checked} file(s) checked"]
    if skipped:
        parts.append(f"{skipped} skipped (parse errors)")
    if changed:
        verb = "would reformat" if check else "reformatted"
        click.echo(f"{changed} file(s) {verb}, {', '.join(parts)}.")
    else:
        click.echo(f"{', '.join(parts)}, all already formatted.")

    if check and changed:
        raise SystemExit(1)


@main.command()
@click.argument("path", default=".", type=click.Path(exists=True))
@click.option("--md", is_flag=True, help="Also lint ```prove blocks in .md files.")
def lint(path: str, md: bool) -> None:
    """Check formatting and report mismatches with excerpts."""
    from prove.formatter import ProveFormatter

    formatter = ProveFormatter()
    target = Path(path)

    prv_files = sorted(target.rglob("*.prv")) if target.is_dir() else [target]

    issues = 0
    checked = 0
    skipped = 0
    for prv_file in prv_files:
        source = prv_file.read_text()
        filename = str(prv_file)
        try:
            tokens = Lexer(source, filename).lex()
            module = Parser(tokens, filename).parse()
        except CompileError as e:
            skipped += 1
            renderer = DiagnosticRenderer(color=True)
            for diag in e.diagnostics:
                click.echo(renderer.render(diag), err=True)
            continue

        checked += 1
        formatted = formatter.format(module)
        if formatted != source:
            issues += 1
            click.echo(f"lint: {filename}")
            click.echo(_format_excerpt(filename, source, formatted))
            click.echo()

    if md and target.is_dir():
        import re

        fence_re = re.compile(r"(```prove\s*\n)(.*?)(```)", re.DOTALL)
        for md_file in sorted(target.rglob("*.md")):
            original = md_file.read_text()
            checked += 1
            for match in fence_re.finditer(original):
                code = match.group(2)
                fmt = _format_source(code, "<md-block>")
                if fmt is not None and fmt != code:
                    issues += 1
                    # Line number of the block in the .md file
                    block_line = original[:match.start()].count("\n") + 2
                    click.echo(f"lint: {md_file}:{block_line} (prove block)")
                    click.echo(
                        _format_excerpt(str(md_file), code, fmt)
                    )
                    click.echo()

    # --- summary ---
    parts = [f"{checked} file(s) checked"]
    if skipped:
        parts.append(f"{skipped} skipped (parse errors)")
    if issues:
        click.echo(f"{issues} formatting issue(s), {', '.join(parts)}.")
        raise SystemExit(1)
    else:
        click.echo(f"{', '.join(parts)}, all clean.")


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
        fields = node.__dataclass_fields__
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
