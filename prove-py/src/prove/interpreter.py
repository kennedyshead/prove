"""Compile-time interpreter for evaluating comptime blocks."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from prove.ast_nodes import (
    Assignment,
    BinaryExpr,
    BooleanLit,
    CallExpr,
    CharLit,
    CommentStmt,
    ComptimeExpr,
    DecimalLit,
    Expr,
    ExprStmt,
    IdentifierExpr,
    IntegerLit,
    ListLiteral,
    MatchExpr,
    PathLit,
    Stmt,
    StringInterp,
    StringLit,
    TailContinue,
    TailLoop,
    TripleStringLit,
    UnaryExpr,
    VarDecl,
)
from prove.errors import CompileError, Diagnostic, Severity


@dataclass
class ComptimeResult:
    value: object
    dependencies: set[Path] = field(default_factory=set)


class ComptimeInterpreter:
    def __init__(self, module_source_dir: Path | None = None) -> None:
        self._module_source_dir = module_source_dir or Path(".")
        self._vars: dict[str, object] = {}
        self._dependencies: set[Path] = set()

    def evaluate(self, expr: ComptimeExpr) -> ComptimeResult:
        result: object = None
        for stmt in expr.body:
            result = self._eval_stmt(stmt)
        return ComptimeResult(value=result, dependencies=self._dependencies)

    def _eval_stmt(self, stmt: Stmt) -> object:
        if isinstance(stmt, VarDecl):
            value = self._eval_expr(stmt.value)
            self._vars[stmt.name] = value
            return value
        if isinstance(stmt, Assignment):
            value = self._eval_expr(stmt.value)
            self._vars[stmt.target] = value
            return value
        if isinstance(stmt, ExprStmt):
            return self._eval_expr(stmt.expr)
        if isinstance(stmt, CommentStmt):
            return None
        if isinstance(stmt, (TailLoop, TailContinue)):
            raise CompileError(
                [
                    Diagnostic(
                        severity=Severity.ERROR,
                        code="E410",
                        message="tail recursion not supported in comptime blocks",
                        labels=[],
                    )
                ]
            )
        return None

    def _eval_expr(self, expr: Expr) -> object:
        if isinstance(expr, IntegerLit):
            return int(expr.value)
        if isinstance(expr, DecimalLit):
            return float(expr.value)
        if isinstance(expr, BooleanLit):
            return expr.value
        if isinstance(expr, StringLit):
            return expr.value
        if isinstance(expr, CharLit):
            return expr.value
        if isinstance(expr, TripleStringLit):
            return expr.value
        if isinstance(expr, PathLit):
            return expr.value
        if isinstance(expr, StringInterp):
            return self._eval_string_interp(expr)
        if isinstance(expr, BinaryExpr):
            return self._eval_binary(expr)
        if isinstance(expr, UnaryExpr):
            return self._eval_unary(expr)
        if isinstance(expr, ListLiteral):
            return [self._eval_expr(e) for e in expr.elements]
        if isinstance(expr, MatchExpr):
            return self._eval_match(expr)
        if isinstance(expr, ComptimeExpr):
            result: object = None
            for stmt in expr.body:
                result = self._eval_stmt(stmt)
            return result
        if isinstance(expr, IdentifierExpr):
            if expr.name in self._vars:
                return self._vars[expr.name]
            raise CompileError(
                [
                    Diagnostic(
                        severity=Severity.ERROR,
                        code="E418",
                        message=f"undefined variable '{expr.name}' in comptime",
                        labels=[],
                    )
                ]
            )
        if isinstance(expr, CallExpr):
            return self._eval_call(expr)
        raise CompileError(
            [
                Diagnostic(
                    severity=Severity.ERROR,
                    code="E411",
                    message=f"unsupported expression type in comptime: {type(expr).__name__}",
                    labels=[],
                )
            ]
        )

    def _eval_call(self, expr: CallExpr) -> object:
        func_name: str
        if isinstance(expr.func, IdentifierExpr):
            func_name = expr.func.name
        else:
            raise CompileError(
                [
                    Diagnostic(
                        severity=Severity.ERROR,
                        code="E419",
                        message="only simple function calls supported in comptime",
                        labels=[],
                    )
                ]
            )

        args = [self._eval_expr(a) for a in expr.args]

        if func_name == "read":
            if len(args) != 1 or not isinstance(args[0], str):
                raise CompileError(
                    [
                        Diagnostic(
                            severity=Severity.ERROR,
                            code="E420",
                            message="read() expects a single string argument",
                            labels=[],
                        )
                    ]
                )
            file_path = self._module_source_dir / args[0]
            self._dependencies.add(file_path.absolute())
            if not file_path.exists():
                raise CompileError(
                    [
                        Diagnostic(
                            severity=Severity.ERROR,
                            code="E421",
                            message=f"file not found: {args[0]}",
                            labels=[],
                        )
                    ]
                )
            return file_path.read_text()

        raise CompileError(
            [
                Diagnostic(
                    severity=Severity.ERROR,
                    code="E422",
                    message=f"unknown function '{func_name}' in comptime "
                    f"(only 'read' is supported)",
                    labels=[],
                )
            ]
        )

    def _eval_string_interp(self, expr: StringInterp) -> str:
        parts: list[str] = []
        for part in expr.parts:
            if isinstance(part, StringLit):
                parts.append(part.value)
            else:
                val = self._eval_expr(part)
                parts.append(str(val))
        return "".join(parts)

    def _eval_binary(self, expr: BinaryExpr) -> object:
        left = self._eval_expr(expr.left)
        right = self._eval_expr(expr.right)
        op = expr.op

        if op == "+":
            if isinstance(left, str) or isinstance(right, str):
                return str(left) + str(right)
            return left + right
        if op == "-":
            return left - right
        if op == "*":
            return left * right
        if op == "/":
            return left / right
        if op == "%":
            return left % right
        if op == "==":
            return left == right
        if op == "!=":
            return left != right
        if op == "<":
            return left < right
        if op == "<=":
            return left <= right
        if op == ">":
            return left > right
        if op == ">=":
            return left >= right
        if op == "and":
            return left and right
        if op == "or":
            return left or right
        if op == "++":
            if isinstance(left, list) and isinstance(right, list):
                return left + right
            if isinstance(left, str) and isinstance(right, str):
                return left + right
            raise CompileError(
                [
                    Diagnostic(
                        severity=Severity.ERROR,
                        code="E412",
                        message="++ operator requires both operands to be lists or strings",
                        labels=[],
                    )
                ]
            )
        raise CompileError(
            [
                Diagnostic(
                    severity=Severity.ERROR,
                    code="E413",
                    message=f"unsupported binary operator in comptime: {op}",
                    labels=[],
                )
            ]
        )

    def _eval_unary(self, expr: UnaryExpr) -> object:
        operand = self._eval_expr(expr.operand)
        op = expr.op
        if op == "not":
            return not operand
        if op == "-":
            return -operand
        if op == "+":
            return +operand
        raise CompileError(
            [
                Diagnostic(
                    severity=Severity.ERROR,
                    code="E414",
                    message=f"unsupported unary operator in comptime: {op}",
                    labels=[],
                )
            ]
        )

    def _eval_match(self, expr: MatchExpr) -> object:
        if expr.subject is None:
            raise CompileError(
                [
                    Diagnostic(
                        severity=Severity.ERROR,
                        code="E415",
                        message="implicit match not supported in comptime",
                        labels=[],
                    )
                ]
            )

        subj = self._eval_expr(expr.subject)

        for arm in expr.arms:
            if self._match_pattern(arm.pattern, subj):
                return self._eval_arm_body(arm.body)
        raise CompileError(
            [
                Diagnostic(
                    severity=Severity.ERROR,
                    code="E416",
                    message="non-exhaustive match in comptime",
                    labels=[],
                )
            ]
        )

    def _match_pattern(self, pattern, value: object) -> bool:
        from prove.ast_nodes import BindingPattern, LiteralPattern, VariantPattern, WildcardPattern

        if isinstance(pattern, WildcardPattern):
            return True
        if isinstance(pattern, BindingPattern):
            self._vars[pattern.name] = value
            return True
        if isinstance(pattern, LiteralPattern):
            if pattern.kind == "integer":
                return int(pattern.value) == value
            if pattern.kind == "decimal":
                return float(pattern.value) == value
            if pattern.kind == "string":
                return pattern.value == value
            if pattern.kind == "boolean":
                return (pattern.value == "true") == value
        if isinstance(pattern, VariantPattern):
            if not hasattr(value, "variant") or not hasattr(value, "name"):
                return False
            return pattern.name == value.name
        return False

    def _eval_arm_body(self, body: list) -> object:
        result: object = None
        for stmt in body:
            result = self._eval_stmt(stmt)
        return result
