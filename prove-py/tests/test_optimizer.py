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
    LambdaExpr,
    LiteralPattern,
    MainDef,
    MatchArm,
    MatchExpr,
    Module,
    Param,
    SimpleType,
    Stmt,
    TailContinue,
    TailLoop,
    VarDecl,
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
    body: list[Stmt] | None = None,
    terminates: BinaryExpr | None = None,
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
        explain=None,
        terminates=terminates,
        trusted=None,
        binary=False,
        why_not=[],
        chosen=None,
        near_misses=[],
        know=[],
        assume=[],
        believe=[],
        with_constraints=[],
        intent=None,
        satisfies=[],
        event_type=None,
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
        from prove.config import BuildConfig, OptimizeConfig, PackageConfig, ProveConfig

        # Create a project with a tail-recursive function
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (tmp_path / "prove.toml").write_text(
            textwrap.dedent("""\
            [package]
            name = "tco_test"
            [build]
            optimize = true
        """)
        )
        (src_dir / "main.prv").write_text(
            "module TcoTest\n"
            '  narrative: """TCO test"""\n'
            "  System outputs console\n"
            "matches count(n Integer, acc Integer) Integer\n"
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
            optimize=OptimizeConfig(enabled=True),
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
            "  System outputs console\n"
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
                    IdentifierExpr("x", _SPAN),
                    "*",
                    IntegerLit("2", _SPAN),
                    _SPAN,
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

        # After CT evaluation, the function is eliminated (since it was CT-evaluated)
        # Only MainDef remains (index 0)
        main_decl = result.declarations[0]
        assert isinstance(main_decl, MainDef)
        stmt = main_decl.body[0]
        assert isinstance(stmt, ExprStmt)
        # Should now be an IntegerLit (10) from CT evaluation
        assert isinstance(stmt.expr, IntegerLit)
        assert stmt.expr.value == "10"

    def test_recursive_not_inlined(self):
        """Functions with terminates (recursive) should not be CT-evaluated."""
        param = _make_param("n")
        recur_call = CallExpr(
            func=IdentifierExpr("recur", _SPAN),
            args=[BinaryExpr("-", IdentifierExpr("n", _SPAN), IntegerLit("1", _SPAN), _SPAN)],
            span=_SPAN,
        )
        body = [ExprStmt(recur_call, _SPAN)]
        fd = _make_func(
            "recur",
            params=[param],
            body=body,
            terminates=IdentifierExpr("n", _SPAN),
        )

        call = CallExpr(
            func=IdentifierExpr("recur", _SPAN),
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

        module = _make_module(fd, main)
        symbols = SymbolTable()
        result = Optimizer(module, symbols).optimize()

        main_decl = result.declarations[1]
        assert isinstance(main_decl, MainDef)
        stmt = main_decl.body[0]
        assert isinstance(stmt, ExprStmt)
        # Should still be a CallExpr (not CT-evaluated because recursive)
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


# ── Iterator Fusion tests ────────────────────────────────────────


class TestIteratorFusion:
    def test_map_filter_fused(self):
        """map(filter(list, pred), func) should be fused into __fused_map_filter."""
        # filter(xs, pred)
        inner = CallExpr(
            func=IdentifierExpr("filter", _SPAN),
            args=[
                IdentifierExpr("xs", _SPAN),
                LambdaExpr(params=["x"], body=BinaryExpr(
                    IdentifierExpr("x", _SPAN), ">", IntegerLit("0", _SPAN), _SPAN
                ), span=_SPAN),
            ],
            span=_SPAN,
        )
        # map(filter(xs, pred), func)
        outer = CallExpr(
            func=IdentifierExpr("map", _SPAN),
            args=[
                inner,
                LambdaExpr(params=["x"], body=BinaryExpr(
                    IdentifierExpr("x", _SPAN), "*", IntegerLit("2", _SPAN), _SPAN
                ), span=_SPAN),
            ],
            span=_SPAN,
        )
        fd = _make_func(
            "test_fusion",
            params=[_make_param("xs")],
            body=[ExprStmt(outer, _SPAN)],
        )
        module = _make_module(fd)
        symbols = SymbolTable()
        result = Optimizer(module, symbols).optimize()

        new_fd = result.declarations[0]
        assert isinstance(new_fd, FunctionDef)
        stmt = new_fd.body[0]
        assert isinstance(stmt, ExprStmt)
        call = stmt.expr
        assert isinstance(call, CallExpr)
        assert isinstance(call.func, IdentifierExpr)
        assert call.func.name == "__fused_map_filter"
        assert len(call.args) == 3  # list, pred, func

    def test_filter_map_fused(self):
        """filter(map(list, func), pred) should be fused into __fused_filter_map."""
        # map(xs, func)
        inner = CallExpr(
            func=IdentifierExpr("map", _SPAN),
            args=[
                IdentifierExpr("xs", _SPAN),
                LambdaExpr(params=["x"], body=BinaryExpr(
                    IdentifierExpr("x", _SPAN), "*", IntegerLit("2", _SPAN), _SPAN
                ), span=_SPAN),
            ],
            span=_SPAN,
        )
        # filter(map(xs, func), pred)
        outer = CallExpr(
            func=IdentifierExpr("filter", _SPAN),
            args=[
                inner,
                LambdaExpr(params=["x"], body=BinaryExpr(
                    IdentifierExpr("x", _SPAN), ">", IntegerLit("0", _SPAN), _SPAN
                ), span=_SPAN),
            ],
            span=_SPAN,
        )
        fd = _make_func(
            "test_fusion",
            params=[_make_param("xs")],
            body=[ExprStmt(outer, _SPAN)],
        )
        module = _make_module(fd)
        symbols = SymbolTable()
        result = Optimizer(module, symbols).optimize()

        new_fd = result.declarations[0]
        stmt = new_fd.body[0]
        call = stmt.expr
        assert isinstance(call, CallExpr)
        assert call.func.name == "__fused_filter_map"
        assert len(call.args) == 3

    def test_map_map_fused(self):
        """map(map(list, f), g) should be fused into __fused_map_map."""
        # map(xs, f)
        inner = CallExpr(
            func=IdentifierExpr("map", _SPAN),
            args=[
                IdentifierExpr("xs", _SPAN),
                IdentifierExpr("double", _SPAN),
            ],
            span=_SPAN,
        )
        # map(map(xs, f), g)
        outer = CallExpr(
            func=IdentifierExpr("map", _SPAN),
            args=[
                inner,
                IdentifierExpr("negate", _SPAN),
            ],
            span=_SPAN,
        )
        fd = _make_func(
            "test_fusion",
            params=[_make_param("xs")],
            body=[ExprStmt(outer, _SPAN)],
        )
        module = _make_module(fd)
        symbols = SymbolTable()
        result = Optimizer(module, symbols).optimize()

        new_fd = result.declarations[0]
        stmt = new_fd.body[0]
        call = stmt.expr
        assert isinstance(call, CallExpr)
        assert call.func.name == "__fused_map_map"
        assert len(call.args) == 3

    def test_single_map_unchanged(self):
        """A single map() call should not be fused."""
        call = CallExpr(
            func=IdentifierExpr("map", _SPAN),
            args=[
                IdentifierExpr("xs", _SPAN),
                IdentifierExpr("double", _SPAN),
            ],
            span=_SPAN,
        )
        fd = _make_func(
            "test_no_fusion",
            params=[_make_param("xs")],
            body=[ExprStmt(call, _SPAN)],
        )
        module = _make_module(fd)
        symbols = SymbolTable()
        result = Optimizer(module, symbols).optimize()

        new_fd = result.declarations[0]
        stmt = new_fd.body[0]
        assert isinstance(stmt.expr, CallExpr)
        assert stmt.expr.func.name == "map"  # unchanged


# ── Copy Elision tests ───────────────────────────────────────────


class TestCopyElision:
    def test_single_use_var_marked(self):
        """A variable used exactly once should be marked for elision."""
        body = [
            VarDecl(
                name="tmp",
                type_expr=SimpleType("Integer", _SPAN),
                value=IntegerLit("42", _SPAN),
                span=_SPAN,
            ),
            ExprStmt(IdentifierExpr("tmp", _SPAN), _SPAN),
        ]
        fd = _make_func("test_elision", body=body)
        module = _make_module(fd)
        symbols = SymbolTable()
        opt = Optimizer(module, symbols)
        opt.optimize()

        assert "tmp" in opt.get_elision_candidates()

    def test_multi_use_var_not_marked(self):
        """A variable used more than once should NOT be marked for elision."""
        body = [
            VarDecl(
                name="tmp",
                type_expr=SimpleType("Integer", _SPAN),
                value=IntegerLit("42", _SPAN),
                span=_SPAN,
            ),
            ExprStmt(
                BinaryExpr(
                    IdentifierExpr("tmp", _SPAN),
                    "+",
                    IdentifierExpr("tmp", _SPAN),
                    _SPAN,
                ),
                _SPAN,
            ),
        ]
        fd = _make_func("test_no_elision", body=body)
        module = _make_module(fd)
        symbols = SymbolTable()
        opt = Optimizer(module, symbols)
        opt.optimize()

        assert "tmp" not in opt.get_elision_candidates()


# ── Trivial Loop Folding tests ────────────────────────────────────


class TestTrivialLoopFolding:
    """Tests for the _fold_trivial_loops optimizer pass."""

    def _make_count_loop(self, delta: str = "1") -> FunctionDef:
        """Build count(n, acc) = match n<=0: True->acc, _->count(n-1, acc+delta).

        After TCO this becomes a TailLoop.
        """
        n = IdentifierExpr("n", _SPAN)
        acc = IdentifierExpr("acc", _SPAN)

        base_arm = MatchArm(
            pattern=LiteralPattern("true", _SPAN),
            body=[ExprStmt(acc, _SPAN)],
            span=_SPAN,
        )

        recursive_call = CallExpr(
            func=IdentifierExpr("count", _SPAN),
            args=[
                BinaryExpr(n, "-", IntegerLit("1", _SPAN), _SPAN),
                BinaryExpr(acc, "+", IntegerLit(delta, _SPAN), _SPAN),
            ],
            span=_SPAN,
        )
        rec_arm = MatchArm(
            pattern=WildcardPattern(_SPAN),
            body=[ExprStmt(recursive_call, _SPAN)],
            span=_SPAN,
        )

        cond = BinaryExpr(n, "<=", IntegerLit("0", _SPAN), _SPAN)
        match_expr = MatchExpr(subject=cond, arms=[base_arm, rec_arm], span=_SPAN)

        return _make_func(
            "count",
            params=[_make_param("n"), _make_param("acc")],
            body=[match_expr],
            terminates=n,
        )

    def test_count_loop_folded(self):
        """count(n-1, acc+1) should fold to: match n<=0: True->acc, _->acc+n."""
        fd = self._make_count_loop("1")
        module = _make_module(fd)
        symbols = SymbolTable()
        result = Optimizer(module, symbols).optimize()

        new_fd = result.declarations[0]
        assert isinstance(new_fd, FunctionDef)
        # Should NOT have a TailLoop anymore — it should be folded
        assert len(new_fd.body) == 1
        body_stmt = new_fd.body[0]
        assert isinstance(body_stmt, MatchExpr), f"Expected MatchExpr, got {type(body_stmt)}"
        assert len(body_stmt.arms) == 2

        # The recursive arm should now be acc + n (no TailContinue)
        rec_arm = body_stmt.arms[1]
        assert len(rec_arm.body) == 1
        assert isinstance(rec_arm.body[0], ExprStmt)
        folded = rec_arm.body[0].expr
        assert isinstance(folded, BinaryExpr)
        assert folded.op == "+"
        # Left should be acc, right should be n
        assert isinstance(folded.left, IdentifierExpr) and folded.left.name == "acc"
        assert isinstance(folded.right, IdentifierExpr) and folded.right.name == "n"

    def test_constant_delta_folded(self):
        """count(n-1, acc+3) should fold to: match n<=0: True->acc, _->acc+3*n."""
        fd = self._make_count_loop("3")
        module = _make_module(fd)
        symbols = SymbolTable()
        result = Optimizer(module, symbols).optimize()

        new_fd = result.declarations[0]
        body_stmt = new_fd.body[0]
        assert isinstance(body_stmt, MatchExpr)
        rec_arm = body_stmt.arms[1]
        folded = rec_arm.body[0].expr
        assert isinstance(folded, BinaryExpr)
        assert folded.op == "+"
        # Left: acc, Right: 3 * n
        assert isinstance(folded.left, IdentifierExpr) and folded.left.name == "acc"
        product = folded.right
        assert isinstance(product, BinaryExpr)
        assert product.op == "*"

    def test_factorial_not_folded(self):
        """fact(n-1, acc*n) should NOT be folded — acc*n is not acc+delta."""
        n = IdentifierExpr("n", _SPAN)
        acc = IdentifierExpr("acc", _SPAN)

        base_arm = MatchArm(
            pattern=LiteralPattern("true", _SPAN),
            body=[ExprStmt(acc, _SPAN)],
            span=_SPAN,
        )
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

        cond = BinaryExpr(n, "<=", IntegerLit("0", _SPAN), _SPAN)
        match_expr = MatchExpr(subject=cond, arms=[base_arm, rec_arm], span=_SPAN)

        fd = _make_func(
            "factorial",
            params=[_make_param("n"), _make_param("acc")],
            body=[match_expr],
            terminates=n,
        )
        module = _make_module(fd)
        symbols = SymbolTable()
        result = Optimizer(module, symbols).optimize()

        # Should still have a TailLoop (not folded because acc*n is not acc+delta)
        new_fd = result.declarations[0]
        assert isinstance(new_fd.body[0], TailLoop)

    def test_counter_dependent_delta_not_folded(self):
        """count(n-1, acc+n) should NOT be folded — delta depends on counter."""
        n = IdentifierExpr("n", _SPAN)
        acc = IdentifierExpr("acc", _SPAN)

        base_arm = MatchArm(
            pattern=LiteralPattern("true", _SPAN),
            body=[ExprStmt(acc, _SPAN)],
            span=_SPAN,
        )
        recursive_call = CallExpr(
            func=IdentifierExpr("count", _SPAN),
            args=[
                BinaryExpr(n, "-", IntegerLit("1", _SPAN), _SPAN),
                BinaryExpr(acc, "+", n, _SPAN),  # delta = n, depends on counter
            ],
            span=_SPAN,
        )
        rec_arm = MatchArm(
            pattern=WildcardPattern(_SPAN),
            body=[ExprStmt(recursive_call, _SPAN)],
            span=_SPAN,
        )

        cond = BinaryExpr(n, "<=", IntegerLit("0", _SPAN), _SPAN)
        match_expr = MatchExpr(subject=cond, arms=[base_arm, rec_arm], span=_SPAN)

        fd = _make_func(
            "count",
            params=[_make_param("n"), _make_param("acc")],
            body=[match_expr],
            terminates=n,
        )
        module = _make_module(fd)
        symbols = SymbolTable()
        result = Optimizer(module, symbols).optimize()

        # Should still have a TailLoop (not folded because delta depends on counter)
        new_fd = result.declarations[0]
        assert isinstance(new_fd.body[0], TailLoop)


class TestTailContinueTemporaryElimination:
    """Tests for temporary elimination in _emit_tail_continue."""

    def test_no_cross_deps_no_temps(self, tmp_path, needs_cc):
        """count(n-1, acc+1) should NOT use temp variables (no cross-deps)."""
        from prove.c_emitter import CEmitter
        from prove.checker import Checker
        from prove.lexer import Lexer
        from prove.optimizer import Optimizer
        from prove.parser import Parser

        source = (
            "module CountTest\n"
            "  System outputs console\n"
            "matches count(n Integer, acc Integer) Integer\n"
            "  terminates: n\n"
            "from\n"
            "    match n\n"
            "        0 => acc\n"
            "        _ => count(n - 1, acc + 1)\n"
            "\n"
            "main()\n"
            "from\n"
            "    console(to_string(count(5, 0)))\n"
        )

        tokens = Lexer(source, "<test>").lex()
        module = Parser(tokens, "<test>").parse()
        checker = Checker()
        symbols = checker.check(module)

        optimizer = Optimizer(module, symbols)
        optimized = optimizer.optimize()

        emitter = CEmitter(optimized, symbols)
        c_code = emitter.emit()

        # This loop gets folded, so no TailContinue should remain.
        # The folded version is: match n: 0->acc, _->acc+n
        assert "while (1)" not in c_code

    def test_cross_deps_use_temps(self, tmp_path, needs_cc):
        """fact(n-1, acc*n) should still use temps (acc*n references n)."""
        from prove.c_emitter import CEmitter
        from prove.checker import Checker
        from prove.lexer import Lexer
        from prove.optimizer import Optimizer
        from prove.parser import Parser

        source = (
            "module FactTest\n"
            "  System outputs console\n"
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

        # Should still have while(1) (not folded — acc*n is not additive)
        assert "while (1)" in c_code
        # Should use temps because acc*n references n (cross-dependency)
        assert "_tmp" in c_code
