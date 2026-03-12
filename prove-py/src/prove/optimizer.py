"""AST optimizer for the Prove language.

Sits between the Checker/Prover and C Emitter. Each pass takes a Module
and returns a new Module (frozen AST, no mutation). Uses
dataclasses.replace() for field updates.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from prove.ast_nodes import (
    Assignment,
    BinaryExpr,
    BooleanLit,
    CallExpr,
    CharLit,
    DecimalLit,
    Declaration,
    Expr,
    ExprStmt,
    FailPropExpr,
    FieldExpr,
    FloatLit,
    FunctionDef,
    IdentifierExpr,
    IndexExpr,
    IntegerLit,
    LambdaExpr,
    ListLiteral,
    LiteralPattern,
    MainDef,
    MatchArm,
    MatchExpr,
    Module,
    ModuleDecl,
    PipeExpr,
    StringInterp,
    StringLit,
    TailContinue,
    TailLoop,
    UnaryExpr,
    VarDecl,
    WhileLoop,
    WildcardPattern,
)
from prove.c_runtime import STDLIB_RUNTIME_LIBS
from prove.interpreter import ComptimeInterpreter
from prove.symbols import SymbolTable


@dataclass
class MemoizationCandidate:
    """A pure function that is a candidate for memoization."""

    name: str
    verb: str
    param_count: int
    body_size: int  # number of statements
    param_types: tuple[str, ...] = ()  # C type signatures for hashing


class MemoizationInfo:
    """Tracks memoization candidates discovered during optimization."""

    def __init__(self) -> None:
        self._candidates: dict[str, MemoizationCandidate] = {}

    def add_candidate(self, cand: MemoizationCandidate) -> None:
        key = f"{cand.verb}:{cand.name}"
        self._candidates[key] = cand

    def is_candidate(self, verb: str, name: str) -> bool:
        key = f"{verb}:{name}"
        return key in self._candidates

    def get_candidate(self, verb: str, name: str) -> "MemoizationCandidate | None":
        key = f"{verb}:{name}"
        return self._candidates.get(key)

    def get_candidates(self) -> list[MemoizationCandidate]:
        return list(self._candidates.values())


class RuntimeDeps:
    """Tracks which C runtime libraries are required based on stdlib imports."""

    def __init__(self) -> None:
        self._libs: set[str] = set()

    def add_lib(self, lib: str) -> None:
        self._libs.add(lib)

    def add_module(self, module: str) -> None:
        """Add all runtime libs needed for a stdlib module."""
        normalized = module.lower()
        if normalized in STDLIB_RUNTIME_LIBS:
            self._libs.update(STDLIB_RUNTIME_LIBS[normalized])

    def get_libs(self) -> set[str]:
        return self._libs


class EscapeInfo:
    """Tracks escape analysis information for function allocations.

    A value escapes if it's returned, stored in a mutable parameter,
    stored in a global, or passed to an escaping function.
    Non-escaping values can use region allocation instead of arena/malloc.
    """

    def __init__(self) -> None:
        self._escapes: set[tuple[str, str]] = set()  # (func_name, var_name)
        self._noescape_calls: set[tuple[str, str]] = set()  # (func_name, call_name)

    def mark_escapes(self, func_name: str, var_name: str) -> None:
        """Mark that a variable escapes in a function."""
        self._escapes.add((func_name, var_name))

    def mark_noescape_call(self, func_name: str, call_name: str) -> None:
        """Mark that a call doesn't cause escape (pure function)."""
        self._noescape_calls.add((func_name, call_name))

    def escapes(self, func_name: str, var_name: str) -> bool:
        """Check if a variable escapes in a function. Conservative: defaults to True."""
        return (func_name, var_name) in self._escapes

    def is_noescape_call(self, func_name: str, call_name: str) -> bool:
        """Check if a call is known to be pure/non-escaping."""
        return (func_name, call_name) in self._noescape_calls

    def get_escaping_vars(self, func_name: str) -> set[str]:
        """Get all escaping variables in a function."""
        return {v for f, v in self._escapes if f == func_name}


