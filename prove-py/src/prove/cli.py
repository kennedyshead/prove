"""Prove compiler CLI."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import click

from prove import __version__
from prove.config import find_config, load_config
from prove.errors import CompileError, Diagnostic, DiagnosticRenderer, Severity
from prove.lexer import Lexer
from prove.parser import Parser

if TYPE_CHECKING:
    from prove.ast_nodes import Module
    from prove.symbols import SymbolTable


def _collect_verification_stats(module: Module) -> dict[str, int]:
    """Collect verification statistics from a module."""
    from prove.ast_nodes import FunctionDef, MainDef

    stats = {
        "ensures_count": 0,
        "near_miss_count": 0,
        "trusted_count": 0,
    }

    for decl in module.declarations:
        if isinstance(decl, FunctionDef):
            if decl.ensures:
                stats["ensures_count"] += 1
            if decl.near_misses:
                stats["near_miss_count"] += 1
            if decl.trusted is not None:
                stats["trusted_count"] += 1
        elif isinstance(decl, MainDef):
            pass  # MainDef doesn't have ensures/near_miss/trusted

    return stats


def _print_refutation_challenges(project_dir: Path) -> None:
    """Generate and display refutation challenges from ensures contracts."""
    from prove.ast_nodes import FunctionDef
    from prove.mutator import Mutator

    src_dir = project_dir / "src"
    if not src_dir.is_dir():
        src_dir = project_dir

    prv_files = sorted(src_dir.rglob("*.prv"))
    total_challenges = 0
    addressed = 0

    for prv_file in prv_files:
        try:
            source = prv_file.read_text()
            tokens = Lexer(source, str(prv_file)).lex()
            module = Parser(tokens, str(prv_file)).parse()
        except Exception:
            continue

        # Only challenge functions with ensures contracts
        for decl in module.declarations:
            if not isinstance(decl, FunctionDef):
                continue
            if not decl.ensures:
                continue

            mutator = Mutator(module, seed=42)
            result = mutator.generate_mutants(max_mutants=5)
            if not result.mutants:
                continue

            fn_challenges = len(result.mutants)
            fn_addressed = len(decl.why_not)
            total_challenges += fn_challenges
            addressed += min(fn_addressed, fn_challenges)

            if fn_addressed >= fn_challenges:
                continue  # All challenges addressed

            click.echo(f"\n  {decl.verb} {decl.name} — {fn_challenges} challenges, {fn_addressed} addressed:")
            for i, mutant in enumerate(result.mutants):
                marker = "+" if i < fn_addressed else "-"
                click.echo(f"    [{marker}] {mutant.description}")

    if total_challenges > 0:
        click.echo(f"\nrefutation: {addressed}/{total_challenges} challenges addressed")
    else:
        click.echo("\nrefutation: no functions with ensures contracts found")


def _compile_project(
    project_path: Path,
    *,
    coherence: bool = False,
) -> tuple[bool, int, int, int, int, dict]:
    """Lex, parse, and check all .prv files under src/.

    Returns (ok, checked, errors, warnings, format_issues, stats) tuple.
    """
    from prove.checker import Checker
    from prove.formatter import ProveFormatter

    src_dir = project_path / "src"
    if not src_dir.is_dir():
        src_dir = project_path  # fallback to project root

    prv_files = sorted(src_dir.rglob("*.prv"))
    if not prv_files:
        click.echo("warning: no .prv files found", err=True)
        return True, 0, 0, 0, 0, {"ensures_count": 0, "near_miss_count": 0, "trusted_count": 0}

    # Build local module registry for cross-file imports
    from prove.module_resolver import build_module_registry

    local_modules = build_module_registry(prv_files) if len(prv_files) > 1 else None

    renderer = DiagnosticRenderer(color=True)
    checked = 0
    errors = 0
    warnings = 0
    format_issues = 0
    total_stats = {"ensures_count": 0, "near_miss_count": 0, "trusted_count": 0}

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
        checker = Checker(local_modules=local_modules, project_dir=project_path)
        checker._coherence = coherence
        symbols = checker.check(module)

        module_stats = _collect_verification_stats(module)
        for key in total_stats:
            total_stats[key] += module_stats[key]

        for diag in checker.diagnostics:
            click.echo(renderer.render(diag), err=True)
            if diag.severity == Severity.ERROR:
                errors += 1
            elif diag.severity == Severity.WARNING:
                warnings += 1

        formatter = ProveFormatter(symbols=symbols, diagnostics=checker.diagnostics)
        formatted = formatter.format(module)
        if formatted != source:
            format_issues += 1
            click.echo(f"format: {filename}", err=True)
            click.echo(_format_excerpt(filename, source, formatted), err=True)

    return errors == 0, checked, errors, warnings, format_issues, total_stats


def _is_cache_stale(project_dir: Path) -> bool:
    """Check if .prove/ stores need rebuilding."""
    cache_dir = project_dir / ".prove"
    index_file = cache_dir / "stdlib_index.dat"
    if not index_file.exists():
        return True
    index_mtime = index_file.stat().st_mtime
    src_dir = project_dir / "src"
    if not src_dir.is_dir():
        src_dir = project_dir
    for prv in src_dir.rglob("*.prv"):
        if prv.stat().st_mtime > index_mtime:
            return True
    return False


def _update_project_cache(project_dir: Path) -> None:
    """Rebuild .prove_cache and .prove/ stores when stale."""
    if not _is_cache_stale(project_dir):
        return
    try:
        from prove.lsp import _ProjectIndexer

        indexer = _ProjectIndexer(project_dir)
        indexer.index_all_files()
    except Exception:
        pass  # cache update is always non-fatal
    try:
        from prove.nlp_store import build_stdlib_index

        build_stdlib_index(project_dir)
    except Exception:
        pass  # store generation is always non-fatal


@click.group()
@click.version_option(__version__, prog_name="prove")
def main() -> None:
    """The Prove programming language compiler."""


@main.group()
def advanced() -> None:
    """Advanced development and debugging tools."""


@main.command()
@click.argument("path", default=".", type=click.Path(exists=True))
@click.option("--no-mutate", is_flag=True, help="Disable mutation testing.")
@click.option("--debug", is_flag=True, default=None, help="Compile with debug symbols (-g) and no optimization.")
def build(path: str, no_mutate: bool, debug: bool | None) -> None:
    """Compile a Prove project."""
    _warn_no_nlp()
    from prove.builder import build_project

    try:
        config_path = find_config(Path(path))
        config = load_config(config_path)
        click.echo(f"building {config.package.name}...")
        project_dir = config_path.parent

        # CLI flags override config values
        effective_debug = debug if debug is not None else config.build.debug
        effective_mutate = not no_mutate and config.build.mutate

        renderer = DiagnosticRenderer(color=True)
        result = build_project(project_dir, config, debug=effective_debug)

        for diag in result.diagnostics:
            click.echo(renderer.render(diag), err=True)

        if not result.ok:
            if result.c_error:
                click.echo(f"error: {result.c_error}", err=True)
            raise SystemExit(1)

        if effective_mutate:
            click.echo("running mutation testing...")
            from prove.checker import Checker
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

            from prove.mutator import get_survivors_path

            get_survivors_path(project_dir).unlink(missing_ok=True)

            from prove.mutator import save_survivors

            save_survivors(project_dir, mutation_result)

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
        _update_project_cache(project_dir)
    except FileNotFoundError:
        click.echo("error: no prove.toml found", err=True)
        raise SystemExit(1)


def _check_file(filepath: Path, *, coherence: bool = True) -> tuple[int, int, int]:
    """Lex, parse, and check a single .prv file.

    Returns (errors, warnings, format_issues) tuple.
    """
    from prove.checker import Checker
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
    checker._coherence = coherence
    symbols = checker.check(module)

    errors = 0
    warnings = 0
    for diag in checker.diagnostics:
        click.echo(renderer.render(diag), err=True)
        if diag.severity == Severity.ERROR:
            errors += 1
        elif diag.severity == Severity.WARNING:
            warnings += 1

    formatter = ProveFormatter(symbols=symbols, diagnostics=checker.diagnostics)
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

    from prove.checker import Checker

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


def _print_verification_stats(stats: dict) -> None:
    """Print verification statistics after check."""
    ensures = stats.get("ensures_count", 0)
    near_miss = stats.get("near_miss_count", 0)
    trusted = stats.get("trusted_count", 0)

    if ensures == 0 and near_miss == 0 and trusted == 0:
        return

    click.echo("")
    click.echo("Verification:")
    if ensures > 0:
        click.echo(f"  \u2713 {ensures} functions with ensures (property tests)")
    if near_miss > 0:
        click.echo(f"  \u2713 {near_miss} validators with near_miss (boundary tests)")
    if trusted > 0:
        click.echo(f"  \u26a0 {trusted} functions trusted")


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


def _apply_nlp_override(enabled: bool) -> None:
    """Force NLP backend on or off for the current process."""
    import prove.nlp as nlp_mod

    if enabled:
        if not nlp_mod.has_nlp_backend():
            click.echo("error: --nlp requested but no NLP backend available", err=True)
            click.echo("  run: prove setup", err=True)
            raise SystemExit(1)
    else:
        # Disable by marking both backends as checked but unavailable
        nlp_mod._spacy_checked = True
        nlp_mod._spacy_available = False
        nlp_mod._nlp_model = None
        nlp_mod._wordnet_checked = True
        nlp_mod._wordnet_available = False


_nlp_warned = False


def _warn_no_nlp() -> None:
    """Print a one-line info to stderr when NLP is not available (once per process)."""
    global _nlp_warned
    if _nlp_warned:
        return
    _nlp_warned = True
    import prove.nlp as nlp_mod

    if not nlp_mod.has_nlp_backend():
        click.echo("info: NLP not available \u2014 run `prove setup` for improved narrative analysis.", err=True)


def _print_nlp_status() -> None:
    """Print NLP backend and PDAT store availability."""
    from prove.nlp import has_spacy, has_wordnet
    from prove.nlp_store import _data_path

    click.echo("NLP status:")

    # Backends
    spacy_ok = has_spacy()
    wordnet_ok = has_wordnet()
    click.echo(f"  spaCy:   {'available' if spacy_ok else 'not available'}")
    click.echo(f"  WordNet: {'available' if wordnet_ok else 'not available'}")

    # PDAT stores
    click.echo("  Stores:")
    stores = [
        "verb_synonyms.dat",
        "synonym_cache.dat",
    ]
    for name in stores:
        p = _data_path(name)
        exists = p.is_file()
        click.echo(f"    {name}: {'found' if exists else 'missing'}")

    # Project-local stores (check cwd)
    cwd = Path.cwd()
    project_stores = [
        "stdlib_index.dat",
        "similarity_matrix.dat",
        "semantic_features.dat",
    ]
    prove_dir = cwd / ".prove"
    if prove_dir.is_dir():
        for name in project_stores:
            p = prove_dir / name
            exists = p.is_file()
            click.echo(f"    .prove/{name}: {'found' if exists else 'missing'}")
    else:
        click.echo("    .prove/ directory: not found")


@main.command()
@click.argument("path", default=".", type=click.Path(exists=True))
@click.option("--md", is_flag=True, help="Also check ```prove blocks in .md files.")
@click.option("--strict", is_flag=True, help="Treat warnings as errors.")
@click.option("--no-coherence", is_flag=True, help="Skip vocabulary consistency check.")
@click.option("--no-challenges", is_flag=True, help="Skip refutation challenges.")
@click.option("--no-status", is_flag=True, help="Skip module completeness report.")
@click.option("--no-intent", is_flag=True, help="Skip intent coverage check.")
@click.option("--nlp-status", is_flag=True, help="Report NLP backend and store availability.")
def check(path: str, md: bool, strict: bool, no_coherence: bool, no_challenges: bool, no_status: bool, no_intent: bool, nlp_status: bool) -> None:
    """Type-check, lint, and verify a Prove project or a single .prv file."""
    _warn_no_nlp()
    if nlp_status:
        _print_nlp_status()
        return

    target = Path(path)

    if target.is_file() and target.suffix == ".prv":
        click.echo(f"checking {target.name}...")
        errors, warnings, fmt = _check_file(target, coherence=not no_coherence)
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
        ok, checked, errors, warnings, format_issues, stats = _compile_project(
            project_dir,
            coherence=not no_coherence,
        )

        if not no_challenges:
            _print_refutation_challenges(project_dir)

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
        _print_verification_stats(stats)

        if not no_status:
            _print_completeness_status(project_dir)

        if not no_intent:
            _check_intent_coverage(project_dir)

        _update_project_cache(project_dir)
        if errors:
            raise SystemExit(1)
    except FileNotFoundError:
        click.echo("error: no prove.toml found", err=True)
        raise SystemExit(1)


def _check_intent_coverage(project_dir: Path) -> None:
    """Check project.intent declarations against implemented code."""
    from prove.intent_generator import check_intent_coverage
    from prove.intent_parser import parse_intent

    intent_path = project_dir / "project.intent"
    if not intent_path.exists():
        click.echo("  no project.intent found — skipping intent check")
        return

    source = intent_path.read_text(encoding="utf-8")
    result = parse_intent(source, str(intent_path))
    if result.project is None:
        click.echo("  error parsing project.intent", err=True)
        return

    src_dir = project_dir / "src"
    source_dir = src_dir if src_dir.is_dir() else project_dir
    statuses = check_intent_coverage(result.project, source_dir)
    click.echo("\nIntent coverage:")
    for s in statuses:
        icon = {"implemented": "+", "todo": "~", "missing": "-"}.get(s["status"], "?")
        click.echo(f"  [{icon}] {s['module']}.{s['noun']} — {s['status']}")
    impl = sum(1 for s in statuses if s["status"] == "implemented")
    click.echo(f"  {impl}/{len(statuses)} declarations implemented")


def _print_completeness_status(project_dir: Path) -> None:
    """Print per-module completeness showing todo counts."""
    from prove.ast_nodes import FunctionDef, ModuleDecl, TodoStmt

    src_dir = project_dir / "src"
    if not src_dir.is_dir():
        src_dir = project_dir

    prv_files = sorted(src_dir.rglob("*.prv"))
    if not prv_files:
        return

    click.echo("\nCompleteness:")
    for prv_file in prv_files:
        try:
            source = prv_file.read_text()
            tokens = Lexer(source, str(prv_file)).lex()
            module = Parser(tokens, str(prv_file)).parse()
        except Exception:
            continue

        mod_name = prv_file.stem
        for decl in module.declarations:
            if isinstance(decl, ModuleDecl):
                mod_name = decl.name
                break

        fns = [d for d in module.declarations if isinstance(d, FunctionDef)]
        if not fns:
            continue

        todo_fns = []
        complete_fns = []
        for fn in fns:
            if any(isinstance(s, TodoStmt) for s in fn.body):
                todo_fns.append(fn)
            else:
                complete_fns.append(fn)

        total = len(fns)
        done = len(complete_fns)
        pct = 100 * done // total if total else 0
        click.echo(f"  Module {mod_name}: {done}/{total} functions complete ({pct}%)")
        for fn in fns:
            has_todo = any(isinstance(s, TodoStmt) for s in fn.body)
            marker = "[todo]" if has_todo else "[complete]"
            click.echo(f"    - {fn.verb} {fn.name}     {marker}")


@main.command()
@click.argument("path", default=".", type=click.Path(exists=True))
@click.option("--property-rounds", type=int, default=None, help="Override property test rounds.")
def test(path: str, property_rounds: int | None) -> None:
    """Run tests for a Prove project."""
    _warn_no_nlp()
    from prove.checker import Checker
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

        if result.test_details:
            click.echo("\nTested functions:")
            for tc in result.test_details:
                type_labels = {
                    "property": "property-based",
                    "near_miss": "near-miss case",
                    "boundary": "boundary values",
                    "believe": "adversarial",
                }
                type_label = type_labels.get(tc.test_type, tc.test_type)
                verb_display = f"[{tc.verb}] " if tc.verb else ""
                click.echo(f"  • {verb_display}{tc.function_name} ({type_label})")
            click.echo(f"  rounds per test: {rounds}")
            click.echo("")

        if result.ok:
            click.echo(
                f"tested {config.package.name} — "
                f"{result.tests_passed}/{result.tests_run} passed"
            )
        else:
            click.echo(
                f"tested {config.package.name} — "
                f"{result.tests_passed}/{result.tests_run} passed, "
                f"{result.tests_failed} failed",
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
    from prove.project import scaffold

    try:
        project_dir = scaffold(name)
        _update_project_cache(project_dir)
        click.echo(f"created project '{name}' at {project_dir}")
    except FileExistsError as e:
        click.echo(f"error: {e}", err=True)
        raise SystemExit(1)


def _format_source(source: str, filename: str) -> str | None:
    """Parse and format Prove source. Returns None on parse failure."""
    try:
        tokens = Lexer(source, filename).lex()
        module = Parser(tokens, filename).parse()
    except CompileError:
        return None
    from prove.formatter import ProveFormatter

    symbols, diagnostics = _try_check(source, filename)
    return ProveFormatter(symbols=symbols, diagnostics=diagnostics).format(module)


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
    local_modules: dict[str, object] | None = None,
) -> tuple[SymbolTable | None, list[Diagnostic]]:
    """Run checker on source, returning symbols and diagnostics.

    Returns the symbol table even when the checker finds errors, because
    function signatures (registered in pass 1) are still useful for type
    inference.  Returns (None, []) only if parsing fails.
    """
    from prove.checker import Checker

    try:
        tokens = Lexer(source, filename).lex()
        module = Parser(tokens, filename).parse()
    except CompileError:
        return None, []

    checker = Checker(local_modules=local_modules)
    checker.check(module)
    return checker.symbols, checker.diagnostics


@main.command(name="format")
@click.argument("path", default=".", type=click.Path(exists=True))
@click.option("--status", is_flag=True, help="Show formatting status without modifying files.")
@click.option("--stdin", "use_stdin", is_flag=True, help="Read from stdin, write to stdout.")
@click.option("--md", is_flag=True, help="Also format ```prove blocks in .md files.")
def format_cmd(path: str, status: bool, use_stdin: bool, md: bool) -> None:
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
        if status:
            if formatted != source:
                raise SystemExit(1)
        else:
            sys.stdout.write(formatted)
        return

    target = Path(path)

    # --- .prv files ---
    prv_files = sorted(target.rglob("*.prv")) if target.is_dir() else [target]

    # Build local module registry for cross-file type inference
    local_modules: dict[str, object] | None = None
    if target.is_dir() and len(prv_files) > 1:
        from prove.module_resolver import build_module_registry

        local_modules = build_module_registry(prv_files)

    changed = 0
    checked = 0
    skipped = 0
    changed_files: list[tuple[Path, str]] = []  # (path, formatted_source)
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
            if status:
                click.echo(f"would reformat {filename}")
            else:
                prv_file.write_text(formatted)
                changed_files.append((prv_file, formatted))
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
                if status:
                    click.echo(f"would reformat {filename}")
                else:
                    md_file.write_text(result)
                    click.echo(f"formatted {filename}")

    # --- summary ---
    parts = [f"{checked} file(s) checked"]
    if skipped:
        parts.append(f"{skipped} skipped (parse errors)")
    if changed:
        verb = "would reformat" if status else "reformatted"
        click.echo(f"{changed} file(s) {verb}, {', '.join(parts)}.")
    else:
        click.echo(f"{', '.join(parts)}, all already formatted.")

    # Update cache for changed .prv files
    if changed_files and not status:
        try:
            from prove.lsp import _ProjectIndexer

            root = _ProjectIndexer._find_root(target)
            indexer = _ProjectIndexer(root)
            indexer.index_all_files()
        except Exception:
            pass

    if status and changed:
        raise SystemExit(1)


@main.command()
def lsp() -> None:
    """Start the Prove language server."""
    from prove.lsp import main as lsp_main

    lsp_main()


@advanced.command()
@click.argument("path", default=".", type=click.Path(exists=True))
def index(path: str) -> None:
    """Rebuild the .prove_cache ML completion index."""
    from prove.lsp import _ProjectIndexer

    config_path = find_config(Path(path))
    project_dir = config_path.parent
    click.echo("indexing...")
    indexer = _ProjectIndexer(project_dir)
    indexer.index_all_files()
    click.echo(f"indexed {len(indexer._file_ngrams)} files -> {project_dir / '.prove_cache'}")


def _generate_from_intent(target: Path, dry_run: bool) -> None:
    """Generate .prv files from a .intent project file."""
    from prove.intent_generator import generate_project
    from prove.intent_parser import parse_intent

    source = target.read_text(encoding="utf-8")
    result = parse_intent(source, str(target))

    for diag in result.diagnostics:
        severity = diag.severity.upper()
        code = f" {diag.code}" if diag.code else ""
        click.echo(f"{target}:{diag.line}: {severity}{code}: {diag.message}", err=True)

    if result.project is None:
        click.echo("error: failed to parse intent file", err=True)
        raise SystemExit(1)

    generated = generate_project(result.project, target.parent, dry_run=dry_run)
    for filename, src in generated:
        if dry_run:
            click.echo(f"--- {filename} ---")
            click.echo(src)
        else:
            click.echo(f"generated {filename}")


def _generate_from_narrative(target: Path, update: bool, dry_run: bool) -> None:
    """Generate function stubs from module narrative prose in a .prv file."""
    from prove._body_gen import generate_function_source, has_generated_marker
    from prove._generate import generate_stub_function
    from prove._nl_intent import extract_nouns, implied_verbs, pair_verbs_nouns
    from prove.ast_nodes import FunctionDef, ModuleDecl, TodoStmt

    source = target.read_text()
    filename = str(target)

    try:
        tokens = Lexer(source, filename).lex()
        module = Parser(tokens, filename).parse()
    except CompileError as e:
        renderer = DiagnosticRenderer(color=True)
        for diag in e.diagnostics:
            click.echo(renderer.render(diag), err=True)
        raise SystemExit(1)

    # Find narrative
    mod_decl = None
    for decl in module.declarations:
        if isinstance(decl, ModuleDecl):
            mod_decl = decl
            break

    if mod_decl is None or not mod_decl.narrative:
        click.echo("error: file has no module declaration with narrative", err=True)
        raise SystemExit(1)

    # Extract verbs and nouns from narrative
    verbs = implied_verbs(mod_decl.narrative)
    nouns = extract_nouns(mod_decl.narrative)

    if not verbs:
        click.echo("warning: no verbs implied by narrative", err=True)
        return
    if not nouns:
        click.echo("warning: no nouns extracted from narrative", err=True)
        return

    # Generate stubs
    stubs = pair_verbs_nouns(verbs, nouns)

    # Collect existing function names and check for @generated markers
    existing_fns = [d for d in module.declarations if isinstance(d, FunctionDef)]
    if mod_decl:
        existing_fns.extend(d for d in mod_decl.body if isinstance(d, FunctionDef))
    existing_names = {fn.name for fn in existing_fns}

    # On --update: also regenerate @generated functions that still have todos
    updatable_names: set[str] = set()
    if update:
        for fn in existing_fns:
            if has_generated_marker(fn.doc_comment) and any(
                isinstance(s, TodoStmt) for s in fn.body
            ):
                updatable_names.add(fn.name)

    new_stubs = [s for s in stubs if s.name not in existing_names or s.name in updatable_names]

    if not new_stubs:
        click.echo("no new stubs to generate — all verb+noun pairs already have functions")
        return

    # Try body generation for each stub, fall back to simple stub
    generated_lines: list[str] = []
    body_count = 0
    stub_count = 0
    for stub in new_stubs:
        if stub.confidence < 0.3:
            continue
        generated_lines.append("")

        # Attempt body generation using stdlib knowledge base
        result = generate_function_source(
            verb=stub.verb,
            name=stub.name,
            param_names=[p[0] for p in stub.params],
            param_types=[p[1] for p in stub.params],
            return_type=stub.return_type,
            declaration_text=f"{stub.verb} {stub.name}",
        )
        if "todo" not in result.lower() or "chosen:" in result:
            body_count += 1
        else:
            stub_count += 1
        generated_lines.append(result)

    generated_text = "\n".join(generated_lines) + "\n"

    if dry_run:
        click.echo(generated_text)
    else:
        with open(target, "a") as f:
            f.write(generated_text)
        click.echo(f"generated {body_count} body(ies) + {stub_count} stub(s) in {target}")

    # Report completeness
    todo_count = sum(
        1 for fn in existing_fns
        if any(isinstance(s, TodoStmt) for s in fn.body)
    )
    complete = len(existing_fns) - todo_count
    total = len(existing_fns) + len(new_stubs)
    click.echo(f"  {complete}/{total} functions complete ({100 * complete // total if total else 0}%)")


@advanced.command()
@click.argument("path", type=click.Path(exists=True))
@click.option("--update", is_flag=True, help="Regenerate @generated functions with todos.")
@click.option("--dry-run", is_flag=True, help="Preview without writing.")
@click.option("--nlp/--no-nlp", default=None, help="Force NLP backend on/off.")
def generate(path: str, update: bool, dry_run: bool, nlp: bool | None) -> None:
    """Generate function stubs from narrative or intent."""
    _warn_no_nlp()
    if nlp is not None:
        _apply_nlp_override(nlp)

    target = Path(path)
    if target.suffix == ".intent":
        _generate_from_intent(target, dry_run)
    elif target.suffix == ".prv":
        _generate_from_narrative(target, update, dry_run)
    else:
        click.echo("error: expected .prv or .intent file", err=True)
        raise SystemExit(1)


@advanced.command()
@click.argument("path", default="project.intent", type=click.Path(exists=True))
@click.option("--status", is_flag=True, help="Show completeness report.")
@click.option("--drift", is_flag=True, help="Show only mismatches between intent and code.")
@click.option("--generate", "gen", is_flag=True, help="Generate .prv files from intent.")
@click.option("--dry-run", is_flag=True, help="Preview generated files without writing.")
@click.option("--nlp/--no-nlp", default=None, help="Force NLP backend on/off.")
def intent(path: str, status: bool, drift: bool, gen: bool, dry_run: bool, nlp: bool | None) -> None:
    """Work with .intent project declaration files."""
    _warn_no_nlp()
    if nlp is not None:
        _apply_nlp_override(nlp)

    from prove.intent_generator import check_intent_coverage, generate_project
    from prove.intent_parser import parse_intent

    target = Path(path)
    source = target.read_text(encoding="utf-8")
    result = parse_intent(source, str(target))

    # Print parse diagnostics
    for diag in result.diagnostics:
        severity = diag.severity.upper()
        code = f" {diag.code}" if diag.code else ""
        click.echo(f"{target}:{diag.line}: {severity}{code}: {diag.message}", err=True)

    if result.project is None:
        click.echo("error: failed to parse intent file", err=True)
        raise SystemExit(1)

    project = result.project
    project_dir = target.parent
    # Intent file at project root → generate into src/; inside src/ → in-place
    src_dir = project_dir / "src"
    source_dir = src_dir if src_dir.is_dir() else project_dir

    if gen:
        source_dir.mkdir(parents=True, exist_ok=True)
        generated = generate_project(project, source_dir, dry_run=dry_run)
        for filename, src in generated:
            if dry_run:
                click.echo(f"--- {filename} ---")
                click.echo(src)
            else:
                click.echo(f"generated {filename}")
        return

    # Default: show status/drift
    statuses = check_intent_coverage(project, source_dir)

    if drift:
        statuses = [s for s in statuses if s["status"] != "implemented"]

    if not statuses:
        click.echo("all intent declarations have matching implementations")
        return

    for s in statuses:
        icon = {"implemented": "+", "todo": "~", "missing": "-"}.get(s["status"], "?")
        click.echo(f"  [{icon}] {s['module']}.{s['noun']} ({s['verb']}) — {s['status']}")

    # Summary
    impl = sum(1 for s in statuses if s["status"] == "implemented")
    total = len(statuses)
    click.echo(f"\n  {impl}/{total} declarations implemented")


@advanced.command("export")
@click.option(
    "-f",
    "--format",
    "fmt",
    type=click.Choice(["treesitter", "pygments", "chroma"]),
    help="Target format (default: all).",
)
@click.option(
    "--build",
    is_flag=True,
    help="Run build steps after generating.",
)
@click.option(
    "-w",
    "--workspace",
    "workspace_path",
    type=click.Path(exists=True),
    help="Workspace root (default: parent of prove-py).",
)
def export_cmd(fmt: str | None, build: bool, workspace_path: str | None) -> None:
    """Export syntax highlighting data to companion lexer projects."""
    from prove.export import (
        build_chroma,
        build_pygments,
        build_treesitter,
        generate_chroma,
        generate_pygments,
        generate_treesitter,
        read_canonical_lists,
    )

    if workspace_path:
        workspace = Path(workspace_path)
    else:
        # Default: assume prove-py is a sibling directory under workspace
        workspace = Path(__file__).resolve().parent.parent.parent.parent

    lists = read_canonical_lists()
    targets = [fmt] if fmt else ["treesitter", "pygments", "chroma"]

    for target in targets:
        if target == "treesitter":
            click.echo("export: tree-sitter-prove")
            ok = generate_treesitter(lists, workspace)
            if ok and build:
                build_treesitter(workspace)
        elif target == "pygments":
            click.echo("export: pygments-prove")
            ok = generate_pygments(lists, workspace)
            if ok and build:
                build_pygments(workspace)
        elif target == "chroma":
            click.echo("export: chroma-lexer-prove")
            ok = generate_chroma(lists, workspace)
            if ok and build:
                build_chroma(workspace)


@advanced.command()
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


@advanced.command()
@click.argument("file", type=click.Path(exists=True))
@click.option("--load", "mode", flag_value="load", help="Compile .prv lookup to PDAT binary.")
@click.option("--dump", "mode", flag_value="dump", help="Dump PDAT binary to .prv source.")
@click.option("--output", "-o", type=click.Path(), default=None, help="Output path.")
def compiler(file: str, mode: str | None, output: str | None) -> None:
    """Convert between .prv lookup types and PDAT binary format."""
    from prove.store_binary import pdat_to_prv, prv_to_pdat

    if mode is None:
        # Auto-detect from file extension
        if file.endswith(".prv"):
            mode = "load"
        elif file.endswith(".dat") or file.endswith(".bin"):
            mode = "dump"
        else:
            click.echo("Error: specify --load or --dump, or use .prv/.dat extension.", err=True)
            raise SystemExit(1)

    if mode == "load":
        try:
            out = prv_to_pdat(file, output)
        except CompileError as e:
            renderer = DiagnosticRenderer(color=True)
            for diag in e.diagnostics:
                click.echo(renderer.render(diag), err=True)
            raise SystemExit(1)
        except ValueError as e:
            click.echo(f"Error: {e}", err=True)
            raise SystemExit(1)
        click.echo(f"Wrote {out}")
    else:
        try:
            source = pdat_to_prv(file, output)
        except ValueError as e:
            click.echo(f"Error: {e}", err=True)
            raise SystemExit(1)
        if output:
            click.echo(f"Wrote {output}")
        else:
            click.echo(source, nl=False)


@main.command()
def setup() -> None:
    """Set up Prove tools and data stores."""
    import subprocess
    import sys

    errors = 0

    # spaCy model
    click.echo("Downloading spaCy en_core_web_sm model...")
    try:
        result = subprocess.run(
            [sys.executable, "-m", "spacy", "download", "en_core_web_sm",
             "--break-system-packages"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            click.echo("  spaCy model installed.")
        else:
            click.echo(f"  spaCy download failed: {result.stderr.strip()}", err=True)
            errors += 1
    except FileNotFoundError:
        click.echo("  spaCy not installed. Run: pip install 'prove[nlp]'", err=True)
        errors += 1

    # NLTK WordNet data
    click.echo("Downloading NLTK WordNet data...")
    try:
        import nltk  # type: ignore[import-untyped]

        nltk.download("wordnet", quiet=True)
        nltk.download("omw-1.4", quiet=True)
        click.echo("  NLTK data installed.")
    except ImportError:
        click.echo("  NLTK not installed. Run: pip install 'prove[nlp]'", err=True)
        errors += 1
    except Exception as e:
        click.echo(f"  NLTK download failed: {e}", err=True)
        errors += 1

    if errors:
        click.echo(f"\nCompleted with {errors} error(s).", err=True)
        raise SystemExit(1)

    # Build PDAT stores now that NLP deps are available
    click.echo("\nBuilding NLP data stores...")
    try:
        from prove.nlp_store import build_synonym_cache

        build_synonym_cache()
        click.echo("  synonym cache built.")
    except Exception:
        click.echo("  synonym cache skipped.")

    try:
        from prove.nlp_store import build_similarity_matrix

        build_similarity_matrix()
        click.echo("  similarity matrix built.")
    except Exception:
        click.echo("  similarity matrix skipped.")

    try:
        from prove.nlp_store import build_semantic_features

        build_semantic_features()
        click.echo("  semantic features built.")
    except Exception:
        click.echo("  semantic features skipped.")

    click.echo("\nNLP setup complete.")


@advanced.command("setup-nlp", hidden=True)
@click.pass_context
def setup_nlp(ctx: click.Context) -> None:
    """Download NLP models (alias for `prove setup`)."""
    ctx.invoke(setup)


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
