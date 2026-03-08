"""Contract and verb checking mixin for Checker."""

from __future__ import annotations

from prove.ast_nodes import (
    Assignment,
    BinaryExpr,
    CallExpr,
    Expr,
    ExprStmt,
    FailPropExpr,
    FieldAssignment,
    FieldExpr,
    FunctionDef,
    IdentifierExpr,
    IndexExpr,
    LambdaExpr,
    ListLiteral,
    MatchExpr,
    NearMiss,
    Param,
    PipeExpr,
    Stmt,
    TypeIdentifierExpr,
    UnaryExpr,
    ValidExpr,
    VarDecl,
)
from prove.errors import DiagnosticLabel, Severity, make_diagnostic
from prove.source import Span
from prove.symbols import Symbol, SymbolKind
from prove.types import (
    BOOLEAN,
    UNIT,
    AlgebraicType,
    BorrowType,
    ErrorType,
    PrimitiveType,
    Type,
    has_mutable_modifier,
    type_name,
    types_compatible,
)

_PURE_VERBS = frozenset({"transforms", "validates", "reads", "creates", "matches"})
_IO_FUNCTIONS = frozenset({"sleep"})


def _expr_references_name(expr: Expr, name: str) -> bool:
    """Walk an expression tree and return True if it references the given name."""
    if isinstance(expr, IdentifierExpr):
        return expr.name == name
    if isinstance(expr, BinaryExpr):
        return _expr_references_name(expr.left, name) or _expr_references_name(expr.right, name)
    if isinstance(expr, UnaryExpr):
        return _expr_references_name(expr.operand, name)
    if isinstance(expr, CallExpr):
        if _expr_references_name(expr.func, name):
            return True
        return any(_expr_references_name(a, name) for a in expr.args)
    if isinstance(expr, FieldExpr):
        return _expr_references_name(expr.obj, name)
    if isinstance(expr, PipeExpr):
        return _expr_references_name(expr.left, name) or _expr_references_name(expr.right, name)
    if isinstance(expr, ValidExpr):
        if expr.args:
            return any(_expr_references_name(a, name) for a in expr.args)
        return False
    if isinstance(expr, MatchExpr):
        if expr.subject and _expr_references_name(expr.subject, name):
            return True
        for arm in expr.arms:
            for stmt in arm.body:
                if isinstance(stmt, ExprStmt) and _expr_references_name(stmt.expr, name):
                    return True
        return False
    if isinstance(expr, LambdaExpr):
        return _expr_references_name(expr.body, name)
    if isinstance(expr, FailPropExpr):
        return _expr_references_name(expr.expr, name)
    if isinstance(expr, ListLiteral):
        return any(_expr_references_name(e, name) for e in expr.elements)
    # TypeIdentifierExpr, IndexExpr, literals — no name references
    return False


