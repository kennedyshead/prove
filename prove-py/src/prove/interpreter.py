"""Compile-time interpreter for evaluating comptime blocks."""

from __future__ import annotations

import sys
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
    FloatLit,
    FunctionDef,
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
    def __init__(
        self,
        module_source_dir: Path | None = None,
        function_defs: dict[str, "FunctionDef"] | None = None,
    ) -> None:
        self._module_source_dir = module_source_dir or Path(".")
        self._vars: dict[str, object] = {}
        self._dependencies: set[Path] = set()
        self._function_defs = function_defs or {}

    def evaluate(self, expr: ComptimeExpr) -> ComptimeResult:
        result: object = None
        for stmt in expr.body:
            result = self._eval_stmt(stmt)
        return ComptimeResult(value=result, dependencies=self._dependencies)

    def evaluate_pure_call(self, func_name: str, args: list[object], verb: str) -> object | None:
        """Evaluate a pure function call with constant arguments."""
        if func_name not in self._function_defs:
            return None
        fd = self._function_defs[func_name]
        if fd.verb not in {"transforms", "validates", "reads", "creates", "matches"}:
            return None
        if len(fd.params) != len(args):
            return None
        eval_interpreter = ComptimeInterpreter(
            module_source_dir=self._module_source_dir,
            function_defs=self._function_defs,
        )
        for param, arg in zip(fd.params, args):
            eval_interpreter._vars[param.name] = arg
        try:
            result: object = None
            for stmt in fd.body:
                result = eval_interpreter._eval_stmt(stmt)
            return result
        except CompileError:
            return None

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
        if isinstance(stmt, MatchExpr):
            return self._eval_match(stmt)
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
        if isinstance(expr, FloatLit):
            return float(expr.value[:-1])  # Strip 'f' suffix
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

        # Built-in comptime functions
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

        if func_name == "platform":
            if args:
                raise CompileError(
                    [
                        Diagnostic(
                            severity=Severity.ERROR,
                            code="E420",
                            message="platform() takes no arguments",
                            labels=[],
                        )
                    ]
                )
            plat = sys.platform
            if plat.startswith("linux"):
                return "linux"
            if plat == "darwin":
                return "macos"
            if plat == "win32":
                return "windows"
            return plat

        if func_name == "len":
            if len(args) != 1:
                raise CompileError(
                    [
                        Diagnostic(
                            severity=Severity.ERROR,
                            code="E420",
                            message="len() expects a single argument",
                            labels=[],
                        )
                    ]
                )
            val = args[0]
            if isinstance(val, (str, list)):
                return len(val)
            raise CompileError(
                [
                    Diagnostic(
                        severity=Severity.ERROR,
                        code="E420",
                        message="len() requires a string or list argument",
                        labels=[],
                    )
                ]
            )

        if func_name == "contains":
            if len(args) != 2:
                raise CompileError(
                    [
                        Diagnostic(
                            severity=Severity.ERROR,
                            code="E420",
                            message="contains() expects two arguments",
                            labels=[],
                        )
                    ]
                )
            if isinstance(args[0], str) and isinstance(args[1], str):
                return args[1] in args[0]
            if isinstance(args[0], list):
                return args[1] in args[0]
            return False

        if func_name == "to_upper":
            if len(args) == 1 and isinstance(args[0], str):
                return args[0].upper()

        if func_name == "to_lower":
            if len(args) == 1 and isinstance(args[0], str):
                return args[0].lower()

        # Try user-defined pure function call
        result = self.evaluate_pure_call(func_name, args, "transforms")
        if result is not None:
            return result

        raise CompileError(
            [
                Diagnostic(
                    severity=Severity.ERROR,
                    code="E422",
                    message=f"unknown function '{func_name}' in comptime",
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
            return (left) + (right)  # type: ignore[operator]
        if op == "-":
            return (left) - (right)  # type: ignore[operator]
        if op == "*":
            return (left) * (right)  # type: ignore[operator]
        if op == "/":
            return (left) / (right)  # type: ignore[operator]
        if op == "%":
            return (left) % (right)  # type: ignore[operator]
        if op == "==":
            return left == right
        if op == "!=":
            return left != right
        if op == "<":
            return (left) < (right)  # type: ignore[operator]
        if op == "<=":
            return (left) <= (right)  # type: ignore[operator]
        if op == ">":
            return (left) > (right)  # type: ignore[operator]
        if op == ">=":
            return (left) >= (right)  # type: ignore[operator]
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
            return -(operand)  # type: ignore[operator]
        if op == "+":
            return +(operand)  # type: ignore[operator]
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

    def _match_pattern(self, pattern: object, value: object) -> bool:
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
        if isinstance(pattern, VariantPattern) and hasattr(value, "name"):
            return pattern.name == (value.name if hasattr(value, "name") else None)
        return False

    def _eval_arm_body(self, body: list[object]) -> object:
        result: object = None
        for stmt in body:
            result = self._eval_stmt(stmt)
        return result
