"""Format command logic — click-free.

Called by both the click CLI (cli.py) and the proof binary (via PyRun_SimpleString).
Keep this file free of click imports so it remains embeddable.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from prove.errors import Diagnostic
    from prove.symbols import SymbolTable


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
    from prove.errors import CompileError
    from prove.lexer import Lexer
    from prove.parser import Parser

    try:
        tokens = Lexer(source, filename).lex()
        module = Parser(tokens, filename).parse()
    except CompileError:
        return None, []

    checker = Checker(local_modules=local_modules)
    checker.check(module)
    return checker.symbols, checker.diagnostics


def _format_source(source: str, filename: str) -> str | None:
    """Parse and format Prove source. Returns None on parse failure."""
    from prove.errors import CompileError
    from prove.formatter import ProveFormatter
    from prove.lexer import Lexer
    from prove.parser import Parser

    try:
        tokens = Lexer(source, filename).lex()
        module = Parser(tokens, filename).parse()
    except CompileError:
        return None

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


def run_format(
    path: str = ".", *, status: bool = False, use_stdin: bool = False, md: bool = False
) -> int:
    """Format Prove source files. Returns 0 on success, 1 if --status finds unformatted files."""
    from prove.config import discover_prv_files
    from prove.errors import CompileError, DiagnosticRenderer
    from prove.formatter import ProveFormatter
    from prove.lexer import Lexer
    from prove.parser import Parser

    if use_stdin:
        source = sys.stdin.read()
        try:
            tokens = Lexer(source, "<stdin>").lex()
            module = Parser(tokens, "<stdin>").parse()
        except CompileError as e:
            renderer = DiagnosticRenderer(color=True)
            for diag in e.diagnostics:
                sys.stderr.write(renderer.render(diag) + "\n")
            return 1
        symbols, diagnostics = _try_check(source, "<stdin>")
        formatter = ProveFormatter(symbols=symbols, diagnostics=diagnostics)
        formatted = formatter.format(module)
        if status:
            return 1 if formatted != source else 0
        sys.stdout.write(formatted)
        return 0

    target = Path(path)
    prv_files = discover_prv_files(target) if target.is_dir() else [target]

    local_modules: dict[str, object] | None = None
    if target.is_dir() and len(prv_files) > 1:
        from prove.module_resolver import build_module_registry

        local_modules = build_module_registry(prv_files)  # type: ignore[assignment]

    changed = 0
    checked = 0
    skipped = 0
    changed_files: list[tuple[Path, str]] = []

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
                sys.stderr.write(renderer.render(diag) + "\n")
            continue

        checked += 1
        symbols, diagnostics = _try_check(source, filename, local_modules=local_modules)
        formatter = ProveFormatter(symbols=symbols, diagnostics=diagnostics)
        formatted = formatter.format(module)
        if formatted != source:
            changed += 1
            if status:
                print(f"would reformat {filename}")
            else:
                prv_file.write_text(formatted)
                changed_files.append((prv_file, formatted))
                print(f"formatted {filename}")

    if md and target.is_dir():
        for md_file in sorted(target.rglob("*.md")):
            original = md_file.read_text()
            result = _format_md_prove_blocks(original)
            checked += 1
            if result != original:
                changed += 1
                filename = str(md_file)
                if status:
                    print(f"would reformat {filename}")
                else:
                    md_file.write_text(result)
                    print(f"formatted {filename}")

    parts = [f"{checked} file(s) checked"]
    if skipped:
        parts.append(f"{skipped} skipped (parse errors)")
    if changed:
        verb = "would reformat" if status else "reformatted"
        print(f"{changed} file(s) {verb}, {', '.join(parts)}.")
    else:
        print(f"{', '.join(parts)}, all already formatted.")

    if changed_files and not status:
        try:
            from prove.lsp import _ProjectIndexer

            root = _ProjectIndexer._find_root(target)
            indexer = _ProjectIndexer(root)
            indexer.index_all_files()
        except Exception:
            pass

    return 1 if (status and changed) else 0
