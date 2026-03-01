"""Tests for the AST optimizer."""

from __future__ import annotations

import subprocess
import textwrap

from prove.ast_nodes import (
    BinaryExpr,
    BooleanLit,
    CallExpr,
    ExprStmt,
    FunctionDef,
    IdentifierExpr,
    IntegerLit,
    LiteralPattern,
    MainDef,
    MatchArm,
    MatchExpr,
    Module,
    Param,
    SimpleType,
    TailContinue,
    TailLoop,
    WildcardPattern,
)
from prove.optimizer import Optimizer
from prove.source import Span
from prove.symbols import SymbolTable

_SPAN = Span(file="<test>", start_line=1, start_col=1, end_line=1, end_col=1)


def _make_func(
    name: str,
    verb: str = "transforms",
    params: list[Param] | None = None,
    body: list | None = None,
    terminates=None,
) -> FunctionDef:
    """Helper to build a minimal FunctionDef."""
    return FunctionDef(
        verb=verb,
        name=name,
        params=params or [],
        return_type=SimpleType("Integer", _SPAN),
        can_fail=False,
        ensures=[],
        requires=[],
        proof=None,
        explain=[],
        terminates=terminates,
        trusted=None,
        binary=False,
        why_not=[],
        chosen=None,
        near_misses=[],
        know=[],
        assume=[],
        believe=[],
        intent=None,
        satisfies=[],
        body=body or [],
        doc_comment=None,
        span=_SPAN,
    )


def _make_module(*decls) -> Module:
    return Module(declarations=list(decls), span=_SPAN)


def _make_param(name: str) -> Param:
    return Param(name=name, type_expr=SimpleType("Integer", _SPAN), constraint=None, span=_SPAN)


# ── TCO tests ─────────────────────────────────────────────────────


class TestTCO:
    def test_factorial_rewritten(self):
        """A recursive factorial with `terminates` should be rewritten to TailLoop."""
        # factorial(n, acc) = match n == 0 → acc, _ → factorial(n - 1, acc * n)
        # Simplified: body is a match with two arms
        n = IdentifierExpr("n", _SPAN)
        acc = IdentifierExpr("acc", _SPAN)

        # Base case: acc
        base_arm = MatchArm(
            pattern=LiteralPattern("0", _SPAN),
            body=[ExprStmt(acc, _SPAN)],
            span=_SPAN,
        )

        # Recursive case: factorial(n - 1, acc * n)
        recursive_call = CallExpr(
            func=IdentifierExpr("factorial", _SPAN),
            args=[
                BinaryExpr(n, "-", IntegerLit("1", _SPAN), _SPAN),
                BinaryExpr(acc, "*", n, _SPAN),
            ],
            span=_SPAN,
        )
        rec_arm = MatchArm(
            pattern=WildcardPattern(_SPAN),
            body=[ExprStmt(recursive_call, _SPAN)],
            span=_SPAN,
        )

        match_expr = MatchExpr(subject=n, arms=[base_arm, rec_arm], span=_SPAN)

        fd = _make_func(
            "factorial",
            params=[_make_param("n"), _make_param("acc")],
            body=[match_expr],
            terminates=n,  # has terminates annotation
        )

        module = _make_module(fd)
        symbols = SymbolTable()
        opt = Optimizer(module, symbols)
        result = opt.optimize()

        # The function body should now contain a TailLoop
        new_fd = result.declarations[0]
        assert isinstance(new_fd, FunctionDef)
        assert len(new_fd.body) == 1
        tail_loop = new_fd.body[0]
        assert isinstance(tail_loop, TailLoop)
        assert tail_loop.params == ["n", "acc"]

        # The recursive arm should now be a TailContinue
        # Find the match inside the tail loop
        match_in_loop = tail_loop.body[0]
        assert isinstance(match_in_loop, MatchExpr)
        # Wildcard arm should have TailContinue
        wildcard_arm = match_in_loop.arms[1]
        assert isinstance(wildcard_arm.body[0], TailContinue)

    def test_non_recursive_unchanged(self):
        """A non-recursive function should not be modified by TCO."""
        body = [ExprStmt(IntegerLit("42", _SPAN), _SPAN)]
        fd = _make_func("add", body=body, terminates=IdentifierExpr("n", _SPAN))

        module = _make_module(fd)
        symbols = SymbolTable()
        result = Optimizer(module, symbols).optimize()

        new_fd = result.declarations[0]
        assert isinstance(new_fd, FunctionDef)
        assert len(new_fd.body) == 1
        assert isinstance(new_fd.body[0], ExprStmt)  # unchanged

    def test_no_terminates_unchanged(self):
        """A recursive function without `terminates` should not be optimized."""
        recursive_call = CallExpr(
            func=IdentifierExpr("loop", _SPAN),
            args=[IdentifierExpr("n", _SPAN)],
            span=_SPAN,
        )
        fd = _make_func(
            "loop",
            params=[_make_param("n")],
            body=[ExprStmt(recursive_call, _SPAN)],
            terminates=None,  # no terminates
        )

        module = _make_module(fd)
        symbols = SymbolTable()
        result = Optimizer(module, symbols).optimize()

        new_fd = result.declarations[0]
        assert isinstance(new_fd, FunctionDef)
        assert not any(isinstance(s, TailLoop) for s in new_fd.body)