class ContractCheckMixin:
    def _check_contracts(self, fd: FunctionDef, return_type: Type, param_types: list[Type]) -> None:
        """Type-check ensures/requires/know/assume/believe contracts."""
        # Type-check `ensures` — push sub-scope with `result` bound to return type
        for ens_expr in fd.ensures:
            # Check for undefined validator in ensures
            if isinstance(ens_expr, ValidExpr) and ens_expr.args is not None:
                func_name = ens_expr.name
                n_args = len(ens_expr.args)
                sig = self.symbols.resolve_function("validates", func_name, n_args)
                if sig is None:
                    sig = self.symbols.resolve_function_any(func_name, arity=n_args)
                if sig is None or sig.verb != "validates":
                    self._error(
                        "E311",
                        f"undefined function '{func_name}'",
                        ens_expr.span,
                    )
                else:
                    # Mark import as used
                    if sig.module:
                        self._used_imports.add((sig.module, func_name))

            self.symbols.push_scope("ensures")
            self.symbols.define(
                Symbol(
                    name="result",
                    kind=SymbolKind.VARIABLE,
                    resolved_type=return_type,
                    span=fd.span,
                )
            )
            ens_type = self._infer_expr(ens_expr)
            if not isinstance(ens_type, ErrorType) and not types_compatible(BOOLEAN, ens_type):
                self._error(
                    "E380",
                    f"ensures expression must be Boolean, got '{type_name(ens_type)}'",
                    ens_expr.span if hasattr(ens_expr, "span") else fd.span,
                )
            # Skip W328 for validates (implicit Boolean return, ensures
            # naturally checks input conditions) and for ValidExpr
            # (validation postconditions don't reference result).
            if (
                fd.verb != "validates"
                and not isinstance(ens_expr, ValidExpr)
                and not _expr_references_name(ens_expr, "result")
            ):
                self._warning(
                    "W328",
                    "ensures clause doesn't reference 'result'; "
                    "postcondition should constrain the return value",
                    ens_expr.span if hasattr(ens_expr, "span") else fd.span,
                )
            self.symbols.pop_scope()

        # Type-check `requires` — params are already in scope
        for req_expr in fd.requires:
            # Check for undefined validator in requires
            if isinstance(req_expr, ValidExpr) and req_expr.args is not None:
                func_name = req_expr.name
                n_args = len(req_expr.args)
                sig = self.symbols.resolve_function("validates", func_name, n_args)
                if sig is None:
                    sig = self.symbols.resolve_function_any(func_name, arity=n_args)
                if sig is None or sig.verb != "validates":
                    self._error(
                        "E311",
                        f"undefined function '{func_name}'",
                        req_expr.span,
                    )
                else:
                    # Mark import as used
                    if sig.module:
                        self._used_imports.add((sig.module, func_name))
            req_type = self._infer_expr(req_expr)
            if not isinstance(req_type, ErrorType) and not types_compatible(BOOLEAN, req_type):
                self._error(
                    "E381",
                    f"requires expression must be Boolean, got '{type_name(req_type)}'",
                    req_expr.span if hasattr(req_expr, "span") else fd.span,
                )

        # Type-check `know` and attempt proof
        for know_expr in fd.know:
            know_type = self._infer_expr(know_expr)
            if not isinstance(know_type, ErrorType) and not types_compatible(BOOLEAN, know_type):
                self._error(
                    "E384",
                    f"know expression must be Boolean, got '{type_name(know_type)}'",
                    know_expr.span if hasattr(know_expr, "span") else fd.span,
                )
            else:
                # Attempt to prove the claim
                from prove.prover import ClaimProver

                prover = ClaimProver(symbols=self.symbols)
                result = prover.prove_claim(know_expr)
                if result is False:
                    self._error(
                        "E356",
                        "know claim is provably false",
                        know_expr.span if hasattr(know_expr, "span") else fd.span,
                    )
                elif result is None:
                    span = know_expr.span if hasattr(know_expr, "span") else fd.span
                    self.diagnostics.append(
                        make_diagnostic(
                            Severity.WARNING,
                            "W327",
                            "cannot prove know claim; treating as runtime assertion",
                            labels=[DiagnosticLabel(span=span, message="")],
                        )
                    )

        # Type-check `assume`
        for assume_expr in fd.assume:
            assume_type = self._infer_expr(assume_expr)
            if not isinstance(assume_type, ErrorType) and not types_compatible(
                BOOLEAN, assume_type
            ):
                self._error(
                    "E385",
                    f"assume expression must be Boolean, got '{type_name(assume_type)}'",
                    assume_expr.span if hasattr(assume_expr, "span") else fd.span,
                )

        # Type-check `believe`
        for believe_expr in fd.believe:
            self.symbols.push_scope("believe")
            self.symbols.define(
                Symbol(
                    name="result",
                    kind=SymbolKind.VARIABLE,
                    resolved_type=return_type,
                    span=fd.span,
                )
            )
            believe_type = self._infer_expr(believe_expr)
            if not isinstance(believe_type, ErrorType) and not types_compatible(
                BOOLEAN, believe_type
            ):
                self._error(
                    "E386",
                    f"believe expression must be Boolean, got '{type_name(believe_type)}'",
                    believe_expr.span if hasattr(believe_expr, "span") else fd.span,
                )
            self.symbols.pop_scope()

        # Validate `satisfies` — each name must be a type or invariant network
        for sat_name in fd.satisfies:
            resolved = self.symbols.resolve_type(sat_name)
            if resolved is None and sat_name not in self._invariant_networks:
                self._error(
                    "E382",
                    f"satisfies references undefined type or "
                    f"invariant network '{sat_name}'",
                    fd.span,
                )

        # Type-check `near_miss` expressions
        # validates has implicit Boolean return (checker stores Unit)
        nm_return_type = BOOLEAN if fd.verb == "validates" else return_type
        for nm in fd.near_misses:
            # Type-check input expression (params are already in scope)
            self._infer_expr(nm.input)

            # Type-check expected expression — push scope with result available
            self.symbols.push_scope("near_miss")
            self.symbols.define(
                Symbol(
                    name="result",
                    kind=SymbolKind.VARIABLE,
                    resolved_type=nm_return_type,
                    span=fd.span,
                )
            )
            expected_type = self._infer_expr(nm.expected)
            if not isinstance(expected_type, ErrorType) and not types_compatible(
                nm_return_type, expected_type
            ):
                self._error(
                    "E383",
                    f"near_miss expected type '{type_name(expected_type)}' "
                    f"doesn't match return type '{type_name(nm_return_type)}'",
                    nm.expected.span,
                )
            self.symbols.pop_scope()

        # Warning: intent set but no ensures/requires
        if fd.intent and not fd.ensures and not fd.requires:
            diag = make_diagnostic(
                Severity.WARNING,
                "W311",
                "intent declared but no ensures or requires to validate it",
                labels=[DiagnosticLabel(span=fd.span, message="")],
                notes=[
                    "Add `ensures` or `requires` clauses so the compiler can verify the intent.",
                ],
            )
            self.diagnostics.append(diag)

    # ── Requires-based option narrowing ─────────────────────────

    def _collect_requires_narrowings(
        self,
        fd: FunctionDef,
    ) -> list[tuple[str, list[Expr]]]:
        """Scan fd.requires for validates calls and valid expressions.

        Returns a list of (module_name, args) tuples that can be used to
        narrow Option<Value> → Value and Result<Value, Error> → Value in the function body.
        """
        narrowings: list[tuple[str, list[Expr]]] = []
        for req_expr in fd.requires:
            # valid file(path) → ValidExpr
            if isinstance(req_expr, ValidExpr) and req_expr.args is not None:
                func_name = req_expr.name
                args = req_expr.args
                n_args = len(args)
                sig = self.symbols.resolve_function(
                    "validates",
                    func_name,
                    n_args,
                )
                if sig is None:
                    sig = self.symbols.resolve_function_any(
                        func_name,
                        arity=n_args,
                    )
                if sig is not None and sig.verb == "validates":
                    mod = sig.module or "_local"
                    narrowings.append((mod, args))
                continue
            # has(key, table) or Table.has(key, table)
            if not isinstance(req_expr, CallExpr):
                continue
            func = req_expr.func
            module_name: str | None = None
            func_name_: str | None = None
            if isinstance(func, FieldExpr) and isinstance(func.obj, TypeIdentifierExpr):
                module_name = func.obj.name
                func_name_ = func.field
            elif isinstance(func, IdentifierExpr):
                func_name_ = func.name
            else:
                continue
            n_args = len(req_expr.args)
            sig = self.symbols.resolve_function(
                "validates",
                func_name_,
                n_args,
            )
            if sig is None:
                sig = self.symbols.resolve_function_any(
                    func_name_,
                    arity=n_args,
                )
            if sig is not None and sig.verb == "validates":
                mod = module_name or sig.module
                if mod:
                    narrowings.append((mod, req_expr.args))
        return narrowings

    def _has_requires_narrowing(
        self,
        module: str,
        call_args: list[Expr],
    ) -> bool:
        """Check if a matching validates precondition exists."""
        for mod, req_args in self._requires_narrowings:
            if mod != module:
                continue
            if len(req_args) != len(call_args):
                continue
            if all(self._exprs_equal(a, b) for a, b in zip(req_args, call_args)):
                return True
        return False

    # ── Verb enforcement ────────────────────────────────────────

    def _check_verb_rules(self, fd: FunctionDef) -> None:
        """Enforce verb purity constraints."""
        verb = fd.verb
        if verb in _PURE_VERBS:
            # Pure functions cannot be failable
            if fd.can_fail:
                self._error("E361", "pure function cannot be failable", fd.span)
            # Check body for IO calls
            self._check_pure_body(fd.body, fd.span)

        # matches verb: first parameter must be a matchable type
        if verb == "matches":
            if fd.params:
                first_type = self._resolve_type_expr(fd.params[0].type_expr)
                is_matchable = isinstance(first_type, (AlgebraicType, ErrorType)) or (
                    isinstance(first_type, PrimitiveType)
                    and first_type.name in ("String", "Integer")
                )
                if not is_matchable:
                    self._error(
                        "E365",
                        f"matches verb requires first parameter to be "
                        f"a matchable type (algebraic, String, or "
                        f"Integer), got '{type_name(first_type)}'",
                        fd.params[0].span,
                    )
            else:
                self._error(
                    "E365",
                    "matches verb requires at least one parameter",
                    fd.span,
                )

        # I367: suggest extracting match to a matches verb function
        if verb != "matches":
            self._check_match_restriction(fd.body, fd.span)

    def _has_pure_overload(self, name: str) -> bool:
        """Check if a function name has at least one pure verb overload."""
        for verb, fname in self.symbols.all_functions():
            if fname == name and verb in _PURE_VERBS:
                return True
        return False

    def _check_pure_body(self, body: list[Stmt | MatchExpr], span: Span) -> None:
        """Check that a body doesn't contain IO calls."""
        for stmt in body:
            self._check_pure_stmt(stmt)

    def _check_pure_stmt(self, stmt: Stmt | MatchExpr) -> None:
        """Check a single statement for IO calls."""
        if isinstance(stmt, VarDecl):
            self._check_pure_expr(stmt.value)
        elif isinstance(stmt, Assignment):
            self._check_pure_expr(stmt.value)
        elif isinstance(stmt, FieldAssignment):
            self._error(
                "E331",
                "field mutation in pure function; construct a new value instead",
                stmt.span,
            )
            self._check_pure_expr(stmt.value)
        elif isinstance(stmt, ExprStmt):
            self._check_pure_expr(stmt.expr)
        elif isinstance(stmt, MatchExpr):
            if stmt.subject:
                self._check_pure_expr(stmt.subject)
            for arm in stmt.arms:
                for s in arm.body:
                    self._check_pure_stmt(s)

    def _check_pure_expr(self, expr: Expr) -> None:
        """Check an expression for IO calls."""
        if isinstance(expr, CallExpr):
            if isinstance(expr.func, IdentifierExpr):
                fname = expr.func.name
                if fname in _IO_FUNCTIONS:
                    self._error(
                        "E362",
                        f"pure function cannot call IO function '{fname}'",
                        expr.span,
                    )
                elif fname in self._io_function_names:
                    # Skip if the name also has a pure overload (channel
                    # dispatch) — the actual verb check will happen in
                    # _infer_call once the correct overload is resolved.
                    if not self._has_pure_overload(fname):
                        self._error(
                            "E363",
                            f"pure function cannot call IO function '{fname}'",
                            expr.span,
                        )
                else:
                    # Also check if resolved function has an IO verb
                    sig = self.symbols.resolve_function_any(fname)
                    if sig and sig.verb in ("inputs", "outputs"):
                        self._error(
                            "E362",
                            f"pure function cannot call IO function '{fname}'",
                            expr.span,
                        )
            for arg in expr.args:
                self._check_pure_expr(arg)
        elif isinstance(expr, BinaryExpr):
            self._check_pure_expr(expr.left)
            self._check_pure_expr(expr.right)
        elif isinstance(expr, UnaryExpr):
            self._check_pure_expr(expr.operand)
        elif isinstance(expr, PipeExpr):
            self._check_pure_expr(expr.left)
            self._check_pure_expr(expr.right)
        elif isinstance(expr, FailPropExpr):
            self._check_pure_expr(expr.expr)
        elif isinstance(expr, LambdaExpr):
            self._check_pure_expr(expr.body)
        elif isinstance(expr, MatchExpr):
            if expr.subject:
                self._check_pure_expr(expr.subject)
            for arm in expr.arms:
                for s in arm.body:
                    self._check_pure_stmt(s)

    # ── Match restriction (I367) ────────────────────────────────

    def _check_match_restriction(
        self,
        body: list[Stmt | MatchExpr],
        span: Span,
    ) -> None:
        """I367: suggest extracting match to a 'matches' verb function."""
        for stmt in body:
            if isinstance(stmt, MatchExpr):
                self._info(
                    "I367",
                    "consider extracting match to a 'matches' verb function for better code flow",
                    stmt.span,
                )
            elif isinstance(stmt, VarDecl):
                self._check_match_in_expr(stmt.value)
            elif isinstance(stmt, Assignment):
                self._check_match_in_expr(stmt.value)
            elif isinstance(stmt, FieldAssignment):
                self._check_match_in_expr(stmt.value)
            elif isinstance(stmt, ExprStmt):
                self._check_match_in_expr(stmt.expr)

    def _check_match_in_expr(self, expr: Expr) -> None:
        """Walk an expression looking for MatchExpr nodes."""
        if isinstance(expr, MatchExpr):
            self._info(
                "I367",
                "consider extracting match to a 'matches' verb function for better code flow",
                expr.span,
            )
        elif isinstance(expr, CallExpr):
            for arg in expr.args:
                self._check_match_in_expr(arg)
        elif isinstance(expr, BinaryExpr):
            self._check_match_in_expr(expr.left)
            self._check_match_in_expr(expr.right)
        elif isinstance(expr, UnaryExpr):
            self._check_match_in_expr(expr.operand)
        elif isinstance(expr, PipeExpr):
            self._check_match_in_expr(expr.left)
            self._check_match_in_expr(expr.right)
        elif isinstance(expr, LambdaExpr):
            self._check_match_in_expr(expr.body)
        elif isinstance(expr, FailPropExpr):
            self._check_match_in_expr(expr.expr)

    def _infer_param_borrows(
        self, params: list[Param], param_types: list[Type], body: list[Stmt | MatchExpr]
    ) -> dict[str, Type]:
        """Analyze function body to infer which parameters are used in read-only mode.

        Returns a mapping from parameter name to its borrowed type if the parameter
        is only used in read-only contexts (passed to other functions without mutation).
        """
        param_readonly_usage: dict[str, bool] = {}
        for p in params:
            param_readonly_usage[p.name] = True
        param_names = {p.name for p in params}

        def check_expr_readonly(expr: Expr) -> bool:
            """Check if an expression involves mutating any parameter."""
            if isinstance(expr, IdentifierExpr):
                if expr.name in param_names:
                    sym = self.symbols.lookup(expr.name)
                    if sym is not None and has_mutable_modifier(sym.resolved_type):
                        return False
                return True
            if isinstance(expr, CallExpr):
                for arg in expr.args:
                    if not check_expr_readonly(arg):
                        return False
                return True
            if isinstance(expr, BinaryExpr):
                return check_expr_readonly(expr.left) and check_expr_readonly(expr.right)
            if isinstance(expr, UnaryExpr):
                return check_expr_readonly(expr.operand)
            if isinstance(expr, FieldExpr):
                return check_expr_readonly(expr.base)
            if isinstance(expr, ListLiteral):
                return all(check_expr_readonly(e) for e in expr.elements)
            return True

        for stmt in body:
            if not self._check_stmt_readonly(stmt, param_names):
                for p in params:
                    param_readonly_usage[p.name] = False

        result: dict[str, Type] = {}
        for p, pty in zip(params, param_types):
            if param_readonly_usage.get(p.name, False):
                result[p.name] = BorrowType(pty)
        return result

    def _check_stmt_readonly(self, stmt: Stmt, param_names: set[str]) -> bool:
        """Check if a statement only uses parameters in read-only mode."""
        if isinstance(stmt, Assignment):
            if stmt.target in param_names:
                return False
            return True
        if isinstance(stmt, VarDecl):
            return True
        if isinstance(stmt, ExprStmt):
            return True
        if isinstance(stmt, MatchExpr):
            return True
        return True

    def _check_expr_readonly(self, expr: Expr, param_names: set[str]) -> bool:
        """Check if an expression only uses parameters in read-only mode."""
        if isinstance(expr, IdentifierExpr):
            if expr.name in param_names:
                sym = self.symbols.lookup(expr.name)
                if sym is not None and has_mutable_modifier(sym.resolved_type):
                    return False
            return True
        if isinstance(expr, CallExpr):
            return all(self._check_expr_readonly(arg, param_names) for arg in expr.args)
        if isinstance(expr, BinaryExpr):
            return self._check_expr_readonly(expr.left, param_names) and self._check_expr_readonly(
                expr.right, param_names
            )
        if isinstance(expr, FieldExpr):
            return self._check_expr_readonly(expr.base, param_names)
        return True
