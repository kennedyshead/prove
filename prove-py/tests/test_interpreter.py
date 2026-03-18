"""Tests for the comptime interpreter."""

import sys

import pytest

from prove.ast_nodes import (
    BinaryExpr,
    BooleanLit,
    CallExpr,
    ComptimeExpr,
    ExprStmt,
    IdentifierExpr,
    IntegerLit,
    ListLiteral,
    LiteralPattern,
    MatchArm,
    MatchExpr,
    SimpleType,
    StringLit,
    UnaryExpr,
    VarDecl,
    WildcardPattern,
)
from prove.errors import CompileError
from prove.interpreter import ComptimeInterpreter
from prove.source import Span

S = Span("test", 0, 0, 0, 0)


def _make_comptime(stmts):
    return ComptimeExpr(stmts, S)


class TestComptimeInterpreter:
    def test_integer_literal(self):
        expr = _make_comptime([ExprStmt(IntegerLit("42", S), S)])
        result = ComptimeInterpreter().evaluate(expr)
        assert result.value == 42

    def test_string_literal(self):
        expr = _make_comptime([ExprStmt(StringLit("hello", S), S)])
        result = ComptimeInterpreter().evaluate(expr)
        assert result.value == "hello"

    def test_boolean_literal(self):
        expr = _make_comptime([ExprStmt(BooleanLit(True, S), S)])
        result = ComptimeInterpreter().evaluate(expr)
        assert result.value is True

    def test_binary_addition(self):
        expr = _make_comptime(
            [ExprStmt(BinaryExpr(IntegerLit("10", S), "+", IntegerLit("20", S), S), S)]
        )
        result = ComptimeInterpreter().evaluate(expr)
        assert result.value == 30

    def test_binary_multiplication(self):
        expr = _make_comptime(
            [ExprStmt(BinaryExpr(IntegerLit("512", S), "*", IntegerLit("2", S), S), S)]
        )
        result = ComptimeInterpreter().evaluate(expr)
        assert result.value == 1024

    def test_unary_negation(self):
        expr = _make_comptime([ExprStmt(UnaryExpr("-", IntegerLit("5", S), S), S)])
        result = ComptimeInterpreter().evaluate(expr)
        assert result.value == -5

    def test_unary_not(self):
        expr = _make_comptime([ExprStmt(UnaryExpr("not", BooleanLit(True, S), S), S)])
        result = ComptimeInterpreter().evaluate(expr)
        assert result.value is False

    def test_variable_declaration(self):
        expr = _make_comptime(
            [
                VarDecl("x", SimpleType("Integer", S), IntegerLit("10", S), S),
                ExprStmt(BinaryExpr(IdentifierExpr("x", S), "+", IntegerLit("5", S), S), S),
            ]
        )
        result = ComptimeInterpreter().evaluate(expr)
        assert result.value == 15

    def test_list_literal(self):
        expr = _make_comptime(
            [
                ExprStmt(
                    ListLiteral([IntegerLit("1", S), IntegerLit("2", S), IntegerLit("3", S)], S),
                    S,
                )
            ]
        )
        result = ComptimeInterpreter().evaluate(expr)
        assert result.value == [1, 2, 3]

    def test_comparison_operators(self):
        expr = _make_comptime(
            [ExprStmt(BinaryExpr(IntegerLit("5", S), ">", IntegerLit("3", S), S), S)]
        )
        result = ComptimeInterpreter().evaluate(expr)
        assert result.value is True

    def test_string_concat(self):
        expr = _make_comptime(
            [ExprStmt(BinaryExpr(StringLit("hello", S), "+", StringLit(" world", S), S), S)]
        )
        result = ComptimeInterpreter().evaluate(expr)
        assert result.value == "hello world"

    def test_platform_returns_string(self):
        expr = _make_comptime([ExprStmt(CallExpr(IdentifierExpr("platform", S), [], S), S)])
        result = ComptimeInterpreter().evaluate(expr)
        assert isinstance(result.value, str)
        assert result.value in ("linux", "macos", "windows") or isinstance(result.value, str)

    def test_platform_matches_sys(self):
        expr = _make_comptime([ExprStmt(CallExpr(IdentifierExpr("platform", S), [], S), S)])
        result = ComptimeInterpreter().evaluate(expr)
        if sys.platform.startswith("linux"):
            assert result.value == "linux"
        elif sys.platform == "darwin":
            assert result.value == "macos"
        elif sys.platform == "win32":
            assert result.value == "windows"

    def test_len_string(self):
        expr = _make_comptime(
            [
                ExprStmt(
                    CallExpr(
                        IdentifierExpr("len", S),
                        [StringLit("hello", S)],
                        S,
                    ),
                    S,
                )
            ]
        )
        result = ComptimeInterpreter().evaluate(expr)
        assert result.value == 5

    def test_len_list(self):
        expr = _make_comptime(
            [
                ExprStmt(
                    CallExpr(
                        IdentifierExpr("len", S),
                        [ListLiteral([IntegerLit("1", S), IntegerLit("2", S)], S)],
                        S,
                    ),
                    S,
                )
            ]
        )
        result = ComptimeInterpreter().evaluate(expr)
        assert result.value == 2

    def test_contains_string(self):
        expr = _make_comptime(
            [
                ExprStmt(
                    CallExpr(
                        IdentifierExpr("contains", S),
                        [StringLit("hello world", S), StringLit("world", S)],
                        S,
                    ),
                    S,
                )
            ]
        )
        result = ComptimeInterpreter().evaluate(expr)
        assert result.value is True

    def test_match_with_wildcard(self):
        expr = _make_comptime(
            [
                ExprStmt(
                    MatchExpr(
                        IntegerLit("42", S),
                        [
                            MatchArm(
                                LiteralPattern("1", S, "integer"),
                                [ExprStmt(StringLit("one", S), S)],
                                S,
                            ),  # noqa: E501
                            MatchArm(WildcardPattern(S), [ExprStmt(StringLit("other", S), S)], S),
                        ],
                        S,
                    ),
                    S,
                )
            ]
        )
        result = ComptimeInterpreter().evaluate(expr)
        assert result.value == "other"

    def test_match_exact(self):
        expr = _make_comptime(
            [
                ExprStmt(
                    MatchExpr(
                        StringLit("linux", S),
                        [
                            MatchArm(
                                LiteralPattern("linux", S, "string"),
                                [ExprStmt(IntegerLit("4096", S), S)],
                                S,
                            ),
                            MatchArm(WildcardPattern(S), [ExprStmt(IntegerLit("1024", S), S)], S),
                        ],
                        S,
                    ),
                    S,
                )
            ]
        )
        result = ComptimeInterpreter().evaluate(expr)
        assert result.value == 4096

    def test_read_file(self, tmp_path):
        test_file = tmp_path / "data.txt"
        test_file.write_text("file content")

        expr = _make_comptime(
            [
                ExprStmt(
                    CallExpr(
                        IdentifierExpr("read", S),
                        [StringLit("data.txt", S)],
                        S,
                    ),
                    S,
                )
            ]
        )
        interp = ComptimeInterpreter(module_source_dir=tmp_path)
        result = interp.evaluate(expr)
        assert result.value == "file content"
        assert (tmp_path / "data.txt").absolute() in result.dependencies

    def test_read_file_not_found(self, tmp_path):
        expr = _make_comptime(
            [
                ExprStmt(
                    CallExpr(
                        IdentifierExpr("read", S),
                        [StringLit("nonexistent.txt", S)],
                        S,
                    ),
                    S,
                )
            ]
        )
        interp = ComptimeInterpreter(module_source_dir=tmp_path)
        with pytest.raises(CompileError):
            interp.evaluate(expr)

    def test_unknown_function(self):
        expr = _make_comptime([ExprStmt(CallExpr(IdentifierExpr("nonexistent", S), [], S), S)])
        with pytest.raises(CompileError):
            ComptimeInterpreter().evaluate(expr)

    def test_undefined_variable(self):
        expr = _make_comptime([ExprStmt(IdentifierExpr("undefined_var", S), S)])
        with pytest.raises(CompileError):
            ComptimeInterpreter().evaluate(expr)

    def test_dependencies_tracked(self, tmp_path):
        test_file = tmp_path / "config.json"
        test_file.write_text("{}")

        expr = _make_comptime(
            [
                ExprStmt(
                    CallExpr(
                        IdentifierExpr("read", S),
                        [StringLit("config.json", S)],
                        S,
                    ),
                    S,
                )
            ]
        )
        interp = ComptimeInterpreter(module_source_dir=tmp_path)
        result = interp.evaluate(expr)
        assert len(result.dependencies) == 1
        assert test_file.absolute() in result.dependencies