class TestTCOIntegration:
    """Integration test: compile and run a TCO-optimized program."""

    def test_tco_deep_recursion(self, tmp_path, needs_cc):
        """Compile a tail-recursive factorial, run factorial(100000) without segfault."""
        from prove.builder import build_project
        from prove.config import BuildConfig, PackageConfig, ProveConfig

        # Create a project with a tail-recursive function
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (tmp_path / "prove.toml").write_text(textwrap.dedent("""\
            [package]
            name = "tco_test"
            [build]
            optimize = true
        """))
        (src_dir / "main.prv").write_text(
            "module TcoTest\n"
            '  narrative: """TCO test"""\n'
            "  InputOutput outputs console\n"
            "transforms count(n Integer, acc Integer) Integer\n"
            "  terminates: n\n"
            "from\n"
            "    match n\n"
            "        0 => acc\n"
            "        _ => count(n - 1, acc + 1)\n"
            "\n"
            "main()\n"
            "from\n"
            "    console(to_string(count(100000, 0)))\n"
        )

        config = ProveConfig(
            package=PackageConfig(name="tco_test"),
            build=BuildConfig(optimize=True),
        )
        result = build_project(tmp_path, config)
        assert result.ok, f"Build failed: {result.c_error or result.diagnostics}"
        assert result.binary is not None

        proc = subprocess.run(
            [str(result.binary)],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert proc.returncode == 0
        assert "100000" in proc.stdout

    def test_factorial_c_has_while(self, tmp_path, needs_cc):
        """Verify the C output contains 'while (1)' for a TCO'd function."""
        from prove.c_emitter import CEmitter
        from prove.checker import Checker
        from prove.lexer import Lexer
        from prove.optimizer import Optimizer
        from prove.parser import Parser

        source = (
            "module FactTest\n"
            "  InputOutput outputs console\n"
            "transforms fact(n Integer, acc Integer) Integer\n"
            "  terminates: n\n"
            "from\n"
            "    match n\n"
            "        0 => acc\n"
            "        _ => fact(n - 1, acc * n)\n"
            "\n"
            "main()\n"
            "from\n"
            "    console(to_string(fact(5, 1)))\n"
        )

        tokens = Lexer(source, "<test>").lex()
        module = Parser(tokens, "<test>").parse()
        checker = Checker()
        symbols = checker.check(module)

        optimizer = Optimizer(module, symbols)
        optimized = optimizer.optimize()

        emitter = CEmitter(optimized, symbols)
        c_code = emitter.emit()

        assert "while (1)" in c_code
        assert "continue;" in c_code


# ── Dead Branch Elimination tests ─────────────────────────────────


class TestDeadBranchElimination:
    def test_constant_boolean_match(self):
        """Match on a boolean literal should eliminate dead branches."""
        # match true { true -> 1, false -> 2 }
        arms = [
            MatchArm(
                pattern=LiteralPattern("true", _SPAN),
                body=[ExprStmt(IntegerLit("1", _SPAN), _SPAN)],
                span=_SPAN,
            ),
            MatchArm(
                pattern=LiteralPattern("false", _SPAN),
                body=[ExprStmt(IntegerLit("2", _SPAN), _SPAN)],
                span=_SPAN,
            ),
        ]
        match = MatchExpr(subject=BooleanLit(True, _SPAN), arms=arms, span=_SPAN)
        fd = _make_func("test_dbe", body=[match])
        module = _make_module(fd)
        symbols = SymbolTable()

        result = Optimizer(module, symbols).optimize()
        new_fd = result.declarations[0]
        assert isinstance(new_fd, FunctionDef)
        # The match should be in the body
        match_stmt = new_fd.body[0]
        assert isinstance(match_stmt, MatchExpr)
        # Only the 'true' arm should remain
        assert len(match_stmt.arms) == 1
        assert isinstance(match_stmt.arms[0].pattern, LiteralPattern)
        assert match_stmt.arms[0].pattern.value == "true"

    def test_wildcard_kept(self):
        """Wildcard arm should always be kept in dead branch elimination."""
        arms = [
            MatchArm(
                pattern=LiteralPattern("false", _SPAN),
                body=[ExprStmt(IntegerLit("1", _SPAN), _SPAN)],
                span=_SPAN,
            ),
            MatchArm(
                pattern=WildcardPattern(_SPAN),
                body=[ExprStmt(IntegerLit("2", _SPAN), _SPAN)],
                span=_SPAN,
            ),
        ]
        match = MatchExpr(subject=BooleanLit(True, _SPAN), arms=arms, span=_SPAN)
        fd = _make_func("test_wc", body=[match])
        module = _make_module(fd)
        symbols = SymbolTable()

        result = Optimizer(module, symbols).optimize()
        new_fd = result.declarations[0]
        match_stmt = new_fd.body[0]
        assert isinstance(match_stmt, MatchExpr)
        # Only wildcard should remain (false literal eliminated)
        assert len(match_stmt.arms) == 1
        assert isinstance(match_stmt.arms[0].pattern, WildcardPattern)


# ── Small Function Inlining tests ─────────────────────────────────


class TestInlining:
    def test_single_expr_inlined(self):
        """A pure single-expression function should be inlined at call sites."""
        # Define: transforms double(x) from x * 2
        x_param = _make_param("x")
        double_body = [
            ExprStmt(
                BinaryExpr(
                    IdentifierExpr("x", _SPAN), "*", IntegerLit("2", _SPAN), _SPAN,
                ),
                _SPAN,
            ),
        ]
        double_fd = _make_func("double", params=[x_param], body=double_body)

        # Call: double(5)
        call = CallExpr(
            func=IdentifierExpr("double", _SPAN),
            args=[IntegerLit("5", _SPAN)],
            span=_SPAN,
        )
        main = MainDef(
            return_type=None,
            can_fail=False,
            body=[ExprStmt(call, _SPAN)],
            doc_comment=None,
            span=_SPAN,
        )

        module = _make_module(double_fd, main)
        symbols = SymbolTable()
        result = Optimizer(module, symbols).optimize()

        # The call in main should be replaced with the inlined expression
        main_decl = result.declarations[1]
        assert isinstance(main_decl, MainDef)
        stmt = main_decl.body[0]
        assert isinstance(stmt, ExprStmt)
        # Should now be a BinaryExpr (5 * 2) instead of a CallExpr
        assert isinstance(stmt.expr, BinaryExpr)
        assert stmt.expr.op == "*"

    def test_recursive_not_inlined(self):
        """Functions with terminates (recursive) should not be inlined."""
        param = _make_param("n")
        body = [ExprStmt(IdentifierExpr("n", _SPAN), _SPAN)]
        fd = _make_func(
            "recur", params=[param], body=body,
            terminates=IdentifierExpr("n", _SPAN),
        )

        call = CallExpr(
            func=IdentifierExpr("recur", _SPAN),
            args=[IntegerLit("5", _SPAN)],
            span=_SPAN,
        )
        main = MainDef(
            return_type=None, can_fail=False,
            body=[ExprStmt(call, _SPAN)],
            doc_comment=None, span=_SPAN,
        )

        module = _make_module(fd, main)
        symbols = SymbolTable()
        result = Optimizer(module, symbols).optimize()

        main_decl = result.declarations[1]
        assert isinstance(main_decl, MainDef)
        stmt = main_decl.body[0]
        assert isinstance(stmt, ExprStmt)
        # Should still be a CallExpr (not inlined)
        assert isinstance(stmt.expr, CallExpr)


# ── Match Compilation tests ───────────────────────────────────────


class TestMatchCompilation:
    def test_consecutive_matches_merged(self):
        """Two consecutive matches on the same variable should merge."""
        subj = IdentifierExpr("x", _SPAN)

        match1 = MatchExpr(
            subject=subj,
            arms=[
                MatchArm(
                    pattern=LiteralPattern("1", _SPAN),
                    body=[ExprStmt(IntegerLit("10", _SPAN), _SPAN)],
                    span=_SPAN,
                ),
            ],
            span=_SPAN,
        )
        match2 = MatchExpr(
            subject=subj,
            arms=[
                MatchArm(
                    pattern=LiteralPattern("2", _SPAN),
                    body=[ExprStmt(IntegerLit("20", _SPAN), _SPAN)],
                    span=_SPAN,
                ),
            ],
            span=_SPAN,
        )

        fd = _make_func(
            "test_merge",
            params=[_make_param("x")],
            body=[match1, match2],
        )
        module = _make_module(fd)
        symbols = SymbolTable()
        result = Optimizer(module, symbols).optimize()

        new_fd = result.declarations[0]
        assert isinstance(new_fd, FunctionDef)
        # Should be merged into a single match with 2 arms
        assert len(new_fd.body) == 1
        merged = new_fd.body[0]
        assert isinstance(merged, MatchExpr)
        assert len(merged.arms) == 2
