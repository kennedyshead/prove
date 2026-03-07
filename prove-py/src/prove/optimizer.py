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
    FloatLit,
    FunctionDef,
    IdentifierExpr,
    IntegerLit,
    LiteralPattern,
    MainDef,
    MatchArm,
    MatchExpr,
    Module,
    ModuleDecl,
    StringLit,
    TailContinue,
    TailLoop,
    UnaryExpr,
    VarDecl,
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


class Optimizer:
    """Multi-pass AST optimizer."""

    def __init__(self, module: Module, symbols: SymbolTable) -> None:
        self._module = module
        self._symbols = symbols
        self._memo_info = MemoizationInfo()
        self._runtime_deps = RuntimeDeps()

    def optimize(self) -> Module:
        module = self._collect_runtime_deps(self._module)
        module = self._tail_call_optimization(module)
        module = self._dead_branch_elimination(module)
        module = self._ct_eval_pure_calls(module)
        module = self._inline_small_functions(module)
        module = self._dead_code_elimination(module)
        module = self._identify_memoization_candidates(module)
        module = self._match_compilation(module)
        return module

    def get_memo_info(self) -> MemoizationInfo:
        """Return memoization candidates discovered during optimization."""
        return self._memo_info

    def get_runtime_deps(self) -> RuntimeDeps:
        """Return runtime dependencies discovered during optimization."""
        return self._runtime_deps

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

    # ── Pass 2b: Dead Code Elimination ─────────────────────────────

    def _dead_code_elimination(self, module: Module) -> Module:
        """Remove unused functions - those never called from reachable code."""
        reachable = self._find_reachable_functions(module)
        if not reachable:
            return module
        new_decls: list[Declaration] = []
        for decl in module.declarations:
            if isinstance(decl, FunctionDef):
                if decl.name in reachable:
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
        elif isinstance(stmt, VarDecl):
            self._find_called_in_expr(stmt.value, called)
        elif isinstance(stmt, Assignment):
            self._find_called_in_expr(stmt.value, called)

    def _find_called_in_stmts(self, stmts: list[Any], called: set[str]) -> None:
        for stmt in stmts:
            self._find_called_in_stmt(stmt, called)

    def _find_called_in_expr(self, expr: Expr, called: set[str]) -> None:
        """Recursively find function calls in an expression."""
        if isinstance(expr, CallExpr) and isinstance(expr.func, IdentifierExpr):
            called.add(expr.func.name)
            for arg in expr.args:
                self._find_called_in_expr(arg, called)
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
                # Their return type already encodes the contract (Option<T>!, Result<T, E>!)
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

    # ── Pass 3b: Memoization Candidate Identification ─────────────

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
