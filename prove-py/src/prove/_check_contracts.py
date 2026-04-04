"""Contract and verb checking mixin for Checker."""

from __future__ import annotations

import re

from prove.ast_nodes import (
    Assignment,
    AsyncCallExpr,
    BinaryExpr,
    BindingPattern,
    CallExpr,
    Expr,
    ExprStmt,
    FailPropExpr,
    FieldAssignment,
    FieldExpr,
    FunctionDef,
    IdentifierExpr,
    LambdaExpr,
    ListLiteral,
    MatchExpr,
    ModuleDecl,
    Param,
    PipeExpr,
    Stmt,
    TypeIdentifierExpr,
    UnaryExpr,
    ValidExpr,
    VarDecl,
    VariantPattern,
)
from prove.errors import DiagnosticLabel, Severity, make_diagnostic
from prove.source import Span
from prove.symbols import Symbol, SymbolKind
from prove.types import (
    BOOLEAN,
    AlgebraicType,
    BorrowType,
    ErrorType,
    GenericInstance,
    PrimitiveType,
    StructType,
    Type,
    has_mutable_modifier,
    type_name,
    types_compatible,
)
from prove.verb_defs import PURE_VERBS

_PURE_VERBS = PURE_VERBS
_IO_FUNCTIONS = frozenset({"sleep"})


def _match_arms_have_fail_prop(match_expr: MatchExpr) -> bool:
    """Return True if any arm body contains a FailPropExpr (failable call).

    A match with failable calls cannot be extracted to a 'matches' verb
    (which must be pure), so I367 must not be suggested.
    """

    def _expr_has_fail(expr: Expr) -> bool:
        if isinstance(expr, FailPropExpr):
            return True
        if isinstance(expr, CallExpr):
            return any(_expr_has_fail(a) for a in expr.args)
        if isinstance(expr, BinaryExpr):
            return _expr_has_fail(expr.left) or _expr_has_fail(expr.right)
        if isinstance(expr, UnaryExpr):
            return _expr_has_fail(expr.operand)
        if isinstance(expr, PipeExpr):
            return _expr_has_fail(expr.left) or _expr_has_fail(expr.right)
        if isinstance(expr, LambdaExpr):
            return _expr_has_fail(expr.body)
        if isinstance(expr, AsyncCallExpr):
            return _expr_has_fail(expr.expr)
        return False

    def _stmt_has_fail(stmt: Stmt | MatchExpr) -> bool:
        if isinstance(stmt, ExprStmt):
            return _expr_has_fail(stmt.expr)
        if isinstance(stmt, VarDecl) and stmt.value is not None:
            return _expr_has_fail(stmt.value)
        if isinstance(stmt, Assignment):
            return _expr_has_fail(stmt.value)
        return False

    return any(_stmt_has_fail(stmt) for arm in match_expr.arms for stmt in arm.body)


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


def _substitute_result_in_expr(expr: Expr, new_name: str) -> Expr:
    """Replace all ``IdentifierExpr(name='result')`` with ``IdentifierExpr(name=new_name)``.

    Used for Phase 4 callee-ensures propagation: when ``y = f(x)`` and
    ``f`` has ``ensures: result > 0``, substitute ``result`` → ``y`` to
    produce the fact ``y > 0`` for the caller's proof context.
    """
    if isinstance(expr, IdentifierExpr):
        if expr.name == "result":
            return IdentifierExpr(name=new_name, span=expr.span)
        return expr  # noqa: E501
    if isinstance(expr, BinaryExpr):
        left = _substitute_result_in_expr(expr.left, new_name)
        right = _substitute_result_in_expr(expr.right, new_name)
        return BinaryExpr(op=expr.op, left=left, right=right, span=expr.span)
    if isinstance(expr, UnaryExpr):
        operand = _substitute_result_in_expr(expr.operand, new_name)
        return UnaryExpr(op=expr.op, operand=operand, span=expr.span)
    # Literals, field access, and other expressions — return as-is
    return expr


