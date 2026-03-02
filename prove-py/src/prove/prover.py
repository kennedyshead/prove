"""Structural verification for the Prove language.

Checks explain blocks for completeness and consistency:
- E391: duplicate entry names (error)
- E392: explain entries < ensures count (error)
- E393: believe without ensures (error)
- E366: recursive function missing terminates (error)
- W321: explain text doesn't reference function concepts
- W322: duplicate near-miss inputs
- W323: ensures without explain (warning, replaces E390)
- W324: ensures without requires
- W325: explain without ensures (warning)
- W326: recursion depth may be unbounded
"""

from __future__ import annotations

from prove.ast_nodes import FunctionDef, IdentifierExpr, IntegerLit, NearMiss
from prove.errors import DIAGNOSTIC_DOCS, Diagnostic, DiagnosticLabel, Severity
from prove.source import Span


class ProofVerifier:
    """Verify structural obligations for functions."""

    def __init__(self) -> None:
        self.diagnostics: list[Diagnostic] = []

    def verify(self, fd: FunctionDef) -> None:
        """Run all explain verification checks on a function."""
        self._check_ensures_explain(fd)
        self._check_entry_uniqueness(fd)
        self._check_entry_coverage(fd)
        self._check_explain_references(fd)
        self._check_near_miss_duplicates(fd)
        self._check_believe_without_ensures(fd)
        self._check_ensures_without_requires(fd)
        self._check_explain_without_ensures(fd)
        self._check_terminates(fd)
        self._check_recursion_depth(fd)

    def _error(self, code: str, message: str, span: Span) -> None:
        self.diagnostics.append(Diagnostic(
            severity=Severity.ERROR,
            code=code,
            message=message,
            labels=[DiagnosticLabel(span=span, message="")],
            doc_url=DIAGNOSTIC_DOCS.get(code),
        ))

    def _warning(self, code: str, message: str, span: Span) -> None:
        self.diagnostics.append(Diagnostic(
            severity=Severity.WARNING,
            code=code,
            message=message,
            labels=[DiagnosticLabel(span=span, message="")],
            doc_url=DIAGNOSTIC_DOCS.get(code),
        ))

    def _check_ensures_explain(self, fd: FunctionDef) -> None:
        """W323: ensures without explain block (warning, not error)."""
        if fd.trusted:
            return  # trusted functions opt out of verification
        if fd.ensures and not fd.explain:
            self._warning(
                "W323",
                f"Function '{fd.name}' has `ensures` but no `explain`. "
                f"Document how each step satisfies the contract.",
                fd.span,
            )

    def _check_entry_uniqueness(self, fd: FunctionDef) -> None:
        """E391: duplicate named entry names."""
        if fd.explain is None:
            return
        seen: set[str] = set()
        for entry in fd.explain.entries:
            if entry.name is None:
                continue  # prose entries have no name to clash
            if entry.name in seen:
                self._error(
                    "E391",
                    f"duplicate explain entry name '{entry.name}'",
                    entry.span,
                )
            seen.add(entry.name)

    def _check_entry_coverage(self, fd: FunctionDef) -> None:
        """E392: named entries must cover ensures count."""
        if fd.explain is None or not fd.ensures:
            return
        named = [e for e in fd.explain.entries if e.name is not None]
        if not named:
            return  # prose-only explain blocks don't need 1:1 coverage
        if len(named) < len(fd.ensures):
            self._error(
                "E392",
                f"explain has {len(named)} named entry/entries "
                f"but {len(fd.ensures)} ensures clause(s)",
                fd.explain.span,
            )

    def _check_explain_references(self, fd: FunctionDef) -> None:
        """W321: explain text should reference function concepts."""
        if fd.explain is None:
            return
        # Collect relevant names: function name, param names
        concepts = {fd.name}
        for p in fd.params:
            concepts.add(p.name)
        concepts.add("result")

        for entry in fd.explain.entries:
            # Structured conditions reference params directly — skip text check
            if entry.condition is not None:
                continue
            # Prose entries are documentation — skip text check
            if entry.name is None:
                continue
            text_lower = entry.text.lower()
            if not any(c.lower() in text_lower for c in concepts):
                self._warning(
                    "W321",
                    f"explain entry '{entry.name}' doesn't reference "
                    f"any function concepts ({', '.join(sorted(concepts))})",
                    entry.span,
                )

    def _check_near_miss_duplicates(self, fd: FunctionDef) -> None:
        """W322: duplicate near-miss inputs."""
        seen: list[NearMiss] = []
        for nm in fd.near_misses:
            for prev in seen:
                if self._exprs_equal(nm.input, prev.input):
                    self._warning(
                        "W322",
                        f"duplicate near-miss input "
                        f"(first defined at line {prev.span.start_line})",
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

    def _check_explain_without_ensures(self, fd: FunctionDef) -> None:
        """W325: explain without ensures."""
        if fd.trusted:
            return  # trusted functions opt out of verification
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

    def _check_recursion_depth(self, fd: FunctionDef) -> None:
        """W326: warn when recursive function may have unbounded call depth."""
        if fd.trusted:
            return
        if fd.terminates is None:
            return  # E366 already covers missing terminates
        if not self._calls_self(fd.name, fd.body):
            return
        # If any believe references recursion bounds, suppress
        if fd.believe:
            return
        self._warning(
            "W326",
            f"Recursive function '{fd.name}' may have O(n) call depth. "
            f"Consider an iterative approach or a logarithmic reduction.",
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
