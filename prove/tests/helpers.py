"""Shared test helpers for the Prove compiler test suite."""

from __future__ import annotations

from prove.checker import Checker
from prove.lexer import Lexer
from prove.parser import Parser
from prove.symbols import SymbolTable


def parse_check(source: str) -> tuple:
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


def check_fails(source: str, error_code: str) -> list:
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


def check_warns(source: str, warning_code: str) -> list:
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
