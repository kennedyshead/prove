"""AST optimizer for the Prove language.

Sits between the Checker/Prover and C Emitter. Each pass takes a Module
and returns a new Module (frozen AST, no mutation). Uses
dataclasses.replace() for field updates.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from prove.ast_nodes import (
    Assignment,
    BooleanLit,
    CallExpr,
    Declaration,
    Expr,
    ExprStmt,
    FunctionDef,
    IdentifierExpr,
    LiteralPattern,
    MainDef,
    MatchArm,
    MatchExpr,
    Module,
    ModuleDecl,
    TailContinue,
    TailLoop,
    VarDecl,
    WildcardPattern,
)
from prove.symbols import SymbolTable


class Optimizer:
    """Multi-pass AST optimizer."""

    def __init__(self, module: Module, symbols: SymbolTable) -> None:
        self._module = module
        self._symbols = symbols

    def optimize(self) -> Module:
        module = self._tail_call_optimization(self._module)
        module = self._dead_branch_elimination(module)
        module = self._inline_small_functions(module)
        module = self._match_compilation(module)
        module = self._copy_elision(module)
        module = self._iterator_fusion(module)
        return module

    # ── Pass 1: Tail Call Optimization ────────────────────────────

    def _tail_call_optimization(self, module: Module) -> Module:
        """Rewrite eligible tail-recursive functions into TailLoop/TailContinue."""
        new_decls: list[Declaration] = []
        for decl in module.declarations:
            if isinstance(decl, FunctionDef):
                new_decls.append(self._tco_function(decl))
            elif isinstance(decl, ModuleDecl):
                new_body: list[Declaration] = []
                for inner in decl.body:
                    if isinstance(inner, FunctionDef):
                        new_body.append(self._tco_function(inner))
                    else:
                        new_body.append(inner)
                new_decls.append(replace(decl, body=new_body))
            else:
                new_decls.append(decl)
        return replace(module, declarations=new_decls)

    def _tco_function(self, fd: FunctionDef) -> FunctionDef:
        """Apply TCO to a single function if eligible."""
        # Must have `terminates` annotation and be self-recursive
        if fd.terminates is None:
            return fd
        if not self._calls_self(fd.name, fd.body):
            return fd
        # Check that the body ends in a tail position self-call
        if not self._has_tail_call(fd.name, fd.body):
            return fd

        param_names = [p.name for p in fd.params]
        rewritten_body = self._rewrite_tail_calls(fd.name, param_names, fd.body)
        tail_loop = TailLoop(
            params=param_names,
            body=rewritten_body,
            span=fd.span,
        )
        return replace(fd, body=[tail_loop])

    def _has_tail_call(self, name: str, body: list[Any]) -> bool:
        """Check if body ends with a self-call in tail position."""
        if not body:
            return False
        last = body[-1]
        # Unwrap ExprStmt to get the inner expression
        if isinstance(last, ExprStmt):
            if self._is_tail_call(name, last.expr):
                return True
            # Match wrapped in ExprStmt
            if isinstance(last.expr, MatchExpr):
                return any(
                    arm.body and self._is_tail_call_in_arm(name, arm)
                    for arm in last.expr.arms
                )
        if isinstance(last, MatchExpr):
            return any(
                arm.body and self._is_tail_call_in_arm(name, arm)
                for arm in last.arms
            )
        return False

    def _is_tail_call_in_arm(self, name: str, arm: MatchArm) -> bool:
        """Check if a match arm ends with a tail call."""
        if not arm.body:
            return False
        last = arm.body[-1]
        if isinstance(last, ExprStmt):
            return self._is_tail_call(name, last.expr)
        return False

    def _is_tail_call(self, name: str, expr: Expr) -> bool:
        """Check if an expression is a direct self-call."""
        return (
            isinstance(expr, CallExpr)
            and isinstance(expr.func, IdentifierExpr)
            and expr.func.name == name
        )

    def _rewrite_tail_calls(
        self, name: str, params: list[str], body: list[Any],
    ) -> list[Any]:
        """Rewrite tail-recursive calls to TailContinue."""
        result: list[Any] = []
        for i, stmt in enumerate(body):
            is_last = i == len(body) - 1
            if is_last:
                if isinstance(stmt, ExprStmt) and self._is_tail_call(name, stmt.expr):
                    call = stmt.expr
                    assert isinstance(call, CallExpr)
                    assignments = list(zip(params, call.args))
                    result.append(TailContinue(assignments=assignments, span=stmt.span))
                elif isinstance(stmt, ExprStmt) and isinstance(stmt.expr, MatchExpr):
                    # Match wrapped in ExprStmt — rewrite inner match
                    rewritten = self._rewrite_match_tail_calls(name, params, stmt.expr)
                    result.append(rewritten)
                elif isinstance(stmt, MatchExpr):
                    result.append(self._rewrite_match_tail_calls(name, params, stmt))
                else:
                    result.append(stmt)
            else:
                result.append(stmt)
        return result

    def _rewrite_match_tail_calls(
        self, name: str, params: list[str], m: MatchExpr,
    ) -> MatchExpr:
        """Rewrite tail calls inside match arms."""
        new_arms = []
        for arm in m.arms:
            new_body = self._rewrite_tail_calls(name, params, arm.body)
            new_arms.append(replace(arm, body=new_body))
        return replace(m, arms=new_arms)

    def _calls_self(self, name: str, body: list[Any]) -> bool:
        """Check if function body contains a recursive call to itself."""
        for stmt in body:
            if isinstance(stmt, ExprStmt):
                if self._expr_calls(name, stmt.expr):
                    return True
            elif isinstance(stmt, VarDecl):
                if self._expr_calls(name, stmt.value):
                    return True
            elif isinstance(stmt, Assignment):
                if self._expr_calls(name, stmt.value):
                    return True
            elif isinstance(stmt, MatchExpr):
                if stmt.subject and self._expr_calls(name, stmt.subject):
                    return True
                for arm in stmt.arms:
                    if self._calls_self(name, arm.body):
                        return True
        return False

    def _expr_calls(self, name: str, expr: Expr) -> bool:
        """Check if an expression contains a call to the named function."""
        from prove.ast_nodes import (
            BinaryExpr,
            FailPropExpr,
            LambdaExpr,
            PipeExpr,
            UnaryExpr,
        )
        if isinstance(expr, CallExpr):
            if isinstance(expr.func, IdentifierExpr) and expr.func.name == name:
                return True
            for arg in expr.args:
                if self._expr_calls(name, arg):
                    return True
        elif isinstance(expr, BinaryExpr):
            return self._expr_calls(name, expr.left) or self._expr_calls(name, expr.right)
        elif isinstance(expr, UnaryExpr):
            return self._expr_calls(name, expr.operand)
        elif isinstance(expr, PipeExpr):
            return self._expr_calls(name, expr.left) or self._expr_calls(name, expr.right)
        elif isinstance(expr, FailPropExpr):
            return self._expr_calls(name, expr.expr)
        elif isinstance(expr, LambdaExpr):
            return self._expr_calls(name, expr.body)
        elif isinstance(expr, MatchExpr):
            if expr.subject and self._expr_calls(name, expr.subject):
                return True
            for arm in expr.arms:
                for s in arm.body:
                    if isinstance(s, ExprStmt) and self._expr_calls(name, s.expr):
                        return True
                    elif isinstance(s, VarDecl) and self._expr_calls(name, s.value):
                        return True
                    elif isinstance(s, Assignment) and self._expr_calls(name, s.value):
                        return True
        return False

    # ── Pass 2: Dead Branch Elimination ───────────────────────────

    def _dead_branch_elimination(self, module: Module) -> Module:
        """Remove match arms with statically-known-false patterns."""
        new_decls: list[Declaration] = []
        for decl in module.declarations:
            if isinstance(decl, FunctionDef):
                new_decls.append(self._dbe_function(decl))
            elif isinstance(decl, ModuleDecl):
                new_body = [
                    self._dbe_function(d) if isinstance(d, FunctionDef) else d
                    for d in decl.body
                ]
                new_decls.append(replace(decl, body=new_body))
            elif isinstance(decl, MainDef):
                new_decls.append(replace(decl, body=self._dbe_stmts(decl.body)))
            else:
                new_decls.append(decl)
        return replace(module, declarations=new_decls)

    def _dbe_function(self, fd: FunctionDef) -> FunctionDef:
        return replace(fd, body=self._dbe_stmts(fd.body))

    def _dbe_stmts(self, stmts: list[Any]) -> list[Any]:
        """Walk statements looking for match exprs to simplify."""
        result: list[Any] = []
        for stmt in stmts:
            if isinstance(stmt, ExprStmt) and isinstance(stmt.expr, MatchExpr):
                simplified = self._dbe_match(stmt.expr)
                result.append(replace(stmt, expr=simplified))
            elif isinstance(stmt, MatchExpr):
                result.append(self._dbe_match(stmt))
            elif isinstance(stmt, TailLoop):
                result.append(replace(stmt, body=self._dbe_stmts(stmt.body)))
            else:
                result.append(stmt)
        return result

    def _dbe_match(self, m: MatchExpr) -> MatchExpr:
        """Eliminate dead branches in a match expression."""
        if m.subject is None:
            return m

        # Check if subject is a known boolean literal
        if isinstance(m.subject, BooleanLit):
            val_str = "true" if m.subject.value else "false"
            kept_arms = []
            for arm in m.arms:
                if isinstance(arm.pattern, LiteralPattern):
                    if arm.pattern.value == val_str:
                        kept_arms.append(arm)
                    # else: dead branch, skip
                elif isinstance(arm.pattern, WildcardPattern):
                    kept_arms.append(arm)
                else:
                    kept_arms.append(arm)
            if kept_arms:
                return replace(m, arms=kept_arms)

        return m

    # ── Pass 3: Small Function Inlining ───────────────────────────

    def _inline_small_functions(self, module: Module) -> Module:
        """Inline pure single-expression functions at call sites."""
        # Collect inline candidates
        _pure_verbs = {"transforms", "validates", "reads", "creates", "matches"}
        candidates: dict[str, FunctionDef] = {}
        for decl in module.declarations:
            if isinstance(decl, FunctionDef):
                if (
                    decl.verb in _pure_verbs
                    and len(decl.body) == 1
                    and isinstance(decl.body[0], ExprStmt)
                    and not decl.binary
                    and decl.terminates is None
                    and not self._calls_self(decl.name, decl.body)
                ):
                    candidates[decl.name] = decl
            elif isinstance(decl, ModuleDecl):
                for inner in decl.body:
                    if isinstance(inner, FunctionDef):
                        if (
                            inner.verb in _pure_verbs
                            and len(inner.body) == 1
                            and isinstance(inner.body[0], ExprStmt)
                            and not inner.binary
                            and inner.terminates is None
                            and not self._calls_self(inner.name, inner.body)
                        ):
                            candidates[inner.name] = inner

        if not candidates:
            return module

        # Apply inlining
        new_decls: list[Declaration] = []
        for decl in module.declarations:
            if isinstance(decl, FunctionDef):
                new_decls.append(
                    replace(decl, body=self._inline_stmts(decl.body, candidates)),
                )
            elif isinstance(decl, MainDef):
                new_decls.append(
                    replace(decl, body=self._inline_stmts(decl.body, candidates)),
                )
            elif isinstance(decl, ModuleDecl):
                new_body = [
                    replace(d, body=self._inline_stmts(d.body, candidates))
                    if isinstance(d, FunctionDef) else d
                    for d in decl.body
                ]
                new_decls.append(replace(decl, body=new_body))
            else:
                new_decls.append(decl)
        return replace(module, declarations=new_decls)

    def _inline_stmts(self, stmts: list[Any], candidates: dict[str, FunctionDef]) -> list[Any]:
        return [self._inline_in_stmt(s, candidates) for s in stmts]

    def _inline_in_stmt(self, stmt: Any, candidates: dict[str, FunctionDef]) -> Any:
        if isinstance(stmt, ExprStmt):
            return replace(stmt, expr=self._inline_in_expr(stmt.expr, candidates))
        if isinstance(stmt, VarDecl):
            return replace(stmt, value=self._inline_in_expr(stmt.value, candidates))
        if isinstance(stmt, Assignment):
            return replace(stmt, value=self._inline_in_expr(stmt.value, candidates))
        if isinstance(stmt, MatchExpr):
            new_arms = []
            for arm in stmt.arms:
                new_body = self._inline_stmts(arm.body, candidates)
                new_arms.append(replace(arm, body=new_body))
            subj = self._inline_in_expr(stmt.subject, candidates) if stmt.subject else None
            return replace(stmt, subject=subj, arms=new_arms)
        if isinstance(stmt, TailLoop):
            return replace(stmt, body=self._inline_stmts(stmt.body, candidates))
        return stmt

    def _inline_in_expr(self, expr: Expr, candidates: dict[str, FunctionDef]) -> Expr:
        """Recursively inline small functions in an expression."""
        from prove.ast_nodes import (
            BinaryExpr,
            FailPropExpr,
            IndexExpr,
            ListLiteral,
            PipeExpr,
            StringInterp,
            UnaryExpr,
        )

        if isinstance(expr, CallExpr):
            # Check if this call is to an inline candidate
            if isinstance(expr.func, IdentifierExpr) and expr.func.name in candidates:
                fd = candidates[expr.func.name]
                if len(expr.args) == len(fd.params):
                    # Substitute params with args
                    body_expr = fd.body[0]
                    assert isinstance(body_expr, ExprStmt)
                    substituted = self._substitute_params(
                        body_expr.expr, fd.params, expr.args,
                    )
                    return self._inline_in_expr(substituted, candidates)
            # Recursively inline in args
            new_args = [self._inline_in_expr(a, candidates) for a in expr.args]
            new_func = self._inline_in_expr(expr.func, candidates)
            return replace(expr, func=new_func, args=new_args)

        if isinstance(expr, BinaryExpr):
            return replace(
                expr,
                left=self._inline_in_expr(expr.left, candidates),
                right=self._inline_in_expr(expr.right, candidates),
            )
        if isinstance(expr, UnaryExpr):
            return replace(expr, operand=self._inline_in_expr(expr.operand, candidates))
        if isinstance(expr, PipeExpr):
            return replace(
                expr,
                left=self._inline_in_expr(expr.left, candidates),
                right=self._inline_in_expr(expr.right, candidates),
            )
        if isinstance(expr, FailPropExpr):
            return replace(expr, expr=self._inline_in_expr(expr.expr, candidates))
        if isinstance(expr, IndexExpr):
            return replace(
                expr,
                obj=self._inline_in_expr(expr.obj, candidates),
                index=self._inline_in_expr(expr.index, candidates),
            )
        if isinstance(expr, ListLiteral):
            return replace(
                expr,
                elements=[self._inline_in_expr(e, candidates) for e in expr.elements],
            )
        if isinstance(expr, StringInterp):
            return replace(
                expr,
                parts=[self._inline_in_expr(p, candidates) for p in expr.parts],
            )
        if isinstance(expr, MatchExpr):
            new_arms = []
            for arm in expr.arms:
                new_body = self._inline_stmts(arm.body, candidates)
                new_arms.append(replace(arm, body=new_body))
            subj = self._inline_in_expr(expr.subject, candidates) if expr.subject else None
            return replace(expr, subject=subj, arms=new_arms)

        return expr

    def _substitute_params(
        self, expr: Expr, params: list[Any], args: list[Expr],
    ) -> Expr:
        """Substitute IdentifierExpr nodes matching param names with arg expressions."""
        from prove.ast_nodes import (
            BinaryExpr,
            IndexExpr,
            PipeExpr,
            UnaryExpr,
        )

        param_map = {p.name: a for p, a in zip(params, args)}

        if isinstance(expr, IdentifierExpr):
            if expr.name in param_map:
                return param_map[expr.name]
            return expr
        if isinstance(expr, CallExpr):
            new_args = [self._substitute_params(a, params, args) for a in expr.args]
            new_func = self._substitute_params(expr.func, params, args)
            return replace(expr, func=new_func, args=new_args)
        if isinstance(expr, BinaryExpr):
            return replace(
                expr,
                left=self._substitute_params(expr.left, params, args),
                right=self._substitute_params(expr.right, params, args),
            )
        if isinstance(expr, UnaryExpr):
            return replace(
                expr, operand=self._substitute_params(expr.operand, params, args),
            )
        if isinstance(expr, PipeExpr):
            return replace(
                expr,
                left=self._substitute_params(expr.left, params, args),
                right=self._substitute_params(expr.right, params, args),
            )
        if isinstance(expr, IndexExpr):
            return replace(
                expr,
                obj=self._substitute_params(expr.obj, params, args),
                index=self._substitute_params(expr.index, params, args),
            )
        if isinstance(expr, MatchExpr):
            new_arms = []
            for arm in expr.arms:
                new_body: list[Any] = []
                for s in arm.body:
                    if isinstance(s, ExprStmt):
                        new_body.append(replace(
                            s, expr=self._substitute_params(s.expr, params, args),
                        ))
                    else:
                        new_body.append(s)
                new_arms.append(replace(arm, body=new_body))
            subj = (
                self._substitute_params(expr.subject, params, args)
                if expr.subject else None
            )
            return replace(expr, subject=subj, arms=new_arms)

        return expr

    # ── Pass 4: Match Compilation ─────────────────────────────────

    def _match_compilation(self, module: Module) -> Module:
        """Merge consecutive match statements on the same variable.

        v0.5 scope: simple merge only. Full decision-tree deferred.
        """
        new_decls: list[Declaration] = []
        for decl in module.declarations:
            if isinstance(decl, FunctionDef):
                new_decls.append(replace(decl, body=self._merge_matches(decl.body)))
            elif isinstance(decl, MainDef):
                new_decls.append(replace(decl, body=self._merge_matches(decl.body)))
            elif isinstance(decl, ModuleDecl):
                new_body = [
                    replace(d, body=self._merge_matches(d.body))
                    if isinstance(d, FunctionDef) else d
                    for d in decl.body
                ]
                new_decls.append(replace(decl, body=new_body))
            else:
                new_decls.append(decl)
        return replace(module, declarations=new_decls)

    def _merge_matches(self, stmts: list[Any]) -> list[Any]:
        """Merge consecutive match statements on the same subject."""
        if len(stmts) < 2:
            return stmts

        result = []
        i = 0
        while i < len(stmts):
            stmt = stmts[i]
            if (
                isinstance(stmt, MatchExpr)
                and stmt.subject is not None
                and isinstance(stmt.subject, IdentifierExpr)
            ):
                # Look ahead for more matches on the same subject
                merged_arms = list(stmt.arms)
                subject_name = stmt.subject.name
                j = i + 1
                while j < len(stmts):
                    next_stmt = stmts[j]
                    if (
                        isinstance(next_stmt, MatchExpr)
                        and next_stmt.subject is not None
                        and isinstance(next_stmt.subject, IdentifierExpr)
                        and next_stmt.subject.name == subject_name
                    ):
                        merged_arms.extend(next_stmt.arms)
                        j += 1
                    else:
                        break
                if j > i + 1:
                    result.append(replace(stmt, arms=merged_arms))
                else:
                    result.append(stmt)
                i = j
            else:
                result.append(stmt)
                i += 1
        return result

    # ── Pass 5: Copy Elision ──────────────────────────────────────

    def _copy_elision(self, module: Module) -> Module:
        """Detect transforms functions where return is a direct parameter reference.

        This is tracked as metadata for the C emitter to skip retain/release.
        v0.5: structural detection only, no AST modification.
        """
        # For now, this is a no-op. The C emitter handles retain/release
        # and we'll add elision metadata in a future pass.
        return module

    # ── Pass 6: Iterator Fusion ───────────────────────────────────

    def _iterator_fusion(self, module: Module) -> Module:
        """Detect map(filter(xs, pred), fn) patterns and fuse them.

        v0.5: structural detection only, full rewrite deferred.
        """
        # For now, this is a no-op. Iterator fusion requires List runtime
        # support that will come in v0.6.
        return module
