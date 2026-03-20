"""Check command logic — click-free.

Called by both the click CLI (cli.py) and the proof binary (via PyRun_SimpleString).
Keep this file free of click imports so it remains embeddable.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from prove.ast_nodes import Module


def _collect_verification_stats(module: Module) -> dict[str, int]:
    """Collect verification statistics from a module."""
    from prove.ast_nodes import FunctionDef, MainDef

    stats = {"ensures_count": 0, "near_miss_count": 0, "trusted_count": 0}
    for decl in module.declarations:
        if isinstance(decl, FunctionDef):
            if decl.ensures:
                stats["ensures_count"] += 1
            if decl.near_misses:
                stats["near_miss_count"] += 1
            if decl.trusted is not None:
                stats["trusted_count"] += 1
        elif isinstance(decl, MainDef):
            pass
    return stats


def _format_excerpt(filename: str, original: str, formatted: str) -> str:
    """Return a short excerpt showing the first formatting difference."""
    orig_lines = original.splitlines()
    fmt_lines = formatted.splitlines()
    first_diff = 0
    for i, (a, b) in enumerate(zip(orig_lines, fmt_lines)):
        if a != b:
            first_diff = i
            break
    else:
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
    end_fmt = min(len(fmt_lines), first_diff + context + 1)
    start_fmt = max(0, first_diff - context)
    lines.append("  expected:")
    for i in range(start_fmt, end_fmt):
        marker = ">" if i == first_diff else " "
        lines.append(f"  {marker} {i + 1:4d} | {fmt_lines[i]}")
    return "\n".join(lines)


def _check_file(filepath: Path, *, coherence: bool = True) -> tuple[int, int, int]:
    """Lex, parse, and check a single .prv file. Returns (errors, warnings, format_issues)."""
    from prove.checker import Checker
    from prove.config import discover_prv_files
    from prove.errors import CompileError, DiagnosticRenderer, Severity
    from prove.formatter import ProveFormatter
    from prove.lexer import Lexer
    from prove.parser import Parser

    source = filepath.read_text()
    filename = str(filepath)
    renderer = DiagnosticRenderer(color=True)

    try:
        tokens = Lexer(source, filename).lex()
        module = Parser(tokens, filename).parse()
    except CompileError as e:
        for diag in e.diagnostics:
            sys.stderr.write(renderer.render(diag) + "\n")
        return len(e.diagnostics), 0, 0

    # Discover sibling modules (including subdirectories) for cross-file imports
    local_modules = None
    project_dir = None
    try:
        from prove.config import find_config

        config_path = find_config(filepath)
        project_dir = config_path.parent
        src_dir = project_dir / "src"
        if not src_dir.is_dir():
            src_dir = project_dir
        prv_files = discover_prv_files(src_dir)
        if len(prv_files) > 1:
            from prove.module_resolver import build_module_registry

            local_modules = build_module_registry(prv_files)
    except FileNotFoundError:
        # No prove.toml found — try immediate parent for siblings
        prv_files = discover_prv_files(filepath.parent)
        if len(prv_files) > 1:
            from prove.module_resolver import build_module_registry

            local_modules = build_module_registry(prv_files)

    checker = Checker(local_modules=local_modules, project_dir=project_dir)
    checker._coherence = coherence
    symbols = checker.check(module)

    errors = 0
    warnings = 0
    for diag in checker.diagnostics:
        sys.stderr.write(renderer.render(diag) + "\n")
        if diag.severity == Severity.ERROR:
            errors += 1
        elif diag.severity == Severity.WARNING:
            warnings += 1

    formatter = ProveFormatter(symbols=symbols, diagnostics=checker.diagnostics)
    formatted = formatter.format(module)
    format_issues = 0
    if formatted != source:
        format_issues = 1
        sys.stderr.write(f"format: {filename}\n")
        sys.stderr.write(_format_excerpt(filename, source, formatted) + "\n")

    return errors, warnings, format_issues


def _check_md_prove_blocks(md_file: Path) -> tuple[int, int, int]:
    """Check all ```prove blocks in a markdown file. Returns (blocks, errors, warnings)."""
    import re

    from prove.checker import Checker
    from prove.errors import CompileError, DiagnosticRenderer, Severity
    from prove.lexer import Lexer
    from prove.parser import Parser

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
                sys.stderr.write(renderer.render(diag) + "\n")
                errors += 1
            continue

        checker = Checker()
        checker.check(module)
        for diag in checker.diagnostics:
            sys.stderr.write(renderer.render(diag) + "\n")
            if diag.severity == Severity.ERROR:
                errors += 1
            elif diag.severity == Severity.WARNING:
                warnings += 1

    return blocks, errors, warnings


def _compile_project(
    project_path: Path,
    *,
    coherence: bool = False,
) -> tuple[bool, int, int, int, int, dict]:
    """Lex, parse, and check all .prv files.

    Returns (ok, checked, errors, warnings, format_issues, stats).
    """
    from prove.checker import Checker
    from prove.config import discover_prv_files
    from prove.errors import CompileError, DiagnosticRenderer, Severity
    from prove.formatter import ProveFormatter
    from prove.lexer import Lexer
    from prove.parser import Parser

    src_dir = project_path / "src"
    if not src_dir.is_dir():
        src_dir = project_path

    prv_files = discover_prv_files(src_dir)
    if not prv_files:
        sys.stderr.write("warning: no .prv files found\n")
        return True, 0, 0, 0, 0, {"ensures_count": 0, "near_miss_count": 0, "trusted_count": 0}

    from prove.module_resolver import build_module_registry

    local_modules = build_module_registry(prv_files) if len(prv_files) > 1 else None

    renderer = DiagnosticRenderer(color=True)
    checked = 0
    errors = 0
    warnings = 0
    format_issues = 0
    total_stats: dict[str, int] = {"ensures_count": 0, "near_miss_count": 0, "trusted_count": 0}

    for prv_file in prv_files:
        source = prv_file.read_text()
        filename = str(prv_file)

        try:
            tokens = Lexer(source, filename).lex()
            module = Parser(tokens, filename).parse()
        except CompileError as e:
            errors += 1
            for diag in e.diagnostics:
                sys.stderr.write(renderer.render(diag) + "\n")
            continue

        checked += 1
        checker = Checker(local_modules=local_modules, project_dir=project_path)
        checker._coherence = coherence
        symbols = checker.check(module)

        module_stats = _collect_verification_stats(module)
        for key in total_stats:
            total_stats[key] += module_stats[key]

        for diag in checker.diagnostics:
            sys.stderr.write(renderer.render(diag) + "\n")
            if diag.severity == Severity.ERROR:
                errors += 1
            elif diag.severity == Severity.WARNING:
                warnings += 1

        formatter = ProveFormatter(symbols=symbols, diagnostics=checker.diagnostics)
        formatted = formatter.format(module)
        if formatted != source:
            format_issues += 1
            sys.stderr.write(f"format: {filename}\n")
            sys.stderr.write(_format_excerpt(filename, source, formatted) + "\n")

    return errors == 0, checked, errors, warnings, format_issues, total_stats


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


def _print_verification_stats(stats: dict) -> None:
    """Print verification statistics after check."""
    ensures = stats.get("ensures_count", 0)
    near_miss = stats.get("near_miss_count", 0)
    trusted = stats.get("trusted_count", 0)
    if ensures == 0 and near_miss == 0 and trusted == 0:
        return
    print("")
    print("Verification:")
    if ensures > 0:
        print(f"  \u2713 {ensures} functions with ensures (property tests)")
    if near_miss > 0:
        print(f"  \u2713 {near_miss} validators with near_miss (boundary tests)")
    if trusted > 0:
        print(f"  \u26a0 {trusted} functions trusted")


def _print_nlp_status() -> None:
    """Print NLP backend and PDAT store availability."""
    from prove.nlp import has_spacy, has_wordnet
    from prove.nlp_store import _data_path

    print("NLP status:")
    print(f"  spaCy:   {'available' if has_spacy() else 'not available'}")
    print(f"  WordNet: {'available' if has_wordnet() else 'not available'}")
    print("  Stores:")
    for name in ["verb_synonyms.dat", "synonym_cache.dat"]:
        p = _data_path(name)
        print(f"    {name}: {'found' if p.is_file() else 'missing'}")

    cwd = Path.cwd()
    prove_dir = cwd / ".prove"
    if prove_dir.is_dir():
        for name in ["stdlib_index.dat", "similarity_matrix.dat", "semantic_features.dat"]:
            p = prove_dir / name
            print(f"    .prove/{name}: {'found' if p.is_file() else 'missing'}")
    else:
        print("    .prove/ directory: not found")


def _print_refutation_challenges(project_dir: Path) -> None:
    """Generate and display refutation challenges from ensures contracts."""
    from prove.ast_nodes import FunctionDef
    from prove.config import discover_prv_files
    from prove.errors import CompileError
    from prove.lexer import Lexer
    from prove.mutator import Mutator
    from prove.parser import Parser

    src_dir = project_dir / "src"
    if not src_dir.is_dir():
        src_dir = project_dir

    prv_files = discover_prv_files(src_dir)
    total_challenges = 0
    addressed = 0

    for prv_file in prv_files:
        try:
            source = prv_file.read_text()
            tokens = Lexer(source, str(prv_file)).lex()
            module = Parser(tokens, str(prv_file)).parse()
        except CompileError:
            continue

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
                continue

            print(
                f"\n  {decl.verb} {decl.name} — "
                f"{fn_challenges} challenges, {fn_addressed} addressed:"
            )
            for i, mutant in enumerate(result.mutants):
                marker = "+" if i < fn_addressed else "-"
                print(f"    [{marker}] {mutant.description}")

    if total_challenges > 0:
        print(f"\nrefutation: {addressed}/{total_challenges} challenges addressed")
    else:
        print("\nrefutation: no functions with ensures contracts found")


def _check_intent_coverage(project_dir: Path) -> None:
    """Check project.intent declarations against implemented code."""
    from prove.intent_generator import check_intent_coverage
    from prove.intent_parser import parse_intent

    intent_path = project_dir / "project.intent"
    if not intent_path.exists():
        print("  no project.intent found — skipping intent check")
        return

    source = intent_path.read_text(encoding="utf-8")
    result = parse_intent(source, str(intent_path))
    if result.project is None:
        sys.stderr.write("  error parsing project.intent\n")
        return

    src_dir = project_dir / "src"
    source_dir = src_dir if src_dir.is_dir() else project_dir
    statuses = check_intent_coverage(result.project, source_dir)
    print("\nIntent coverage:")
    for s in statuses:
        icon = {"implemented": "+", "todo": "~", "missing": "-"}.get(s["status"], "?")
        print(f"  [{icon}] {s['module']}.{s['noun']} — {s['status']}")
    impl = sum(1 for s in statuses if s["status"] == "implemented")
    print(f"  {impl}/{len(statuses)} declarations implemented")


def _print_completeness_status(project_dir: Path) -> None:
    """Print per-module completeness showing todo counts."""
    from prove.ast_nodes import FunctionDef, ModuleDecl, TodoStmt
    from prove.config import discover_prv_files
    from prove.lexer import Lexer
    from prove.parser import Parser

    src_dir = project_dir / "src"
    if not src_dir.is_dir():
        src_dir = project_dir

    prv_files = discover_prv_files(src_dir)
    if not prv_files:
        return

    print("\nCompleteness:")
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

        todo_fns = [fn for fn in fns if any(isinstance(s, TodoStmt) for s in fn.body)]
        done = len(fns) - len(todo_fns)
        total = len(fns)
        pct = 100 * done // total if total else 0
        print(f"  Module {mod_name}: {done}/{total} functions complete ({pct}%)")
        for fn in fns:
            has_todo = any(isinstance(s, TodoStmt) for s in fn.body)
            marker = "[todo]" if has_todo else "[complete]"
            print(f"    - {fn.verb} {fn.name}     {marker}")


def run_check(
    path: str = ".",
    *,
    md: bool = False,
    strict: bool = False,
    no_coherence: bool = False,
    no_challenges: bool = False,
    no_status: bool = False,
    no_intent: bool = False,
    nlp_status: bool = False,
) -> int:
    """Type-check, lint, and verify a Prove project or single file. Returns 0 on success."""
    from prove.config import find_config, load_config

    if nlp_status:
        _print_nlp_status()
        return 0

    target = Path(path)

    if target.is_file() and target.suffix == ".prv":
        print(f"checking {target.name}...")
        errors, warnings, fmt = _check_file(target, coherence=not no_coherence)
        if strict:
            errors += warnings
            warnings = 0
        print(_check_summary(target.name, 1, errors, warnings, fmt))
        return 1 if errors else 0

    if target.is_file() and target.suffix == ".md":
        print(f"checking {target.name}...")
        blocks, errors, warnings = _check_md_prove_blocks(target)
        if strict:
            errors += warnings
            warnings = 0
        print(_check_summary(target.name, 1, errors, warnings, 0, md_blocks=blocks))
        return 1 if errors else 0

    try:
        config_path = find_config(target)
        config = load_config(config_path)
        print(f"checking {config.package.name}...")
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

        print(
            _check_summary(
                config.package.name, checked, errors, warnings, format_issues, md_blocks=md_blocks
            )
        )
        _print_verification_stats(stats)

        if not no_status:
            _print_completeness_status(project_dir)

        if not no_intent:
            _check_intent_coverage(project_dir)

        return 1 if errors else 0

    except FileNotFoundError:
        sys.stderr.write("error: no prove.toml found\n")
        return 1
