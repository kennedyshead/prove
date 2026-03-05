"""Prove compiler CLI."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import click

from prove import __version__
from prove.checker import Checker
from prove.config import find_config, load_config
from prove.errors import CompileError, DiagnosticRenderer, Severity
from prove.lexer import Lexer
from prove.parser import Parser
from prove.project import scaffold

if TYPE_CHECKING:
    from prove.symbols import SymbolTable


def _compile_project(
    project_path: Path,
) -> tuple[bool, int, int, int, int]:
    """Lex, parse, and check all .prv files under src/.

    Returns (ok, checked, errors, warnings, format_issues) tuple.
    """
    from prove.formatter import ProveFormatter

    src_dir = project_path / "src"
    if not src_dir.is_dir():
        src_dir = project_path  # fallback to project root

    prv_files = sorted(src_dir.rglob("*.prv"))
    if not prv_files:
        click.echo("warning: no .prv files found", err=True)
        return True, 0, 0, 0, 0

    # Build local module registry for cross-file imports
    from prove.module_resolver import build_module_registry

    local_modules = build_module_registry(prv_files) if len(prv_files) > 1 else None

    renderer = DiagnosticRenderer(color=True)
    checked = 0
    errors = 0
    warnings = 0
    format_issues = 0

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
        checker = Checker(local_modules=local_modules)
        symbols = checker.check(module)

        for diag in checker.diagnostics:
            click.echo(renderer.render(diag), err=True)
            if diag.severity == Severity.ERROR:
                errors += 1
            elif diag.severity == Severity.WARNING:
                warnings += 1

        formatter = ProveFormatter(symbols=symbols)
        formatted = formatter.format(module)
        if formatted != source:
            format_issues += 1
            click.echo(f"format: {filename}", err=True)
            click.echo(_format_excerpt(filename, source, formatted), err=True)

    return errors == 0, checked, errors, warnings, format_issues


@click.group()
@click.version_option(__version__, prog_name="prove")
def main() -> None:
    """The Prove programming language compiler."""


@main.command()
@click.argument("path", default=".", type=click.Path(exists=True))
@click.option("--mutate", is_flag=True, help="Enable mutation testing.")
@click.option("--debug", is_flag=True, help="Compile with debug symbols (-g) and no optimization.")
def build(path: str, mutate: bool, debug: bool) -> None:
    """Compile a Prove project."""
    from prove.builder import build_project

    try:
        config_path = find_config(Path(path))
        config = load_config(config_path)
        click.echo(f"building {config.package.name}...")
        project_dir = config_path.parent

        renderer = DiagnosticRenderer(color=True)
        result = build_project(project_dir, config, debug=debug)

        for diag in result.diagnostics:
            click.echo(renderer.render(diag), err=True)

        if not result.ok:
            if result.c_error:
                click.echo(f"error: {result.c_error}", err=True)
            raise SystemExit(1)

        if mutate:
            click.echo("running mutation testing...")
            from prove.module_resolver import build_module_registry
            from prove.mutator import run_mutation_tests

            src_dir = project_dir / "src"
            if not src_dir.is_dir():
                src_dir = project_dir
            prv_files = sorted(src_dir.rglob("*.prv"))

            local_modules = build_module_registry(prv_files) if len(prv_files) > 1 else None
            modules = []
            for prv_file in prv_files:
                source = prv_file.read_text()
                filename = str(prv_file)
                try:
                    tokens = Lexer(source, filename).lex()
                    module = Parser(tokens, filename).parse()
                    checker = Checker(local_modules=local_modules)
                    symbols = checker.check(module)
                    if not checker.has_errors():
                        modules.append((module, symbols))
                except CompileError:
                    continue

            mutation_result = run_mutation_tests(
                project_dir,
                modules,
                max_mutants=50,
                property_rounds=100,
            )

            if mutation_result.total_mutants == 0:
                click.echo("no mutants generated")
            else:
                click.echo(
                    f"mutation score: {mutation_result.mutation_score:.1%} "
                    f"({mutation_result.killed_mutants}/{mutation_result.total_mutants} killed)"
                )
                if mutation_result.survivors:
                    click.echo(f"\nsurviving mutants ({len(mutation_result.survivors)}):")
                    for s in mutation_result.survivors:
                        click.echo(f"  {s['id']}: {s['description']} at {s['location']}")
                        click.echo("    suggestion: add contract to kill this mutant")

        click.echo(f"built {config.package.name} -> {result.binary}")
    except FileNotFoundError:
        click.echo("error: no prove.toml found", err=True)
        raise SystemExit(1)


def _check_file(filepath: Path) -> tuple[int, int, int]:
    """Lex, parse, and check a single .prv file.

    Returns (errors, warnings, format_issues) tuple.
    """
    from prove.formatter import ProveFormatter

    source = filepath.read_text()
    filename = str(filepath)
    renderer = DiagnosticRenderer(color=True)

    try:
        tokens = Lexer(source, filename).lex()
        module = Parser(tokens, filename).parse()
    except CompileError as e:
        for diag in e.diagnostics:
            click.echo(renderer.render(diag), err=True)
        return len(e.diagnostics), 0, 0

    checker = Checker()
    symbols = checker.check(module)

    errors = 0
    warnings = 0
    for diag in checker.diagnostics:
        click.echo(renderer.render(diag), err=True)
        if diag.severity == Severity.ERROR:
            errors += 1
        elif diag.severity == Severity.WARNING:
            warnings += 1

    formatter = ProveFormatter(symbols=symbols)
    formatted = formatter.format(module)
    format_issues = 0
    if formatted != source:
        format_issues = 1
        click.echo(f"format: {filename}", err=True)
        click.echo(_format_excerpt(filename, source, formatted), err=True)

    return errors, warnings, format_issues


def _check_md_prove_blocks(md_file: Path) -> tuple[int, int, int]:
    """Check all ```prove blocks in a markdown file.

    Returns (checked_blocks, error_count, warning_count).
    """
    import re

    text = md_file.read_text()
    fence_re = re.compile(r"```prove\s*\n(.*?)```", re.DOTALL)
    renderer = DiagnosticRenderer(color=True)
    blocks = 0
    errors = 0
    warnings = 0

    for match in fence_re.finditer(text):
        code = match.group(1)
        block_line = text[: match.start()].count("\n") + 2
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
            elif diag.severity == Severity.WARNING:
                warnings += 1

    return blocks, errors, warnings


def _check_summary(
    name: str, files: int, errors: int, warnings: int, format_issues: int, md_blocks: int = 0
) -> str:
    """Build a unified check summary line."""
    parts = [f"{files} file(s)"]
    if md_blocks:
        parts[0] += f", {md_blocks} md block(s)"

    counts: list[str] = []
    if errors:
        counts.append(f"{errors} error(s)")
    if warnings:
        counts.append(f"{warnings} warning(s)")
    if format_issues:
        counts.append(f"{format_issues} formatting issue(s)")

    if counts:
        return f"checked {name} — {', '.join(parts)}, {', '.join(counts)}"
    return f"checked {name} — {', '.join(parts)}, no issues"


@main.command()
@click.argument("path", default=".", type=click.Path(exists=True))
@click.option("--md", is_flag=True, help="Also check ```prove blocks in .md files.")
@click.option("--strict", is_flag=True, help="Treat warnings as errors.")
def check(path: str, md: bool, strict: bool) -> None:
    """Type-check and lint a Prove project or a single .prv file."""
    target = Path(path)

    if target.is_file() and target.suffix == ".prv":
        click.echo(f"checking {target.name}...")
        errors, warnings, fmt = _check_file(target)
        if strict:
            errors += warnings
            warnings = 0
        click.echo(_check_summary(target.name, 1, errors, warnings, fmt))
        if errors:
            raise SystemExit(1)
        return

    if target.is_file() and target.suffix == ".md":
        click.echo(f"checking {target.name}...")
        blocks, errors, warnings = _check_md_prove_blocks(target)
        if strict:
            errors += warnings
            warnings = 0
        click.echo(_check_summary(target.name, 1, errors, warnings, 0, md_blocks=blocks))
        if errors:
            raise SystemExit(1)
        return

    try:
        config_path = find_config(target)
        config = load_config(config_path)
        click.echo(f"checking {config.package.name}...")
        project_dir = config_path.parent
        ok, checked, errors, warnings, format_issues = _compile_project(
            project_dir,
        )

        md_blocks = 0
        md_errors = 0
        md_warnings = 0
        if md and target.is_dir():
            for md_file in sorted(target.rglob("*.md")):
                b, e, w = _check_md_prove_blocks(md_file)
                md_blocks += b
                md_errors += e
                md_warnings += w
            errors += md_errors
            warnings += md_warnings

        if strict:
            errors += warnings
            warnings = 0

        click.echo(
            _check_summary(
                config.package.name, checked, errors, warnings, format_issues, md_blocks=md_blocks
            )
        )
        if errors:
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

        # Build local module registry for cross-file imports
        from prove.module_resolver import build_module_registry

        local_modules = build_module_registry(prv_files) if len(prv_files) > 1 else None

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

            checker = Checker(local_modules=local_modules)
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
            project_dir,
            modules,
            property_rounds=rounds,
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
                f"tested {config.package.name} — {result.tests_failed} FAILED",
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

    symbols = _try_check(source, filename)
    return ProveFormatter(symbols=symbols).format(module)


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


