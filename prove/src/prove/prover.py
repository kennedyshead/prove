"""Structural proof verification for the Prove language.

Checks proof blocks for completeness and consistency:
- E390: ensures without proof block (error)
- E391: duplicate obligation names (error)
- E392: proof obligations < ensures count (error)
- E393: believe without ensures (error)
- E366: recursive function missing terminates (error)
- W321: proof text doesn't reference function concepts
- W322: duplicate near-miss inputs
- W323: ensures without explain (warning)
- W324: ensures without requires
- W325: explain without ensures (warning)
"""

from __future__ import annotations

from prove.ast_nodes import FunctionDef, IntegerLit, NearMiss
from prove.errors import Diagnostic, DiagnosticLabel, Severity
from prove.source import Span


class ProofVerifier:
    """Verify structural proof obligations for functions."""

    def __init__(self) -> None:
        self.diagnostics: list[Diagnostic] = []

    def verify(self, fd: FunctionDef) -> None:
        """Run all proof checks on a function."""
        self._check_ensures_proof(fd)
        self._check_obligation_uniqueness(fd)
        self._check_obligation_coverage(fd)
        self._check_proof_references(fd)
        self._check_near_miss_duplicates(fd)
        self._check_believe_without_ensures(fd)
        self._check_ensures_without_requires(fd)
        self._check_explain_ensures(fd)
        self._check_terminates(fd)

    def _error(self, code: str, message: str, span: Span) -> None:
        self.diagnostics.append(Diagnostic(
            severity=Severity.ERROR,
            code=code,
            message=message,
            labels=[DiagnosticLabel(span=span, message="")],
        ))

    def _warning(self, code: str, message: str, span: Span) -> None:
        self.diagnostics.append(Diagnostic(
            severity=Severity.WARNING,
            code=code,
            message=message,
            labels=[DiagnosticLabel(span=span, message="")],
        ))

    def _check_ensures_proof(self, fd: FunctionDef) -> None:
        """E390: ensures without proof block."""
        if fd.trusted:
            return  # trusted functions opt out of proof requirement
        if fd.ensures and fd.proof is None:
            self._error(
                "E390",
                f"function '{fd.name}' has ensures but no proof block",
                fd.span,
            )

    def _check_obligation_uniqueness(self, fd: FunctionDef) -> None:
        """E391: duplicate obligation names."""
        if fd.proof is None:
            return
        seen: set[str] = set()
        for obl in fd.proof.obligations:
            if obl.name in seen:
                self._error(
                    "E391",
                    f"duplicate proof obligation name '{obl.name}'",
                    obl.span,
                )
            seen.add(obl.name)

    def _check_obligation_coverage(self, fd: FunctionDef) -> None:
        """E392: obligations must cover ensures count."""
        if fd.proof is None or not fd.ensures:
            return
        if len(fd.proof.obligations) < len(fd.ensures):
            self._error(
                "E392",
                f"proof has {len(fd.proof.obligations)} obligation(s) "
                f"but {len(fd.ensures)} ensures clause(s)",
                fd.proof.span,
            )

    def _check_proof_references(self, fd: FunctionDef) -> None:
        """W321: proof text should reference function concepts."""
        if fd.proof is None:
            return
        # Collect relevant names: function name, param names
        concepts = {fd.name}
        for p in fd.params:
            concepts.add(p.name)
        concepts.add("result")

        for obl in fd.proof.obligations:
            # Structured conditions reference params directly — skip text check
            if obl.condition is not None:
                continue
            text_lower = obl.text.lower()
            if not any(c.lower() in text_lower for c in concepts):
                self._warning(
                    "W321",
                    f"proof obligation '{obl.name}' doesn't reference "
                    f"any function concepts ({', '.join(sorted(concepts))})",
                    obl.span,
                )

    def _check_near_miss_duplicates(self, fd: FunctionDef) -> None:
        """W322: duplicate near-miss inputs."""
        seen: list[NearMiss] = []
        for nm in fd.near_misses:
            for prev in seen:
                if self._exprs_equal(nm.input, prev.input):
                    self._warning(
                        "W322",
                        "duplicate near-miss input",
                        nm.span,
                    )
                    break
            seen.append(nm)

    def _check_believe_without_ensures(self, fd: FunctionDef) -> None:
        """E393: believe without ensures."""
        if fd.believe and not fd.ensures:
            self._error(
                "E393",
                f"function '{fd.name}' has believe but no ensures",
                fd.span,
            )

    def _check_ensures_without_requires(self, fd: FunctionDef) -> None:
        """W324: ensures without requires."""
        if fd.ensures and not fd.requires:
            self._warning(
                "W324",
                f"function '{fd.name}' has ensures but no requires",
                fd.span,
            )

    def _check_explain_ensures(self, fd: FunctionDef) -> None:
        """W323: ensures without explain. W325: explain without ensures."""
        if fd.trusted:
            return  # trusted functions opt out of verification
        if fd.ensures and not fd.explain:
            self._warning(
                "W323",
                f"function '{fd.name}' has ensures but no explain",
                fd.span,
            )
        if fd.explain and not fd.ensures:
            self._warning(
                "W325",
                f"function '{fd.name}' has explain but no ensures",
                fd.span,
            )

    def _check_terminates(self, fd: FunctionDef) -> None:
        """E366: recursive function missing terminates."""
        if fd.trusted:
            return  # trusted functions opt out
        if self._calls_self(fd.name, fd.body) and fd.terminates is None:
            self._error(
                "E366",
                f"recursive function '{fd.name}' missing terminates",
                fd.span,
            )

    def _calls_self(self, name: str, body: list) -> bool:
        """Check if a function body contains a recursive call to itself."""
        from prove.ast_nodes import (
            Assignment,
            ExprStmt,
            MatchExpr,
            VarDecl,
        )
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

    def _expr_calls(self, name: str, expr) -> bool:
        """Check if an expression contains a call to the named function."""
        from prove.ast_nodes import (
            Assignment,
            BinaryExpr,
            CallExpr,
            ExprStmt,
            FailPropExpr,
            IdentifierExpr,
            LambdaExpr,
            MatchExpr,
            PipeExpr,
            UnaryExpr,
            VarDecl,
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

    @staticmethod
    def _exprs_equal(a, b) -> bool:
        """Simple structural equality check for expressions."""
        if type(a) is not type(b):
            return False
        if isinstance(a, IntegerLit):
            return a.value == b.value
        return False
