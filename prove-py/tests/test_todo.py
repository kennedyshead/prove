"""Tests for TodoStmt — parsing, checking, formatting, and emitter."""

from __future__ import annotations

from prove.ast_nodes import FunctionDef, TodoStmt
from prove.checker import Checker
from prove.lexer import Lexer
from prove.parser import Parser
from tests.helpers import check_info


class TestTodoParsing:
    def test_bare_todo(self) -> None:
        tokens = Lexer(
            "transforms stub(x Integer) Integer\nfrom\n    todo\n", "<test>"
        ).lex()
        module = Parser(tokens, "<test>").parse()
        fd = module.declarations[0]
        assert isinstance(fd, FunctionDef)
        assert len(fd.body) == 1
        assert isinstance(fd.body[0], TodoStmt)
        assert fd.body[0].message is None

    def test_todo_with_message(self) -> None:
        tokens = Lexer(
            'transforms stub(x Integer) Integer\nfrom\n    todo "implement this"\n',
            "<test>",
        ).lex()
        module = Parser(tokens, "<test>").parse()
        fd = module.declarations[0]
        assert isinstance(fd, FunctionDef)
        assert isinstance(fd.body[0], TodoStmt)
        assert fd.body[0].message == "implement this"

    def test_todo_among_other_stmts(self) -> None:
        tokens = Lexer(
            "transforms stub(x Integer) Integer\n"
            "from\n"
            "    y as Integer = x + 1\n"
            "    todo\n"
            "    y\n",
            "<test>",
        ).lex()
        module = Parser(tokens, "<test>").parse()
        fd = module.declarations[0]
        assert isinstance(fd, FunctionDef)
        assert any(isinstance(s, TodoStmt) for s in fd.body)


class TestTodoChecker:
    def test_i601_emitted(self) -> None:
        check_info(
            "transforms stub(x Integer) Integer\n"
            "from\n"
            "    todo\n",
            "I601",
        )

    def test_no_i601_without_todo(self) -> None:
        tokens = Lexer(
            "transforms add(a Integer, b Integer) Integer\n"
            "from\n"
            "    a + b\n",
            "<test>",
        ).lex()
        module = Parser(tokens, "<test>").parse()
        checker = Checker()
        checker.check(module)
        assert not any(d.code == "I601" for d in checker.diagnostics)


class TestTodoFormatter:
    def test_bare_todo_roundtrip(self) -> None:
        source = "transforms stub(x Integer) Integer\nfrom\n  todo\n"
        tokens = Lexer(source, "<test>").lex()
        module = Parser(tokens, "<test>").parse()
        from prove.formatter import ProveFormatter

        formatted = ProveFormatter().format(module)
        assert "todo" in formatted

    def test_todo_with_message_roundtrip(self) -> None:
        source = 'transforms stub(x Integer) Integer\nfrom\n  todo "do it"\n'
        tokens = Lexer(source, "<test>").lex()
        module = Parser(tokens, "<test>").parse()
        from prove.formatter import ProveFormatter

        formatted = ProveFormatter().format(module)
        assert 'todo "do it"' in formatted