def _try_check(
    source: str,
    filename: str,
    local_modules: dict | None = None,
) -> tuple[SymbolTable | None, list]:
    """Run checker on source, returning symbols and diagnostics.

    Returns the symbol table even when the checker finds errors, because
    function signatures (registered in pass 1) are still useful for type
    inference.  Returns (None, []) only if parsing fails.
    """
    try:
        tokens = Lexer(source, filename).lex()
        module = Parser(tokens, filename).parse()
    except (CompileError, Exception):
        return None, []

    checker = Checker(local_modules=local_modules)
    checker.check(module)
    return checker.symbols, checker.diagnostics


@main.command(name="format")
@click.argument("path", default=".", type=click.Path(exists=True))
@click.option("--check", is_flag=True, help="Check formatting without modifying files.")
@click.option("--stdin", "use_stdin", is_flag=True, help="Read from stdin, write to stdout.")
@click.option("--md", is_flag=True, help="Also format ```prove blocks in .md files.")
def format_cmd(path: str, check: bool, use_stdin: bool, md: bool) -> None:
    """Format Prove source files."""
    import sys

    from prove.formatter import ProveFormatter

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
        symbols, diagnostics = _try_check(source, "<stdin>")
        formatter = ProveFormatter(symbols=symbols, diagnostics=diagnostics)
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

    # Build local module registry for cross-file type inference
    local_modules: dict | None = None
    if target.is_dir() and len(prv_files) > 1:
        from prove.module_resolver import build_module_registry

        local_modules = build_module_registry(prv_files)

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
        symbols, diagnostics = _try_check(source, filename, local_modules=local_modules)
        formatter = ProveFormatter(symbols=symbols, diagnostics=diagnostics)
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