class Optimizer:
    """Multi-pass AST optimizer."""

    def __init__(self, module: Module, symbols: SymbolTable) -> None:
        self._module = module
        self._symbols = symbols
        self._memo_info = MemoizationInfo()
        self._runtime_deps = RuntimeDeps()
        self._elision_candidates: set[str] = set()
        self._escape_info = EscapeInfo()

    def optimize(self) -> Module:
        module = self._collect_runtime_deps(self._module)
        module = self._tail_call_optimization(module)
        module = self._dead_branch_elimination(module)
        module = self._ct_eval_pure_calls(module)
        module = self._inline_small_functions(module)
        module = self._inline_tco_calls(module)
        module = self._iterator_fusion(module)
        module = self._copy_elision(module)
        module = self._dead_code_elimination(module)
        module = self._identify_memoization_candidates(module)
        module = self._match_compilation(module)
        module = self._escape_analysis(module)
        return module

    def get_memo_info(self) -> MemoizationInfo:
        """Return memoization candidates discovered during optimization."""
        return self._memo_info

    def get_runtime_deps(self) -> RuntimeDeps:
        """Return runtime dependencies discovered during optimization."""
        return self._runtime_deps

    def get_elision_candidates(self) -> set[str]:
        """Return variable names eligible for move-instead-of-copy."""
        return self._elision_candidates

    def get_escape_info(self) -> EscapeInfo:
        """Return escape analysis information."""
        return self._escape_info

    # ── Pass 0: Runtime Dependency Collection ─────────────────────

    def _collect_runtime_deps(self, module: Module) -> Module:
        """Collect which C runtime libraries are needed based on stdlib imports."""
        for decl in module.declarations:
            if isinstance(decl, ModuleDecl):
                for imp in decl.imports:
                    self._runtime_deps.add_module(imp.module)
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
                    arm.body and self._is_tail_call_in_arm(name, arm) for arm in last.expr.arms
                )
        if isinstance(last, MatchExpr):
            return any(arm.body and self._is_tail_call_in_arm(name, arm) for arm in last.arms)
        return False

    def _is_tail_call_in_arm(self, name: str, arm: MatchArm) -> bool:
        """Check if a match arm ends with a tail call."""
        if not arm.body:
            return False
        last = arm.body[-1]
        if isinstance(last, ExprStmt):
            if self._is_tail_call(name, last.expr):
                return True
            if isinstance(last.expr, MatchExpr):
                return any(
                    inner.body and self._is_tail_call_in_arm(name, inner)
                    for inner in last.expr.arms
                )
        if isinstance(last, MatchExpr):
            return any(
                inner.body and self._is_tail_call_in_arm(name, inner)
                for inner in last.arms
            )
        return False

    def _is_tail_call(self, name: str, expr: Expr) -> bool:
        """Check if an expression is a direct self-call."""
        return (
            isinstance(expr, CallExpr)
            and isinstance(expr.func, IdentifierExpr)
            and expr.func.name == name
        )

    def _rewrite_tail_calls(
        self,
        name: str,
        params: list[str],
        body: list[Any],
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
        self,
        name: str,
        params: list[str],
        m: MatchExpr,
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
                    self._dbe_function(d) if isinstance(d, FunctionDef) else d for d in decl.body
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

    # ── Pass 2b: Compile-Time Evaluation of Pure Functions ────────

    def _ct_eval_pure_calls(self, module: Module) -> Module:
        """Evaluate pure function calls with constant arguments at compile time."""
        func_defs: dict[str, FunctionDef] = {}
        for decl in module.declarations:
            if isinstance(decl, FunctionDef):
                func_defs[decl.name] = decl

        new_decls: list[Declaration] = []
        for decl in module.declarations:
            if isinstance(decl, FunctionDef):
                new_decls.append(self._ct_eval_function(decl, func_defs))
            elif isinstance(decl, ModuleDecl):
                new_body = [
                    self._ct_eval_function(d, func_defs) if isinstance(d, FunctionDef) else d
                    for d in decl.body
                ]
                new_decls.append(replace(decl, body=new_body))
            elif isinstance(decl, MainDef):
                new_decls.append(replace(decl, body=self._ct_eval_stmts(decl.body, func_defs)))
            else:
                new_decls.append(decl)
        return replace(module, declarations=new_decls)

    def _ct_eval_function(self, fd: FunctionDef, func_defs: dict[str, FunctionDef]) -> FunctionDef:
        return replace(fd, body=self._ct_eval_stmts(fd.body, func_defs))

    def _ct_eval_stmts(self, stmts: list[Any], func_defs: dict[str, FunctionDef]) -> list[Any]:
        """Walk statements looking for pure function calls with constant args."""
        result: list[Any] = []
        for stmt in stmts:
            if isinstance(stmt, ExprStmt):
                new_expr = self._ct_eval_expr(stmt.expr, func_defs)
                result.append(replace(stmt, expr=new_expr))
            elif isinstance(stmt, MatchExpr):
                result.append(self._ct_eval_match(stmt, func_defs))
            elif isinstance(stmt, TailLoop):
                result.append(replace(stmt, body=self._ct_eval_stmts(stmt.body, func_defs)))
            else:
                result.append(stmt)
        return result

    def _ct_eval_match(self, m: MatchExpr, func_defs: dict[str, FunctionDef]) -> MatchExpr:
        """Evaluate pure function calls in match arms."""
        new_arms: list[MatchArm] = []
        for arm in m.arms:
            new_body = self._ct_eval_stmts(arm.body, func_defs) if arm.body else arm.body
            new_arms.append(replace(arm, body=new_body))
        return replace(m, arms=new_arms)

    def _ct_eval_expr(self, expr: Expr, func_defs: dict[str, FunctionDef]) -> Expr:
        """Try to evaluate a pure function call at compile time."""
        if isinstance(expr, CallExpr) and isinstance(expr.func, IdentifierExpr):
            func_name = expr.func.name
            if func_name not in func_defs:
                return expr
            func_def = func_defs[func_name]
            if self._calls_self(func_name, func_def.body):
                return expr
            args = expr.args
            const_args: list[object] = []
            for arg in args:
                if isinstance(arg, IntegerLit):
                    const_args.append(int(arg.value))
                elif isinstance(arg, BooleanLit):
                    const_args.append(arg.value)
                elif isinstance(arg, StringLit):
                    const_args.append(arg.value)
                elif isinstance(arg, DecimalLit):
                    const_args.append(float(arg.value))
                elif isinstance(arg, FloatLit):
                    const_args.append(float(arg.value[:-1]))
                elif isinstance(arg, CharLit):
                    const_args.append(arg.value)
                else:
                    const_args.append(None)
            if None not in const_args:
                interp = ComptimeInterpreter(function_defs=func_defs)
                result = interp.evaluate_pure_call(func_name, const_args, "transforms")
                if result is not None:
                    if isinstance(result, int):
                        return IntegerLit(value=str(result), span=expr.span)
                    elif isinstance(result, float):
                        return FloatLit(value=str(result) + "f", span=expr.span)
                    elif isinstance(result, bool):
                        return BooleanLit(value=result, span=expr.span)
                    elif isinstance(result, str):
                        return StringLit(value=result, span=expr.span)
        return expr

    # ── Pass 2c: Iterator Fusion ───────────────────────────────────

    def _iterator_fusion(self, module: Module) -> Module:
        """Fuse chained HOF calls into single-pass operations.

        Detects patterns:
        - map(filter(list, pred), func) → fused_map_filter(list, pred, func)
        - filter(map(list, func), pred) → fused_filter_map(list, func, pred)
        - map(map(list, f), g) → map(list, composed(f, g))
        """
        new_decls: list[Declaration] = []
        for decl in module.declarations:
            if isinstance(decl, FunctionDef):
                new_decls.append(self._fuse_iterators_in_func(decl))
            elif isinstance(decl, MainDef):
                new_body = [self._fuse_iterators_in_stmt(s) for s in decl.body]
                new_body = self._fuse_multi_reduce(new_body)
                new_decls.append(replace(decl, body=new_body))
            elif isinstance(decl, ModuleDecl):
                new_body = [
                    self._fuse_iterators_in_func(d) if isinstance(d, FunctionDef) else d
                    for d in decl.body
                ]
                new_decls.append(replace(decl, body=new_body))
            else:
                new_decls.append(decl)
        return replace(module, declarations=new_decls)

    def _fuse_iterators_in_func(self, fd: FunctionDef) -> FunctionDef:
        """Apply iterator fusion within a function body."""
        new_body = [self._fuse_iterators_in_stmt(s) for s in fd.body]
        new_body = self._fuse_multi_reduce(new_body)
        return replace(fd, body=new_body)

    @staticmethod
    def _is_reduce_on(stmt: Any) -> str | None:
        """If stmt is VarDecl with reduce(ident, init, lambda), return the list ident name."""
        if not isinstance(stmt, VarDecl):
            return None
        val = stmt.value
        if not isinstance(val, CallExpr):
            return None
        if not isinstance(val.func, IdentifierExpr):
            return None
        if val.func.name != "reduce" or len(val.args) != 3:
            return None
        # The lambda must be a LambdaExpr with 2 params for safe fusion
        if not isinstance(val.args[2], LambdaExpr) or len(val.args[2].params) != 2:
            return None
        # List arg must be a simple identifier (same variable reference)
        if isinstance(val.args[0], IdentifierExpr):
            return val.args[0].name
        return None

    def _fuse_multi_reduce(self, stmts: list[Any]) -> list[Any]:
        """Fuse consecutive reduce() calls on the same list into one loop."""
        result: list[Any] = []
        i = 0
        while i < len(stmts):
            list_name = self._is_reduce_on(stmts[i])
            if list_name is None:
                result.append(stmts[i])
                i += 1
                continue

            # Collect consecutive reduces on the same list
            group = [stmts[i]]
            j = i + 1
            while j < len(stmts) and self._is_reduce_on(stmts[j]) == list_name:
                group.append(stmts[j])
                j += 1

            if len(group) < 2:
                # Only one reduce — no fusion benefit
                result.append(stmts[i])
                i += 1
                continue

            # Build fused call: __fused_multi_reduce(list, name1, init1, lam1, name2, ...)
            first = group[0]
            call = first.value  # the reduce CallExpr
            span = call.span
            fused_args: list[Expr] = [call.args[0]]  # shared list arg
            for stmt in group:
                rcall = stmt.value
                fused_args.append(StringLit(value=stmt.name, span=span))
                fused_args.append(rcall.args[1])  # init
                fused_args.append(rcall.args[2])  # lambda

            fused_call = CallExpr(
                func=IdentifierExpr(name="__fused_multi_reduce", span=span),
                args=fused_args,
                span=span,
            )
            # First VarDecl carries the fused call; rest become no-op refs
            result.append(replace(first, value=fused_call))
            for k, stmt in enumerate(group[1:], 1):
                ref_call = CallExpr(
                    func=IdentifierExpr(name="__fused_multi_reduce_ref", span=span),
                    args=[IntegerLit(value=k, span=span)],
                    span=span,
                )
                result.append(replace(stmt, value=ref_call))
            i = j

        return result

    def _fuse_iterators_in_stmt(self, stmt: Any) -> Any:
        """Apply iterator fusion within a statement."""
        if isinstance(stmt, VarDecl):
            new_val = self._fuse_iterators_in_expr(stmt.value)
            if new_val is not stmt.value:
                return replace(stmt, value=new_val)
        elif isinstance(stmt, ExprStmt):
            new_expr = self._fuse_iterators_in_expr(stmt.expr)
            if new_expr is not stmt.expr:
                return replace(stmt, expr=new_expr)
        elif isinstance(stmt, MatchExpr):
            new_arms = []
            for arm in stmt.arms:
                new_arm_body = [self._fuse_iterators_in_stmt(s) for s in arm.body]
                new_arm_body = self._fuse_multi_reduce(new_arm_body)
                new_arms.append(replace(arm, body=new_arm_body))
            new_subj = self._fuse_iterators_in_expr(stmt.subject) if stmt.subject else None
            return replace(stmt, arms=new_arms, subject=new_subj)
        return stmt

    def _fuse_iterators_in_expr(self, expr: Expr) -> Expr:
        """Detect and fuse chained HOF calls in an expression."""
        if not isinstance(expr, CallExpr):
            if isinstance(expr, PipeExpr):
                new_left = self._fuse_iterators_in_expr(expr.left)
                new_right = self._fuse_iterators_in_expr(expr.right)
                if new_left is not expr.left or new_right is not expr.right:
                    return replace(expr, left=new_left, right=new_right)
            if isinstance(expr, BinaryExpr):
                new_left = self._fuse_iterators_in_expr(expr.left)
                new_right = self._fuse_iterators_in_expr(expr.right)
                if new_left is not expr.left or new_right is not expr.right:
                    return replace(expr, left=new_left, right=new_right)
            return expr

        func = expr.func
        if not isinstance(func, IdentifierExpr):
            return expr

        outer_name = func.name
        args = expr.args

        # Recursively fuse nested args first
        new_args = [self._fuse_iterators_in_expr(a) for a in args]
        if any(na is not oa for na, oa in zip(new_args, args)):
            expr = replace(expr, args=new_args)
            args = new_args

        # map(map(list, f), g) → map(list, composed(f, g))
        if outer_name == "map" and len(args) == 2:
            inner = args[0]
            if (
                isinstance(inner, CallExpr)
                and isinstance(inner.func, IdentifierExpr)
                and inner.func.name == "map"
                and len(inner.args) == 2
            ):
                list_arg = inner.args[0]
                f = inner.args[1]
                g = args[1]
                # Compose: \x -> g(f(x))
                if isinstance(f, LambdaExpr) and isinstance(g, LambdaExpr):
                    # compose lambdas: \x -> g_body[g_param -> f_body[f_param -> x]]
                    composed = LambdaExpr(
                        params=f.params,
                        body=CallExpr(
                            func=g.func
                            if isinstance(g.func, IdentifierExpr)
                            else IdentifierExpr(name="__composed", span=expr.span),
                            args=[
                                CallExpr(
                                    func=f.func
                                    if isinstance(f.func, IdentifierExpr)
                                    else IdentifierExpr(name="__inner", span=expr.span),
                                    args=[IdentifierExpr(name=f.params[0], span=expr.span)],
                                    span=expr.span,
                                )
                            ]
                            if isinstance(f, LambdaExpr) and len(f.params) == 1
                            else [f],
                            span=expr.span,
                        ),
                        span=expr.span,
                    )
                    return CallExpr(
                        func=IdentifierExpr(name="map", span=expr.span),
                        args=[list_arg, composed],
                        span=expr.span,
                    )
                # Non-lambda case: mark as fused for emitter
                return CallExpr(
                    func=IdentifierExpr(name="__fused_map_map", span=expr.span),
                    args=[list_arg, f, g],
                    span=expr.span,
                )

        # map(filter(list, pred), func) → fused single pass
        if outer_name == "map" and len(args) == 2:
            inner = args[0]
            if (
                isinstance(inner, CallExpr)
                and isinstance(inner.func, IdentifierExpr)
                and inner.func.name == "filter"
                and len(inner.args) == 2
            ):
                list_arg = inner.args[0]
                pred = inner.args[1]
                func_arg = args[1]
                return CallExpr(
                    func=IdentifierExpr(name="__fused_map_filter", span=expr.span),
                    args=[list_arg, pred, func_arg],
                    span=expr.span,
                )

        # filter(map(list, func), pred) → fused single pass
        if outer_name == "filter" and len(args) == 2:
            inner = args[0]
            if (
                isinstance(inner, CallExpr)
                and isinstance(inner.func, IdentifierExpr)
                and inner.func.name == "map"
                and len(inner.args) == 2
            ):
                list_arg = inner.args[0]
                func_arg = inner.args[1]
                pred = args[1]
                return CallExpr(
                    func=IdentifierExpr(name="__fused_filter_map", span=expr.span),
                    args=[list_arg, func_arg, pred],
                    span=expr.span,
                )
            if (
                isinstance(inner, CallExpr)
                and isinstance(inner.func, IdentifierExpr)
                and inner.func.name == "filter"
                and len(inner.args) == 2
            ):
                list_arg = inner.args[0]
                p1 = inner.args[1]
                p2 = args[1]
                return CallExpr(
                    func=IdentifierExpr(name="__fused_filter_filter", span=expr.span),
                    args=[list_arg, p1, p2],
                    span=expr.span,
                )

        # reduce(map(list, f), init, g) → fused single pass
        if outer_name == "reduce" and len(args) == 3:
            inner = args[0]
            if (
                isinstance(inner, CallExpr)
                and isinstance(inner.func, IdentifierExpr)
                and inner.func.name == "map"
                and len(inner.args) == 2
            ):
                list_arg = inner.args[0]
                func_arg = inner.args[1]
                init = args[1]
                reducer = args[2]
                return CallExpr(
                    func=IdentifierExpr(name="__fused_reduce_map", span=expr.span),
                    args=[list_arg, func_arg, init, reducer],
                    span=expr.span,
                )
            if (
                isinstance(inner, CallExpr)
                and isinstance(inner.func, IdentifierExpr)
                and inner.func.name == "filter"
                and len(inner.args) == 2
            ):
                list_arg = inner.args[0]
                pred = inner.args[1]
                init = args[1]
                reducer = args[2]
                return CallExpr(
                    func=IdentifierExpr(name="__fused_reduce_filter", span=expr.span),
                    args=[list_arg, pred, init, reducer],
                    span=expr.span,
                )

        # each(map(list, f), g) → fused single pass
        if outer_name == "each" and len(args) == 2:
            inner = args[0]
            if (
                isinstance(inner, CallExpr)
                and isinstance(inner.func, IdentifierExpr)
                and inner.func.name == "map"
                and len(inner.args) == 2
            ):
                list_arg = inner.args[0]
                func_arg = inner.args[1]
                consumer = args[1]
                return CallExpr(
                    func=IdentifierExpr(name="__fused_each_map", span=expr.span),
                    args=[list_arg, func_arg, consumer],
                    span=expr.span,
                )
            if (
                isinstance(inner, CallExpr)
                and isinstance(inner.func, IdentifierExpr)
                and inner.func.name == "filter"
                and len(inner.args) == 2
            ):
                list_arg = inner.args[0]
                pred = inner.args[1]
                consumer = args[1]
                return CallExpr(
                    func=IdentifierExpr(name="__fused_each_filter", span=expr.span),
                    args=[list_arg, pred, consumer],
                    span=expr.span,
                )

        return expr

    # ── Pass 2d: Copy Elision ────────────────────────────────────────

    def _copy_elision(self, module: Module) -> Module:
        """Mark last-use variables for move semantics instead of copy.

        Performs simple liveness analysis per function: if a variable is used
        exactly once after its definition, mark the use as a move (no copy
        needed). This is recorded as an annotation on the AST node.
        """
        new_decls: list[Declaration] = []
        for decl in module.declarations:
            if isinstance(decl, FunctionDef):
                new_decls.append(self._elide_copies_in_func(decl))
            elif isinstance(decl, MainDef):
                new_body = self._mark_last_uses(decl.body)
                new_decls.append(replace(decl, body=new_body))
            elif isinstance(decl, ModuleDecl):
                new_body = [
                    self._elide_copies_in_func(d) if isinstance(d, FunctionDef) else d
                    for d in decl.body
                ]
                new_decls.append(replace(decl, body=new_body))
            else:
                new_decls.append(decl)
        return replace(module, declarations=new_decls)

    def _elide_copies_in_func(self, fd: FunctionDef) -> FunctionDef:
        """Mark last-use identifiers in a function body."""
        new_body = self._mark_last_uses(fd.body)
        return replace(fd, body=new_body)

    def _mark_last_uses(self, stmts: list[Any]) -> list[Any]:
        """Analyze variable usage and mark last uses for move semantics.

        Walk the statement list backwards to find last uses of locally-defined
        variables. When a variable's last use is as a function argument or
        assignment source, mark it for move semantics.
        """
        # Collect locally defined variable names
        local_defs: set[str] = set()
        for stmt in stmts:
            if isinstance(stmt, VarDecl):
                local_defs.add(stmt.name)

        if not local_defs:
            return stmts

        # Count uses of each local in the body
        use_counts: dict[str, int] = {n: 0 for n in local_defs}
        for stmt in stmts:
            self._count_uses_in_stmt(stmt, use_counts)

        # For variables used exactly once: the single use is the last use,
        # which can be a move instead of a copy. We record this in the
        # module's elision set for the emitter to use.
        for name, count in use_counts.items():
            if count == 1:
                self._elision_candidates.add(name)

        return stmts

    def _count_uses_in_stmt(self, stmt: Any, counts: dict[str, int]) -> None:
        """Count uses of tracked variables in a statement."""
        if isinstance(stmt, VarDecl):
            self._count_uses_in_expr(stmt.value, counts)
        elif isinstance(stmt, ExprStmt):
            self._count_uses_in_expr(stmt.expr, counts)
        elif isinstance(stmt, Assignment):
            self._count_uses_in_expr(stmt.value, counts)
        elif isinstance(stmt, MatchExpr):
            if stmt.subject:
                self._count_uses_in_expr(stmt.subject, counts)
            for arm in stmt.arms:
                for s in arm.body:
                    self._count_uses_in_stmt(s, counts)

    def _count_uses_in_expr(self, expr: Expr, counts: dict[str, int]) -> None:
        """Count uses of tracked variables in an expression."""
        if isinstance(expr, IdentifierExpr):
            if expr.name in counts:
                counts[expr.name] += 1
        elif isinstance(expr, CallExpr):
            for arg in expr.args:
                self._count_uses_in_expr(arg, counts)
        elif isinstance(expr, BinaryExpr):
            self._count_uses_in_expr(expr.left, counts)
            self._count_uses_in_expr(expr.right, counts)
        elif isinstance(expr, UnaryExpr):
            self._count_uses_in_expr(expr.operand, counts)
        elif isinstance(expr, PipeExpr):
            self._count_uses_in_expr(expr.left, counts)
            self._count_uses_in_expr(expr.right, counts)
        elif isinstance(expr, FailPropExpr):
            self._count_uses_in_expr(expr.expr, counts)

    # ── Pass 2b: Dead Code Elimination ─────────────────────────────

    def _dead_code_elimination(self, module: Module) -> Module:
        """Remove unused functions - those never called from reachable code."""
        reachable = self._find_reachable_functions(module)
        if not reachable:
            return module
        new_decls: list[Declaration] = []
        for decl in module.declarations:
            if isinstance(decl, FunctionDef):
                # streams functions are blocking IO entry points — never dead
                if decl.name in reachable or decl.verb == "streams":
                    new_decls.append(decl)
            elif isinstance(decl, MainDef):
                new_decls.append(decl)
            elif isinstance(decl, ModuleDecl):
                new_decls.append(decl)
            else:
                new_decls.append(decl)
        return replace(module, declarations=new_decls)

    def _find_reachable_functions(self, module: Module) -> set[str]:
        """Find all functions that are reachable from main or module exports."""
        reachable: set[str] = set()
        worklist: list[str] = []
        func_defs: dict[str, FunctionDef] = {}
        main_def: MainDef | None = None
        for decl in module.declarations:
            if isinstance(decl, MainDef):
                main_def = decl
                worklist.append("main")
            elif isinstance(decl, FunctionDef):
                func_defs[decl.name] = decl
        while worklist:
            func_name = worklist.pop()
            if func_name in reachable:
                continue
            reachable.add(func_name)
            if func_name == "main" and main_def is not None:
                called = self._find_called_functions(main_def.body)
            elif func_name in func_defs:
                called = self._find_called_functions(func_defs[func_name].body)
            else:
                continue
            for called_name in called:
                if called_name not in reachable:
                    worklist.append(called_name)
        return reachable

    def _find_called_functions(self, stmts: list[Any]) -> set[str]:
        """Find all function names called in the given statements."""
        called: set[str] = set()
        for stmt in stmts:
            self._find_called_in_stmt(stmt, called)
        return called

    def _find_called_in_stmt(self, stmt: Any, called: set[str]) -> None:
        """Recursively find function calls in a statement."""
        if isinstance(stmt, ExprStmt):
            self._find_called_in_expr(stmt.expr, called)
        elif isinstance(stmt, MatchExpr):
            for arm in stmt.arms:
                if arm.body:
                    for body_stmt in arm.body:
                        self._find_called_in_stmt(body_stmt, called)
        elif isinstance(stmt, TailLoop):
            self._find_called_in_stmts(stmt.body, called)
        elif isinstance(stmt, TailContinue):
            for _, expr in stmt.assignments:
                self._find_called_in_expr(expr, called)
        elif isinstance(stmt, WhileLoop):
            self._find_called_in_expr(stmt.break_cond, called)
            self._find_called_in_stmts(stmt.body, called)
        elif isinstance(stmt, VarDecl):
            self._find_called_in_expr(stmt.value, called)
        elif isinstance(stmt, Assignment):
            self._find_called_in_expr(stmt.value, called)

    def _find_called_in_stmts(self, stmts: list[Any], called: set[str]) -> None:
        for stmt in stmts:
            self._find_called_in_stmt(stmt, called)

    def _find_called_in_expr(self, expr: Expr, called: set[str]) -> None:
        """Recursively find function calls in an expression."""
        if isinstance(expr, CallExpr):
            if isinstance(expr.func, IdentifierExpr):
                called.add(expr.func.name)
            else:
                self._find_called_in_expr(expr.func, called)
            for arg in expr.args:
                self._find_called_in_expr(arg, called)
        elif isinstance(expr, FieldExpr):
            self._find_called_in_expr(expr.obj, called)
        elif isinstance(expr, IndexExpr):
            self._find_called_in_expr(expr.obj, called)
            self._find_called_in_expr(expr.index, called)
        elif isinstance(expr, MatchExpr):
            if expr.subject:
                self._find_called_in_expr(expr.subject, called)
            for arm in expr.arms:
                if arm.body:
                    for body_stmt in arm.body:
                        self._find_called_in_stmt(body_stmt, called)
        elif isinstance(expr, BinaryExpr):
            self._find_called_in_expr(expr.left, called)
            self._find_called_in_expr(expr.right, called)
        elif isinstance(expr, UnaryExpr):
            self._find_called_in_expr(expr.operand, called)
        elif isinstance(expr, PipeExpr):
            self._find_called_in_expr(expr.left, called)
            self._find_called_in_expr(expr.right, called)
        elif isinstance(expr, LambdaExpr):
            self._find_called_in_expr(expr.body, called)
        elif isinstance(expr, StringInterp):
            for part in expr.parts:
                self._find_called_in_expr(part, called)
        elif isinstance(expr, ListLiteral):
            for elem in expr.elements:
                self._find_called_in_expr(elem, called)
        elif isinstance(expr, VarDecl):
            self._find_called_in_expr(expr.value, called)
        elif isinstance(expr, FailPropExpr):
            self._find_called_in_expr(expr.expr, called)

    # ── Pass 3: Small Function Inlining ───────────────────────────

    @staticmethod
    def _is_runtime_lookup(fd: FunctionDef) -> bool:
        """Check if function body is a runtime binary lookup (not safe to inline)."""
        from prove.ast_nodes import LookupAccessExpr

        if len(fd.body) != 1:
            return False
        stmt = fd.body[0]
        if not isinstance(stmt, ExprStmt):
            return False
        expr = stmt.expr
        if not isinstance(expr, LookupAccessExpr):
            return False
        # Runtime lookup: operand is a param identifier, not a literal
        return isinstance(expr.operand, IdentifierExpr)

    def _inline_small_functions(self, module: Module) -> Module:
        """Inline pure single-expression functions at call sites."""
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
                    and not decl.requires
                    and not decl.ensures
                    and not self._is_runtime_lookup(decl)
                ):
                    candidates[decl.name] = decl
                # Always inline single-return validators (inputs with can_fail)
                # Their return type already encodes the contract (Option<Value>!, Result<Value, Error>!)
                # But only if no explicit contracts - let those be explicit
                elif (
                    decl.verb == "inputs"
                    and len(decl.body) == 1
                    and decl.can_fail
                    and not decl.binary
                    and decl.terminates is None
                    and not self._calls_self(decl.name, decl.body)
                    and not decl.requires
                    and not decl.ensures
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
                            and not inner.requires
                            and not inner.ensures
                            and not self._is_runtime_lookup(inner)
                        ):
                            candidates[inner.name] = inner
                        # Always inline single-return validators
                        elif (
                            inner.verb == "inputs"
                            and len(inner.body) == 1
                            and inner.can_fail
                            and not inner.binary
                            and inner.terminates is None
                            and not self._calls_self(inner.name, inner.body)
                            and not inner.requires
                            and not inner.ensures
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
                    if isinstance(d, FunctionDef)
                    else d
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
        if isinstance(stmt, WhileLoop):
            return replace(
                stmt,
                break_cond=self._inline_in_expr(stmt.break_cond, candidates),
                body=self._inline_stmts(stmt.body, candidates),
            )
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
                        body_expr.expr,
                        fd.params,
                        expr.args,
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
        self,
        expr: Expr,
        params: list[Any],
        args: list[Expr],
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
                expr,
                operand=self._substitute_params(expr.operand, params, args),
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
                        new_body.append(
                            replace(
                                s,
                                expr=self._substitute_params(s.expr, params, args),
                            )
                        )
                    else:
                        new_body.append(s)
                new_arms.append(replace(arm, body=new_body))
            subj = self._substitute_params(expr.subject, params, args) if expr.subject else None
            return replace(expr, subject=subj, arms=new_arms)

        return expr

    # ── Pass 3b: TCO Loop Inlining ────────────────────────────────

    def _inline_tco_calls(self, module: Module) -> Module:
        """Inline calls to simple TCO'd loop functions within TailContinue nodes.

        Detects tail-recursive functions whose body is a single TailLoop over a
        two-arm match (base-case return + recursive TailContinue). When such a
        function is called inside another function's TailContinue assignment,
        replace it with inline VarDecl(s) + WhileLoop, eliminating the call
        overhead from inside the hot loop.
        """
        candidates: dict[str, FunctionDef] = {}
        for decl in module.declarations:
            if isinstance(decl, FunctionDef) and self._is_tco_loop_candidate(decl):
                candidates[decl.name] = decl
        if not candidates:
            return module

        new_decls: list[Declaration] = []
        for decl in module.declarations:
            if isinstance(decl, FunctionDef):
                new_body = self._tco_inline_stmts(decl.body, candidates)
                new_decls.append(replace(decl, body=new_body))
            elif isinstance(decl, MainDef):
                new_body = self._tco_inline_stmts(decl.body, candidates)
                new_decls.append(replace(decl, body=new_body))
            else:
                new_decls.append(decl)
        return replace(module, declarations=new_decls)

    @staticmethod
    def _is_tco_loop_candidate(fd: FunctionDef) -> bool:
        """Return True if fd is a simple TCO'd loop: body=[TailLoop([MatchExpr(2 arms)])]."""
        if len(fd.body) != 1 or not isinstance(fd.body[0], TailLoop):
            return False
        tl = fd.body[0]
        if len(tl.body) != 1 or not isinstance(tl.body[0], MatchExpr):
            return False
        m = tl.body[0]
        if not m.subject or len(m.arms) != 2:
            return False
        # One arm must return an identifier (base), other must TailContinue (recursive)
        has_base = any(
            arm.body
            and isinstance(arm.body[-1], ExprStmt)
            and isinstance(arm.body[-1].expr, IdentifierExpr)
            for arm in m.arms
        )
        has_rec = any(arm.body and isinstance(arm.body[-1], TailContinue) for arm in m.arms)
        return has_base and has_rec

    def _tco_inline_stmts(self, stmts: list[Any], candidates: dict[str, FunctionDef]) -> list[Any]:
        """Recursively apply TCO call inlining to a statement list."""
        result: list[Any] = []
        for stmt in stmts:
            result.extend(self._tco_inline_stmt(stmt, candidates))
        return result

    def _tco_inline_stmt(self, stmt: Any, candidates: dict[str, FunctionDef]) -> list[Any]:
        """Try to inline TCO calls in a statement; return list of replacement stmts."""
        if isinstance(stmt, TailContinue):
            return self._tco_inline_tail_continue(stmt, candidates)
        if isinstance(stmt, TailLoop):
            return [replace(stmt, body=self._tco_inline_stmts(stmt.body, candidates))]
        if isinstance(stmt, MatchExpr):
            new_arms = []
            for arm in stmt.arms:
                new_body = self._tco_inline_stmts(arm.body, candidates)
                new_arms.append(replace(arm, body=new_body))
            return [replace(stmt, arms=new_arms)]
        if isinstance(stmt, ExprStmt) and isinstance(stmt.expr, MatchExpr):
            new_arms = []
            for arm in stmt.expr.arms:
                new_body = self._tco_inline_stmts(arm.body, candidates)
                new_arms.append(replace(arm, body=new_body))
            return [replace(stmt, expr=replace(stmt.expr, arms=new_arms))]
        return [stmt]

    def _tco_inline_tail_continue(
        self, tc: TailContinue, candidates: dict[str, FunctionDef]
    ) -> list[Any]:
        """If any TailContinue assignment calls a TCO candidate, inline its loop."""
        # Find one inlineable call (take only the first to keep things simple)
        inline_idx = -1
        for i, (_, expr) in enumerate(tc.assignments):
            if (
                isinstance(expr, CallExpr)
                and isinstance(expr.func, IdentifierExpr)
                and expr.func.name in candidates
            ):
                inline_idx = i
                break
        if inline_idx == -1:
            return [tc]

        param_name, call_expr = tc.assignments[inline_idx]
        assert isinstance(call_expr, CallExpr) and isinstance(call_expr.func, IdentifierExpr)
        fname = call_expr.func.name
        fd = candidates[fname]
        tl = fd.body[0]
        assert isinstance(tl, TailLoop)
        m = tl.body[0]
        assert isinstance(m, MatchExpr)

        # Identify base arm and recursive arm
        base_arm = next(
            arm
            for arm in m.arms
            if arm.body
            and isinstance(arm.body[-1], ExprStmt)
            and isinstance(arm.body[-1].expr, IdentifierExpr)
        )
        rec_arm = next(
            arm for arm in m.arms if arm.body and isinstance(arm.body[-1], TailContinue)
        )
        rec_tc: TailContinue = rec_arm.body[-1]  # type: ignore[assignment]

        # Map formal params to actual args
        actual_args = call_expr.args
        if len(actual_args) != len(tl.params):
            return [tc]  # mismatch — bail
        param_to_arg: dict[str, Any] = dict(zip(tl.params, actual_args))

        # Classify params from the recursive TailContinue:
        #   constant    — new value is IdentExpr(self): pass actual arg through unchanged
        #   effect      — new value is CallExpr(_, [IdentExpr(self), ...]): in-place side effect;
        #                  emit as ExprStmt, no fresh var needed, pass actual arg through
        #   induction   — everything else: genuine value change, needs a fresh loop var
        constant_params: set[str] = set()
        effect_params: set[str] = set()   # inner_p → CallExpr whose first arg == IdentExpr(inner_p)
        induction_params: list[str] = []
        for inner_p, new_val in rec_tc.assignments:
            if isinstance(new_val, IdentifierExpr) and new_val.name == inner_p:
                constant_params.add(inner_p)
            elif (
                isinstance(new_val, CallExpr)
                and new_val.args
                and isinstance(new_val.args[0], IdentifierExpr)
                and new_val.args[0].name == inner_p
            ):
                effect_params.add(inner_p)
            else:
                induction_params.append(inner_p)

        # Create fresh variable names for pure induction params only
        fresh: dict[str, str] = {}
        for p in induction_params:
            fresh[p] = f"_il_{p}"

        # Build substitution: fresh var for induction, actual arg for constant/effect
        def subst_expr(expr: Any) -> Any:
            if isinstance(expr, IdentifierExpr):
                if expr.name in fresh:
                    return replace(expr, name=fresh[expr.name])
                if expr.name in param_to_arg:
                    return param_to_arg[expr.name]
                return expr
            if isinstance(expr, CallExpr):
                return replace(
                    expr,
                    func=subst_expr(expr.func),
                    args=[subst_expr(a) for a in expr.args],
                )
            if isinstance(expr, BinaryExpr):
                return replace(
                    expr,
                    left=subst_expr(expr.left),
                    right=subst_expr(expr.right),
                )
            if isinstance(expr, UnaryExpr):
                return replace(expr, operand=subst_expr(expr.operand))
            return expr

        # Determine break condition from base arm pattern + match subject
        base_pattern = base_arm.pattern
        raw_cond = subst_expr(m.subject)
        if isinstance(base_pattern, LiteralPattern) and base_pattern.value == "false":
            # Base arm fires when subject is False → break when False
            break_cond = UnaryExpr(op="!", operand=raw_cond, span=m.span)
        else:
            # Base arm fires when subject is True (or wildcard) → break when True
            break_cond = raw_cond

        # Build while-loop body
        loop_body: list[Any] = []
        # Any non-TailContinue stmts in the recursive arm first (rare)
        for s in rec_arm.body[:-1]:
            if isinstance(s, ExprStmt):
                loop_body.append(replace(s, expr=subst_expr(s.expr)))
            else:
                loop_body.append(s)
        # Effect params: emit their call as a bare ExprStmt (mutation; result discarded)
        for inner_p, new_val in rec_tc.assignments:
            if inner_p in effect_params:
                loop_body.append(ExprStmt(expr=subst_expr(new_val), span=rec_tc.span))
        # Induction params: update the fresh loop var
        for inner_p, new_val in rec_tc.assignments:
            if inner_p in induction_params:
                loop_body.append(
                    Assignment(
                        target=fresh[inner_p],
                        value=subst_expr(new_val),
                        span=rec_tc.span,
                    )
                )

        span = m.span

        # VarDecl for each induction param (initialized to the actual arg)
        prepend: list[Any] = []
        for p in induction_params:
            prepend.append(
                VarDecl(name=fresh[p], type_expr=None, value=param_to_arg[p], span=span)
            )

        while_loop = WhileLoop(break_cond=break_cond, body=loop_body, span=span)

        # Result of the inlined call is the "result param" named in the base arm's ExprStmt
        result_param_name: str = base_arm.body[-1].expr.name  # type: ignore[union-attr]
        if result_param_name in fresh:
            result_expr: Any = IdentifierExpr(name=fresh[result_param_name], span=span)
        else:
            # constant or effect param — use the actual arg directly
            result_expr = param_to_arg.get(
                result_param_name, IdentifierExpr(name=result_param_name, span=span)
            )

        # Rebuild TailContinue with inlined result replacing the call
        new_assignments = list(tc.assignments)
        new_assignments[inline_idx] = (param_name, result_expr)
        new_tc = replace(tc, assignments=new_assignments)

        return [*prepend, while_loop, new_tc]

    # ── Pass 3c: Memoization Candidate Identification ─────────────

    def _identify_memoization_candidates(self, module: Module) -> Module:
        """Identify pure functions eligible for memoization.

        Candidates are pure verbs (transforms, validates, reads, creates, matches)
        that are small and don't have side effects. Memoization allows caching
        results based on input parameters.
        """
        _pure_verbs = {"transforms", "validates", "reads", "creates", "matches"}

        for decl in module.declarations:
            if isinstance(decl, FunctionDef):
                self._check_function_for_memoization(decl, _pure_verbs)
            elif isinstance(decl, ModuleDecl):
                for inner in decl.body:
                    if isinstance(inner, FunctionDef):
                        self._check_function_for_memoization(inner, _pure_verbs)

        return module

    def _check_function_for_memoization(self, fd: FunctionDef, pure_verbs: set[str]) -> None:
        """Check if a function is a memoization candidate."""
        if fd.verb not in pure_verbs:
            return
        if fd.binary:
            return
        if fd.terminates is not None:
            return
        if len(fd.params) > 4:
            return
        if len(fd.body) > 10:
            return
        if self._calls_self(fd.name, fd.body):
            return
        if self._has_side_effects(fd):
            return

        sig = self._symbols.resolve_function(fd.verb, fd.name, len(fd.params))
        if sig is None or not sig.param_types:
            return

        param_type_strs = tuple(self._type_key(pt) for pt in sig.param_types)

        cand = MemoizationCandidate(
            name=fd.name,
            verb=fd.verb,
            param_count=len(fd.params),
            body_size=len(fd.body),
            param_types=param_type_strs,
        )
        self._memo_info.add_candidate(cand)

    def _type_key(self, typ: Any) -> str:
        """Get a string key for a type for hashing."""
        from prove.types import (
            GenericInstance,
            PrimitiveType,
            RecordType,
        )

        if isinstance(typ, PrimitiveType):
            return typ.name
        if isinstance(typ, RecordType):
            return f"record:{typ.name}"
        if isinstance(typ, GenericInstance):
            args = "_".join(self._type_key(a) for a in typ.args) if typ.args else ""
            return f"{typ.base_name}:{args}"
        return "unknown"

    def _has_side_effects(self, fd: FunctionDef) -> bool:
        """Check if a function has potential side effects (returns True if it does)."""
        for stmt in fd.body:
            if self._stmt_has_side_effects(stmt):
                return True
        return False

    def _stmt_has_side_effects(self, stmt: Any) -> bool:
        """Check if a statement has side effects (returns True if it does)."""
        if isinstance(stmt, ExprStmt):
            return self._expr_has_side_effects(stmt.expr)
        if isinstance(stmt, Assignment):
            return self._expr_has_side_effects(stmt.value)
        if isinstance(stmt, VarDecl):
            if stmt.value:
                return self._expr_has_side_effects(stmt.value)
        if isinstance(stmt, MatchExpr):
            if stmt.subject and self._expr_has_side_effects(stmt.subject):
                return True
            for arm in stmt.arms:
                for b in arm.body:
                    if self._stmt_has_side_effects(b):
                        return True
        return False

    def _expr_has_side_effects(self, expr: Expr) -> bool:
        """Check if an expression has side effects (returns True if it does)."""
        from prove.ast_nodes import (
            BinaryExpr,
            FailPropExpr,
            LambdaExpr,
            PipeExpr,
            UnaryExpr,
        )

        if isinstance(expr, CallExpr):
            return False
        if isinstance(expr, BinaryExpr):
            return self._expr_has_side_effects(expr.left) or self._expr_has_side_effects(expr.right)
        if isinstance(expr, UnaryExpr):
            return self._expr_has_side_effects(expr.operand)
        if isinstance(expr, PipeExpr):
            return self._expr_has_side_effects(expr.left) or self._expr_has_side_effects(expr.right)
        if isinstance(expr, FailPropExpr):
            return self._expr_has_side_effects(expr.expr)
        if isinstance(expr, LambdaExpr):
            return False
        if isinstance(expr, MatchExpr):
            if expr.subject and self._expr_has_side_effects(expr.subject):
                return True
            for arm in expr.arms:
                for s in arm.body:
                    if isinstance(s, ExprStmt) and self._expr_has_side_effects(s.expr):
                        return True
        return False

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
                    if isinstance(d, FunctionDef)
                    else d
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

    # ── Pass 5: Escape Analysis ─────────────────────────────────────

    PURE_FUNCTIONS: frozenset[str] = frozenset(
        {
            "string.length",
            "string.is_empty",
            "string.to_upper",
            "string.to_lower",
            "string.trim",
            "string.reverse",
            "list.length",
            "list.is_empty",
            "list.first",
            "list.last",
            "list.sum",
            "list.product",
            "table.length",
        }
    )

    def _escape_analysis(self, module: Module) -> Module:
        """Analyze which values escape their enclosing function.

        A value escapes if:
        1. It's returned from the function
        2. It's stored in a mutable parameter
        3. It's stored in a global/module variable
        4. It's passed to a function that may store it beyond current scope

        Conservative: defaults to escaping if uncertain.
        """
        for decl in module.declarations:
            if isinstance(decl, FunctionDef):
                self._analyze_function_escape(decl.name, decl.params, decl.body)
            elif isinstance(decl, MainDef):
                self._analyze_function_escape("main", [], decl.body)
            elif isinstance(decl, ModuleDecl):
                for item in decl.body:
                    if isinstance(item, FunctionDef):
                        self._analyze_function_escape(item.name, item.params, item.body)
        return module

    def _analyze_function_escape(
        self,
        func_name: str,
        params: list[Any],
        body: list[Any],
    ) -> None:
        local_vars: set[str] = set()
        self._collect_local_vars(body, local_vars)

        param_names = {p.name for p in params}

        self._check_escapes_in_body(func_name, body, local_vars, param_names)

    def _collect_local_vars(self, body: list[Any], vars_set: set[str]) -> None:
        for stmt in body:
            if isinstance(stmt, VarDecl):
                vars_set.add(stmt.name)
            elif hasattr(stmt, "body"):
                if isinstance(stmt, (MatchExpr,)):
                    for arm in getattr(stmt, "arms", []):
                        self._collect_local_vars(arm.body, vars_set)
                elif isinstance(stmt, list):
                    self._collect_local_vars(stmt, vars_set)

    def _check_escapes_in_body(
        self,
        func_name: str,
        body: list[Any],
        local_vars: set[str],
        param_names: set[str],
    ) -> None:
        for stmt in body:
            self._check_stmt_escape(func_name, stmt, local_vars, param_names)

    def _check_stmt_escape(
        self,
        func_name: str,
        stmt: Any,
        local_vars: set[str],
        param_names: set[str],
    ) -> None:
        if isinstance(stmt, VarDecl):
            if stmt.value:
                self._check_expr_escape(func_name, stmt.value, local_vars, param_names)
        elif isinstance(stmt, Assignment):
            self._check_assignment_escape(func_name, stmt, local_vars, param_names)
        elif isinstance(stmt, ExprStmt):
            self._check_expr_escape(func_name, stmt.expr, local_vars, param_names)
        elif isinstance(stmt, MatchExpr):
            for arm in stmt.arms:
                self._check_escapes_in_body(func_name, arm.body, local_vars, param_names)

    def _check_assignment_escape(
        self,
        func_name: str,
        assignment: Assignment,
        local_vars: set[str],
        param_names: set[str],
    ) -> None:
        target = assignment.target
        if isinstance(target, IdentifierExpr):
            target_name = target.name
            if target_name in param_names:
                if assignment.value:
                    self._check_expr_escape(func_name, assignment.value, local_vars, param_names)

    def _check_expr_escape(
        self,
        func_name: str,
        expr: Any,
        local_vars: set[str],
        param_names: set[str],
    ) -> None:
        if isinstance(expr, CallExpr):
            func_expr = expr.func
            if isinstance(func_expr, IdentifierExpr):
                func_ref = func_expr.name
                for arg in expr.args:
                    if isinstance(arg, IdentifierExpr) and arg.name in local_vars:
                        full_func = f"{func_name}.{func_ref}"
                        if not self._is_pure_function(full_func):
                            self._escape_info.mark_escapes(func_name, arg.name)
            for arg in expr.args:
                self._check_expr_escape(func_name, arg, local_vars, param_names)
        elif isinstance(expr, IdentifierExpr):
            pass
        elif hasattr(expr, "elements"):
            for elem in getattr(expr, "elements", []):
                self._check_expr_escape(func_name, elem, local_vars, param_names)
        elif hasattr(expr, "body"):
            if isinstance(expr, MatchExpr):
                for arm in expr.arms:
                    self._check_escapes_in_body(func_name, arm.body, local_vars, param_names)

    def _is_pure_function(self, func_name: str) -> bool:
        return func_name in self.PURE_FUNCTIONS