class ContractCheckMixin:
    def _check_contracts(self, fd: FunctionDef, return_type: Type, param_types: list[Type]) -> None:
        """Type-check ensures/requires/know/assume/believe/with contracts."""
        # Validate `with` constraints for row polymorphism
        param_names = {p.name for p in fd.params}
        param_type_map = {p.name: pt for p, pt in zip(fd.params, param_types)}
        seen_with: set[tuple[str, str]] = set()
        for wc in fd.with_constraints:
            if wc.param_name not in param_names:
                self._error(
                    "E430",
                    f"`with` references unknown parameter '{wc.param_name}'",
                    wc.span,
                )
                continue
            raw_pt = param_type_map[wc.param_name]
            # Check the raw type before narrowing — StructType params
            # are already narrowed, so also accept narrowed StructType
            if not isinstance(raw_pt, StructType):
                self._error(
                    "E431",
                    f"`with` on parameter '{wc.param_name}' which is not typed Struct",
                    wc.span,
                )
                continue
            key = (wc.param_name, wc.field_name)
            if key in seen_with:
                self._error(
                    "E432",
                    f"duplicate `with` for {wc.param_name}.{wc.field_name}",
                    wc.span,
                )
            seen_with.add(key)

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
                # Infer each arg before _infer_expr(req_expr) so E310 diagnostics
                # for undefined names land before ValidExpr's per-arg rollback
                # snapshot, making them immune to suppression.  All params must be
                # in scope for `requires` (unlike `ensures` where body vars may not).
                for arg in req_expr.args:
                    self._infer_expr(arg)
            req_type = self._infer_expr(req_expr)
            if not isinstance(req_type, ErrorType) and not types_compatible(BOOLEAN, req_type):
                self._error(
                    "E381",
                    f"requires expression must be Boolean, got '{type_name(req_type)}'",
                    req_expr.span if hasattr(req_expr, "span") else fd.span,
                )

        # Build proof context from requires, assume, believe
        from prove.prover import ClaimProver, ProofContext

        proof_context = ProofContext()
        proof_context.add_all(fd.requires)
        proof_context.add_all(fd.assume)
        proof_context.add_all(fd.believe)

        # Phase 4: add callee ensures as facts (y = f(x) + f ensures result > 0
        # → y > 0 added to context)
        callee_facts = self._collect_callee_ensures_facts(fd.body)
        proof_context.add_all(callee_facts)

        # Phase 5: record match arm structural bindings
        self._collect_match_arm_facts(fd.body, proof_context)

        # Phase 6: infer types for arm-bound variables so function-level
        # `know` claims can reference them (e.g. `know: len(inner) > 0`
        # when `inner` is bound in `Some(inner)`).
        arm_bound_types = self._collect_arm_bound_types(proof_context)

        # Type-check `know` and attempt proof
        for know_expr in fd.know:
            # Temporarily define arm-bound variables in scope so that
            # know claims referencing them can be type-checked and proved.
            uses_arm_var = arm_bound_types and any(
                _expr_references_name(know_expr, bname) for bname in arm_bound_types
            )
            if uses_arm_var:
                self.symbols.push_scope("know_arm")
                for bname, btype in arm_bound_types.items():
                    self.symbols.define(
                        Symbol(
                            name=bname,
                            kind=SymbolKind.VARIABLE,
                            resolved_type=btype,
                            span=fd.span,
                        )
                    )
            try:
                know_type = self._infer_expr(know_expr)
                if not isinstance(know_type, ErrorType) and not types_compatible(
                    BOOLEAN, know_type
                ):
                    self._error(
                        "E384",
                        f"know expression must be Boolean, got '{type_name(know_type)}'",
                        know_expr.span if hasattr(know_expr, "span") else fd.span,
                    )
                else:
                    # Attempt to prove the claim using proof context
                    prover = ClaimProver(symbols=self.symbols, context=proof_context)
                    result = prover.prove_claim(know_expr)
                    if result is False:
                        self._error(
                            "E356",
                            "know claim is provably false",
                            know_expr.span if hasattr(know_expr, "span") else fd.span,
                        )
                    elif result is None:
                        span = know_expr.span if hasattr(know_expr, "span") else fd.span
                        code = "W372" if uses_arm_var else "W327"
                        msg = (
                            "cannot prove arm-bound know claim; treating as runtime assertion"
                            if uses_arm_var
                            else "cannot prove know claim; treating as runtime assertion"
                        )
                        self.diagnostics.append(
                            make_diagnostic(
                                Severity.WARNING,
                                code,
                                msg,
                                labels=[DiagnosticLabel(span=span, message="")],
                            )
                        )
                    else:
                        # Proven true — add to context for subsequent claims
                        proof_context.add(know_expr)
            finally:
                if uses_arm_var:
                    self.symbols.pop_scope()

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
                    f"satisfies references undefined type or invariant network '{sat_name}'",
                    fd.span,
                )

        # Check invariant network constraints for functions with `satisfies`
        self._check_invariant_constraints(fd, return_type)

        # Check temporal ordering of operations in function body
        self._check_temporal_ordering(fd)

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

    def _check_intent_prose(self, fd: FunctionDef) -> None:
        """W313: intent: prose has no vocabulary overlap with the function body."""
        if not fd.intent:
            return
        from prove._nl_intent import body_tokens, prose_overlaps

        tokens = body_tokens(fd)
        if tokens and not prose_overlaps(fd.intent, tokens):
            self.diagnostics.append(
                make_diagnostic(
                    Severity.WARNING,
                    "W313",
                    "intent prose doesn't reference any function concepts",
                    labels=[DiagnosticLabel(span=fd.span, message="")],
                    notes=[
                        f"intent: '{fd.intent}'",
                        f"mention at least one of: {', '.join(sorted(tokens)[:5])}",
                    ],
                )
            )

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
        # Flatten &&-conjunctions so each ValidExpr/CallExpr is processed individually
        exprs_to_check: list[Expr] = []
        for req_expr in fd.requires:
            stack = [req_expr]
            while stack:
                e = stack.pop()
                if isinstance(e, BinaryExpr) and e.op == "&&":
                    stack.append(e.left)
                    stack.append(e.right)
                else:
                    exprs_to_check.append(e)
        for req_expr in exprs_to_check:
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
        if verb in ("matches", "dispatches"):
            if fd.params:
                first_type = self._resolve_type_expr(fd.params[0].type_expr)
                is_matchable = (
                    isinstance(first_type, (AlgebraicType, ErrorType))
                    or (
                        isinstance(first_type, PrimitiveType)
                        and first_type.name in ("String", "Integer", "Boolean")
                    )
                    or (
                        isinstance(first_type, GenericInstance)
                        and first_type.base_name in ("Result", "Option")
                    )
                )
                if not is_matchable:
                    self._error(
                        "E365",
                        f"{verb} verb requires first parameter to be "
                        f"a matchable type (algebraic, String, Integer, "
                        f"or Boolean), got '{type_name(first_type)}'",
                        fd.params[0].span,
                    )
            else:
                self._error(
                    "E365",
                    f"{verb} verb requires at least one parameter",
                    fd.span,
                )

        # I367: suggest extracting match to a matches/dispatches verb function
        if verb not in ("matches", "dispatches"):
            self._check_match_restriction(fd.body, fd.span, verb)

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
        verb: str,
    ) -> None:
        """I367: suggest extracting match to a 'matches'/'dispatches' verb function."""
        target = "matches" if verb in _PURE_VERBS else "dispatches"
        for stmt in body:
            if isinstance(stmt, MatchExpr):
                if len(stmt.arms) >= 3 and not _match_arms_have_fail_prop(stmt):
                    self._info(
                        "I367",
                        f"consider extracting match to a '{target}' verb function for better code flow",  # noqa: E501
                        stmt.span,
                    )
            elif isinstance(stmt, VarDecl):
                self._check_match_in_expr(stmt.value, target)
            elif isinstance(stmt, Assignment):
                self._check_match_in_expr(stmt.value, target)
            elif isinstance(stmt, FieldAssignment):
                self._check_match_in_expr(stmt.value, target)
            elif isinstance(stmt, ExprStmt):
                self._check_match_in_expr(stmt.expr, target)

    def _check_match_in_expr(self, expr: Expr, target: str) -> None:
        """Walk an expression looking for MatchExpr nodes."""
        if isinstance(expr, MatchExpr):
            if len(expr.arms) >= 3 and not _match_arms_have_fail_prop(expr):
                self._info(
                    "I367",
                    f"consider extracting match to a '{target}' verb function for better code flow",
                    expr.span,
                )
        elif isinstance(expr, CallExpr):
            for arg in expr.args:
                self._check_match_in_expr(arg, target)
        elif isinstance(expr, BinaryExpr):
            self._check_match_in_expr(expr.left, target)
            self._check_match_in_expr(expr.right, target)
        elif isinstance(expr, UnaryExpr):
            self._check_match_in_expr(expr.operand, target)
        elif isinstance(expr, PipeExpr):
            self._check_match_in_expr(expr.left, target)
            self._check_match_in_expr(expr.right, target)
        elif isinstance(expr, LambdaExpr):
            self._check_match_in_expr(expr.body, target)
        elif isinstance(expr, FailPropExpr):
            self._check_match_in_expr(expr.expr, target)

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

    # ── Invariant network enforcement ───────────────────────────

    def _check_invariant_constraints(self, fd: FunctionDef, return_type: Type) -> None:
        """Type-check invariant network constraints for functions with `satisfies`.

        For each invariant network referenced by `satisfies`, the constraint
        expressions are type-checked in a scope where `result` is bound to the
        function's return type and all parameters are in scope. This validates
        that constraint expressions are well-typed.
        """
        for sat_name in fd.satisfies:
            inv = self._invariant_network_defs.get(sat_name)
            if inv is None or not inv.constraints:
                continue

            # Type-check each constraint expression in a scope with `result`
            self.symbols.push_scope(f"invariant_{sat_name}")
            self.symbols.define(
                Symbol(
                    name="result",
                    kind=SymbolKind.VARIABLE,
                    resolved_type=return_type,
                    span=fd.span,
                )
            )
            for constraint in inv.constraints:
                # Bare function names in constraints are references to validates
                # functions that should be applied to the result — accept them
                # as valid Boolean constraints without full type-inference.
                if isinstance(constraint, IdentifierExpr):
                    sig = self.symbols.resolve_function_any(constraint.name)
                    if sig is not None:
                        continue  # Known function reference — accepted
                constraint_type = self._infer_expr(constraint)
                if not isinstance(constraint_type, ErrorType) and not types_compatible(
                    BOOLEAN, constraint_type
                ):
                    self._error(
                        "E396",
                        f"invariant constraint in '{sat_name}' must be Boolean, "
                        f"got '{type_name(constraint_type)}'",
                        constraint.span if hasattr(constraint, "span") else fd.span,
                    )
            self.symbols.pop_scope()

            # Warn if there are no `ensures` clauses to support verification
            if not fd.ensures:
                diag = make_diagnostic(
                    Severity.WARNING,
                    "W391",
                    f"function satisfies invariant '{sat_name}' but has no "
                    f"'ensures' clause; add ensures clauses to document "
                    f"invariant satisfaction",
                    labels=[DiagnosticLabel(span=fd.span, message="")],
                    notes=[
                        f"The '{sat_name}' invariant has constraints that cannot "
                        f"be automatically verified without postconditions."
                    ],
                )
                self.diagnostics.append(diag)

    # ── Temporal ordering enforcement ────────────────────────────

    def _collect_call_names_from_body(self, body: list) -> list[str]:
        """Collect all top-level function call names from a body in order."""
        names: list[str] = []
        for stmt in body:
            self._collect_call_names_stmt(stmt, names)
        return names

    def _collect_call_names_stmt(self, stmt: Stmt | MatchExpr, names: list[str]) -> None:
        """Recursively collect function call names from a statement."""
        if isinstance(stmt, VarDecl):
            self._collect_call_names_expr(stmt.value, names)
        elif isinstance(stmt, Assignment):
            self._collect_call_names_expr(stmt.value, names)
        elif isinstance(stmt, FieldAssignment):
            self._collect_call_names_expr(stmt.value, names)
        elif isinstance(stmt, ExprStmt):
            self._collect_call_names_expr(stmt.expr, names)
        elif isinstance(stmt, MatchExpr):
            if stmt.subject is not None:
                self._collect_call_names_expr(stmt.subject, names)
            for arm in stmt.arms:
                for s in arm.body:
                    self._collect_call_names_stmt(s, names)

    def _collect_call_names_expr(self, expr: Expr, names: list[str]) -> None:
        """Recursively collect function call names from an expression."""
        if isinstance(expr, CallExpr):
            if isinstance(expr.func, IdentifierExpr):
                names.append(expr.func.name)
            elif isinstance(expr.func, FieldExpr) and isinstance(expr.func.obj, IdentifierExpr):
                names.append(expr.func.field)
            for arg in expr.args:
                self._collect_call_names_expr(arg, names)
        elif isinstance(expr, BinaryExpr):
            self._collect_call_names_expr(expr.left, names)
            self._collect_call_names_expr(expr.right, names)
        elif isinstance(expr, UnaryExpr):
            self._collect_call_names_expr(expr.operand, names)
        elif isinstance(expr, PipeExpr):
            self._collect_call_names_expr(expr.left, names)
            self._collect_call_names_expr(expr.right, names)
        elif isinstance(expr, FailPropExpr):
            self._collect_call_names_expr(expr.expr, names)
        elif isinstance(expr, MatchExpr):
            if expr.subject is not None:
                self._collect_call_names_expr(expr.subject, names)
            for arm in expr.arms:
                for s in arm.body:
                    self._collect_call_names_stmt(s, names)
        elif isinstance(expr, LambdaExpr):
            self._collect_call_names_expr(expr.body, names)

    def _check_temporal_ordering(self, fd: FunctionDef) -> None:
        """Warn when temporal operations appear out of declared order (W390).

        If the module declares `temporal: a -> b -> c`, any function that calls
        temporal operations must call them in that order. Calling `b` before `a`
        in the same function body is flagged.
        """
        if not self._temporal_order:
            return

        temporal_set = set(self._temporal_order)
        call_names = self._collect_call_names_from_body(fd.body)

        # Extract temporal steps in the order they appear in the body
        ordered_steps = [(name, i) for i, name in enumerate(call_names) if name in temporal_set]

        if len(ordered_steps) < 2:
            return

        declared_order = {step: pos for pos, step in enumerate(self._temporal_order)}

        prev_pos = -1
        prev_name: str | None = None
        for name, _call_idx in ordered_steps:
            step_pos = declared_order.get(name, -1)
            if step_pos < prev_pos:
                diag = make_diagnostic(
                    Severity.WARNING,
                    "W390",
                    f"temporal operation '{name}' appears before '{prev_name}'; "
                    f"declared order: {' -> '.join(self._temporal_order)}",
                    labels=[DiagnosticLabel(span=fd.span, message="")],
                    notes=["Reorder the calls to match the declared temporal sequence."],
                )
                self.diagnostics.append(diag)
                return  # Report first violation only
            prev_pos = step_pos
            prev_name = name

    # ── Prose coherence checks (W501-W506) ─────────────────────────────────

    def _check_narrative_verb_coherence(self, mod_decl: ModuleDecl, fns: list[FunctionDef]) -> None:
        """W501: function verb not described in module narrative."""
        if mod_decl.narrative is None:
            return
        from prove._nl_intent import implied_verbs

        verbs = implied_verbs(mod_decl.narrative)
        for fd in fns:
            if fd.verb not in verbs:
                if verbs:
                    note = f"narrative implies: {', '.join(sorted(verbs))}"
                else:
                    note = "narrative does not describe any verb intent"
                self.diagnostics.append(
                    make_diagnostic(
                        Severity.WARNING,
                        "W501",
                        f"verb '{fd.verb}' not described in module narrative",
                        labels=[DiagnosticLabel(span=fd.span, message="")],
                        notes=[note],
                    )
                )

    def _check_narrative_flow_steps(self, mod_decl: ModuleDecl, fns: list[FunctionDef]) -> None:
        """W343: narrative flow: step name is not a defined function."""
        if mod_decl.narrative is None:
            return
        defined = {fd.name for fd in fns}
        # Find all `flow: X -> Y -> Z` lines in the narrative text
        for match in re.finditer(r"(?m)^[ \t]*flow:\s*(.+)$", mod_decl.narrative):
            step_text = match.group(1)
            for raw in re.split(r"\s*->\s*", step_text):
                step = raw.strip()
                # Strip trailing punctuation (commas, periods) that may appear inline
                step = step.rstrip(".,;")
                if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", step):
                    continue  # skip non-identifier tokens (e.g. numbers, ellipsis)
                if step not in defined:
                    self.diagnostics.append(
                        make_diagnostic(
                            Severity.WARNING,
                            "W343",
                            f"narrative flow step '{step}' is not a defined function",
                            labels=[DiagnosticLabel(span=mod_decl.span, message="")],
                            notes=[
                                f"defined functions: {', '.join(sorted(defined)[:5])}",
                            ],
                        )
                    )

    def _check_explain_body_coherence(self, fd: FunctionDef) -> None:
        """W502: explain entry text has no overlap with from-body operations."""
        if fd.explain is None:
            return
        from prove._nl_intent import body_tokens, prose_overlaps

        tokens = body_tokens(fd)
        if not tokens:
            return
        for entry in fd.explain.entries:
            if entry.condition is not None:
                continue  # `when` entries are structural — skip
            if entry.text.strip() and not prose_overlaps(entry.text, tokens):
                self.diagnostics.append(
                    make_diagnostic(
                        Severity.WARNING,
                        "W502",
                        "explain entry doesn't correspond to any operation in from-block",
                        labels=[DiagnosticLabel(span=fd.span, message="")],
                        notes=[
                            f"entry: '{entry.text.strip()}'",
                            f"body references: {', '.join(sorted(tokens))}",
                        ],
                    )
                )

    def _check_chosen_has_why_not(self, fd: FunctionDef) -> None:
        """W503: chosen declared without any why_not alternatives."""
        if fd.chosen and not fd.why_not:
            self.diagnostics.append(
                make_diagnostic(
                    Severity.WARNING,
                    "W503",
                    "chosen declared without any why_not alternatives",
                    labels=[DiagnosticLabel(span=fd.span, message="")],
                    notes=["Add at least one `why_not` entry to document rejected approaches."],
                )
            )

    def _check_chosen_body_coherence(self, fd: FunctionDef) -> None:
        """W504: chosen text has no overlap with from-body operations or params."""
        if not fd.chosen:
            return
        from prove._nl_intent import body_tokens, prose_overlaps

        tokens = body_tokens(fd)
        if tokens and not prose_overlaps(fd.chosen, tokens):
            self.diagnostics.append(
                make_diagnostic(
                    Severity.WARNING,
                    "W504",
                    "chosen text doesn't correspond to any operation in from-block",
                    labels=[DiagnosticLabel(span=fd.span, message="")],
                    notes=[
                        f"chosen: '{fd.chosen}'",
                        f"body references: {', '.join(sorted(tokens))}",
                    ],
                )
            )

    def _check_why_not_names(self, fd: FunctionDef, known_names: set[str]) -> None:
        """W505: why_not entry mentions no function/type name from current scope."""
        lower_known = {n.lower() for n in known_names}
        for entry in fd.why_not:
            words = {w.lower() for w in re.findall(r"[a-zA-Z_][a-zA-Z0-9_]*", entry)}
            if not words & lower_known:
                self.diagnostics.append(
                    make_diagnostic(
                        Severity.WARNING,
                        "W505",
                        "why_not entry mentions no known function or type",
                        labels=[DiagnosticLabel(span=fd.span, message="")],
                        notes=[
                            f"entry: '{entry}'",
                            "Reference a function name, type, or algorithm to anchor the rejection.",  # noqa: E501
                        ],
                    )
                )

    def _check_why_not_contradiction(self, fd: FunctionDef) -> None:
        """W506: why_not entry rejects an approach that appears to be used in the body.

        If a why_not entry mentions words that match function names actually called
        in the from-block, the rejection is contradicted by the implementation.
        Only compares against call names (not parameter names) to avoid false positives
        when programmers mention parameters in their rationale prose.
        """
        if not fd.why_not:
            return

        # Collect only actual function call names (not param names) to avoid
        # false positives when params are mentioned in why_not prose.
        _collected: list[str] = []
        for stmt in fd.body:
            self._collect_call_names_stmt(stmt, _collected)
        call_names = set(_collected)

        if not call_names:
            return
        lower_calls = {t.lower() for t in call_names}
        for entry in fd.why_not:
            words = {w.lower() for w in re.findall(r"[a-zA-Z_][a-zA-Z0-9_]*", entry)}
            overlap = words & lower_calls
            if overlap:
                self.diagnostics.append(
                    make_diagnostic(
                        Severity.WARNING,
                        "W506",
                        "why_not entry rejects an approach that the from-block appears to use",
                        labels=[DiagnosticLabel(span=fd.span, message="")],
                        notes=[
                            f"entry: '{entry}'",
                            f"body uses: {', '.join(sorted(overlap))}",
                            "Either update the why_not to reflect the actual rejected approach, "
                            "or revise the implementation.",
                        ],
                    )
                )

    # ── Phase 4: callee-ensures propagation ──────────────────────────

    def _collect_callee_ensures_facts(self, body: list[Stmt | MatchExpr]) -> list[Expr]:
        """Scan function body for call-result bindings and collect callee ensures.

        Phase 4: callee-ensures propagation.

        For each ``y = f(x)`` where ``f`` has ``ensures: result > 0``,
        substitutes ``result`` → ``y`` to produce ``y > 0`` and adds it to
        the list of proof context facts.  This lets subsequent ``know``
        claims reference the callee's postcondition by the local name.
        """
        facts: list[Expr] = []
        for stmt in body:
            if not isinstance(stmt, VarDecl):
                continue
            call: Expr = stmt.value
            # Unwrap fail-propagation: y = f()! → strip the !
            if isinstance(call, FailPropExpr):
                call = call.expr
            if not isinstance(call, CallExpr):
                continue
            # Resolve callee name
            func = call.func
            if isinstance(func, IdentifierExpr):
                callee_name = func.name
            elif isinstance(func, FieldExpr):
                callee_name = func.field
            else:
                continue
            sig = self.symbols.resolve_function_any(callee_name, arity=len(call.args))
            if sig is None or not sig.ensures:
                continue
            for ens_expr in sig.ensures:
                facts.append(_substitute_result_in_expr(ens_expr, stmt.name))
        return facts

    # ── Phase 5: match-arm structural narrowing ───────────────────────

    def _collect_match_arm_facts(
        self,
        body: list[Stmt | MatchExpr],
        proof_context: object,
    ) -> None:
        """Scan body match arms and record structural binding facts.

        Phase 5: match-arm path narrowing.

        For each ``match subj { Some(x) -> ..., None -> ... }`` found in
        the body, records ``(subj, "Some", ["x"])`` in the proof context
        via ``ProofContext.add_match_arm_binding``.  The proof engine can
        then confirm structural facts (e.g. ``subj != None``) when they
        are independently established by ``requires`` or ``assume``.

        This is primarily infrastructure for future arm-level proof
        checking; with function-level ``know`` claims the gain is the
        structural confirmation described in ``ClaimProver._prove_from_match_bindings``.
        """
        for stmt in body:
            match_expr: MatchExpr | None = None
            if isinstance(stmt, MatchExpr):
                match_expr = stmt
            elif isinstance(stmt, ExprStmt) and isinstance(stmt.expr, MatchExpr):
                match_expr = stmt.expr
            elif isinstance(stmt, VarDecl) and isinstance(stmt.value, MatchExpr):
                match_expr = stmt.value
            if match_expr is None:
                continue
            if not isinstance(match_expr.subject, IdentifierExpr):
                continue
            subj_name = match_expr.subject.name
            for arm in match_expr.arms:
                if not isinstance(arm.pattern, VariantPattern):
                    continue
                if arm.pattern.name not in ("Some", "Ok", "Error", "None"):
                    continue
                bindings = [f.name for f in arm.pattern.fields if isinstance(f, BindingPattern)]
                proof_context.add_match_arm_binding(subj_name, arm.pattern.name, bindings)

    def _collect_arm_bound_types(self, proof_context: object) -> dict[str, Type]:
        """Phase 6: infer types for arm-bound variables.

        For each match arm binding recorded in proof_context, look up the
        subject's type and derive the bound variable type from the variant:
        - ``Option<T>`` / ``Some(x)``  → ``x: T``
        - ``Result<T,E>`` / ``Ok(v)``   → ``v: T``
        - ``Result<T,E>`` / ``Err(e)``  → ``e: E``

        Returns a mapping from bound variable name → inferred type, so
        function-level ``know`` claims that reference arm-bound variables
        can be type-checked and proved.
        """
        bound: dict[str, Type] = {}
        for subj_name, variant, bindings in proof_context.match_bindings:
            if not bindings:
                continue
            subj_sym = self.symbols.lookup(subj_name)
            if subj_sym is None:
                continue
            subj_type = subj_sym.resolved_type
            if not isinstance(subj_type, GenericInstance):
                continue
            inner: Type | None = None
            if subj_type.base_name == "Option" and len(subj_type.args) >= 1:
                if variant == "Some":
                    inner = subj_type.args[0]
            elif subj_type.base_name == "Result" and len(subj_type.args) >= 2:
                if variant == "Ok":
                    inner = subj_type.args[0]
                elif variant in ("Err", "Error"):
                    inner = subj_type.args[1]
            if inner is not None:
                for bname in bindings:
                    bound[bname] = inner
        return bound
