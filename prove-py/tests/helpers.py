"""Shared test helpers for the Prove compiler test suite."""

from __future__ import annotations

from prove.ast_nodes import Module
from prove.checker import Checker
from prove.errors import Diagnostic
from prove.lexer import Lexer
from prove.parser import Parser
from prove.symbols import SymbolTable


def parse_check(source: str) -> tuple[Module, SymbolTable]:
    """Parse and check source, return (module, symbols)."""
    tokens = Lexer(source, "<test>").lex()
    module = Parser(tokens, "<test>").parse()
    checker = Checker()
    symbols = checker.check(module)
    assert not checker.has_errors(), [d.message for d in checker.diagnostics]
    return module, symbols


def check(source: str) -> SymbolTable:
    """Parse and check source, asserting no errors. Returns symbol table."""
    tokens = Lexer(source, "<test>").lex()
    module = Parser(tokens, "<test>").parse()
    checker = Checker()
    st = checker.check(module)
    errors = [d for d in checker.diagnostics if d.severity.value == "error"]
    assert not errors, f"Unexpected errors: {[f'{d.code}: {d.message}' for d in errors]}"
    return st


def check_fails(source: str, error_code: str) -> list[Diagnostic]:
    """Parse and check source, asserting the given error code appears."""
    tokens = Lexer(source, "<test>").lex()
    module = Parser(tokens, "<test>").parse()
    checker = Checker()
    checker.check(module)
    matching = [d for d in checker.diagnostics if d.code == error_code]
    assert matching, (
        f"Expected error {error_code} but got: "
        f"{[f'{d.code}: {d.message}' for d in checker.diagnostics] or 'no diagnostics'}"
    )
    return matching


def check_warns(source: str, warning_code: str) -> list[Diagnostic]:
    """Parse and check source, asserting the given warning code appears."""
    tokens = Lexer(source, "<test>").lex()
    module = Parser(tokens, "<test>").parse()
    checker = Checker()
    checker.check(module)
    matching = [d for d in checker.diagnostics if d.code == warning_code]
    assert matching, (
        f"Expected warning {warning_code} but got: "
        f"{[f'{d.code}: {d.message}' for d in checker.diagnostics] or 'no diagnostics'}"
    )
    return matching


def check_info(source: str, info_code: str) -> list[Diagnostic]:
    """Parse and check source, asserting the given info-level diagnostic appears."""
    tokens = Lexer(source, "<test>").lex()
    module = Parser(tokens, "<test>").parse()
    checker = Checker()
    checker.check(module)
    matching = [d for d in checker.diagnostics if d.code == info_code]
    assert matching, (
        f"Expected info {info_code} but got: "
        f"{[f'{d.code}: {d.message}' for d in checker.diagnostics] or 'no diagnostics'}"
    )
    return matching


def check_all(source: str) -> list[Diagnostic]:
    """Parse and check source, return all diagnostics."""
    tokens = Lexer(source, "<test>").lex()
    module = Parser(tokens, "<test>").parse()
    checker = Checker()
    checker.check(module)
    return list(checker.diagnostics)


def check_coherence_warns(source: str, warning_code: str) -> list[Diagnostic]:
    """Parse and check source with coherence enabled, asserting the given warning appears."""
    tokens = Lexer(source, "<test>").lex()
    module = Parser(tokens, "<test>").parse()
    checker = Checker()
    checker._coherence = True
    checker.check(module)
    matching = [d for d in checker.diagnostics if d.code == warning_code]
    assert matching, (
        f"Expected coherence warning {warning_code} but got: "
        f"{[f'{d.code}: {d.message}' for d in checker.diagnostics] or 'no diagnostics'}"
    )
    return matching


def check_coherence_ok(source: str) -> None:
    """Parse and check source with coherence enabled, asserting no errors."""
    tokens = Lexer(source, "<test>").lex()
    module = Parser(tokens, "<test>").parse()
    checker = Checker()
    checker._coherence = True
    checker.check(module)
    errors = [d for d in checker.diagnostics if d.severity.value == "error"]
    assert not errors, f"Unexpected errors: {[f'{d.code}: {d.message}' for d in errors]}"


def check_and_format(source: str) -> str:
    """Parse, check, and format with diagnostics for auto-fixes."""
    from prove.formatter import ProveFormatter

    tokens = Lexer(source, "<test>").lex()
    module = Parser(tokens, "<test>").parse()
    checker = Checker()
    checker.check(module)
    return ProveFormatter(
        symbols=checker.symbols, diagnostics=checker.diagnostics,
    ).format(module)
