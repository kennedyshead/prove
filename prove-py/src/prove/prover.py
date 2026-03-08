"""Structural verification for the Prove language.

Checks explain blocks for completeness and consistency:
- E391: duplicate entry names (error)
- E392: explain entries < ensures count (error)
- E393: believe without ensures (error)
- W321: explain text doesn't reference function concepts
- W322: duplicate near-miss inputs
- W323: ensures without explain (warning, replaces E390)
- W324: ensures without requires
- W325: explain without ensures (warning)
- W327: know claim cannot be proven (falls back to runtime assertion)

Note: E366 (recursive function missing terminates) and W326 (recursion depth)
are now handled by the Checker, which has access to the symbol table for
verb-aware function resolution.
"""

from __future__ import annotations

from prove.ast_nodes import (
    BinaryExpr,
    BooleanLit,
    CallExpr,
    DecimalLit,
    Expr,
    FieldExpr,
    FloatLit,
    FunctionDef,
    IdentifierExpr,
    IntegerLit,
    NearMiss,
    UnaryExpr,
)
from prove.errors import (
    DIAGNOSTIC_DOCS,
    Diagnostic,
    DiagnosticLabel,
    Severity,
)
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

    def _error(self, code: str, message: str, span: Span) -> None:
        self.diagnostics.append(
            Diagnostic(
                severity=Severity.ERROR,
                code=code,
                message=message,
                labels=[DiagnosticLabel(span=span, message="")],
                doc_url=DIAGNOSTIC_DOCS.get(code),
            )
        )

    def _warning(self, code: str, message: str, span: Span) -> None:
        self.diagnostics.append(
            Diagnostic(
                severity=Severity.WARNING,
                code=code,
                message=message,
                labels=[DiagnosticLabel(span=span, message="")],
                doc_url=DIAGNOSTIC_DOCS.get(code),
            )
        )

    def _check_ensures_explain(self, fd: FunctionDef) -> None:
        """W323: ensures without explain block (warning, not error)."""
        if fd.trusted is not None:
            return  # trusted functions opt out of verification
        if fd.ensures and not fd.explain:
            self.diagnostics.append(
                Diagnostic(
                    severity=Severity.WARNING,
                    code="W323",
                    message=(
                        f"Function '{fd.name}' has `ensures` but no `explain`. "
                        f"Document how each step satisfies the contract."
                    ),
                    labels=[DiagnosticLabel(span=fd.span, message="")],
                    notes=[
                        "Add an `explain` block with entries describing how "
                        "the implementation satisfies each postcondition.",
                    ],
                    doc_url=DIAGNOSTIC_DOCS.get("W323"),
                )
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
                self.diagnostics.append(
                    Diagnostic(
                        severity=Severity.WARNING,
                        code="W321",
                        message=(
                            f"explain entry '{entry.name}' doesn't reference "
                            f"any function concepts "
                            f"({', '.join(sorted(concepts))})"
                        ),
                        labels=[DiagnosticLabel(span=entry.span, message="")],
                        notes=[
                            "Mention at least one of the listed concepts "
                            "(parameter names, function name, or `result`) "
                            "so the explanation ties back to the code.",
                        ],
                        doc_url=DIAGNOSTIC_DOCS.get("W321"),
                    )
                )

    def _check_near_miss_duplicates(self, fd: FunctionDef) -> None:
        """W322: duplicate near-miss inputs."""
        seen: list[NearMiss] = []
        for nm in fd.near_misses:
            for prev in seen:
                if self._exprs_equal(nm.input, prev.input):
                    self.diagnostics.append(
                        Diagnostic(
                            severity=Severity.WARNING,
                            code="W322",
                            message=(
                                f"duplicate near-miss input "
                                f"(first defined at line "
                                f"{prev.span.start_line})"
                            ),
                            labels=[
                                DiagnosticLabel(
                                    span=nm.span,
                                    message="",
                                )
                            ],
                            notes=[
                                "Remove the duplicate or change "
                                "the input to test a different edge case.",
                            ],
                            doc_url=DIAGNOSTIC_DOCS.get("W322"),
                        )
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
            self.diagnostics.append(
                Diagnostic(
                    severity=Severity.WARNING,
                    code="W324",
                    message=(f"function '{fd.name}' has ensures but no requires"),
                    labels=[DiagnosticLabel(span=fd.span, message="")],
                    notes=[
                        "Add a `requires` clause to specify input "
                        "constraints. The compiler uses requires/ensures "
                        "pairs to reason about correctness.",
                    ],
                    doc_url=DIAGNOSTIC_DOCS.get("W324"),
                )
            )

    def _check_explain_without_ensures(self, fd: FunctionDef) -> None:
        """W325: explain without ensures."""
        if fd.trusted is not None:
            return  # trusted functions opt out of verification
        if fd.explain and not fd.ensures:
            self.diagnostics.append(
                Diagnostic(
                    severity=Severity.WARNING,
                    code="W325",
                    message=(f"function '{fd.name}' has explain but no ensures"),
                    labels=[DiagnosticLabel(span=fd.span, message="")],
                    notes=[
                        "Add `ensures` clauses so the `explain` block has "
                        "contracts to document. Without postconditions, "
                        "the explanation is unverifiable.",
                    ],
                    doc_url=DIAGNOSTIC_DOCS.get("W325"),
                )
            )

    @staticmethod
    def _exprs_equal(a: object, b: object) -> bool:
        """Simple structural equality check for expressions."""
        if type(a) is not type(b):
            return False
        if isinstance(a, IntegerLit) and isinstance(b, IntegerLit):
            return a.value == b.value
        return False


class ClaimProver:
    """Lightweight proof engine for `know` claims.

    Attempts to prove boolean expressions using:
    - Constant folding: know 2 + 2 == 4 → trivially true
    - Type-based: know x > 0 when x has refinement >= 1 → true
    - Algebraic simplification: x + 0 == x, x * 1 == x, x - x == 0
    """

    def __init__(self, symbols: object | None = None) -> None:
        self._symbols = symbols

    def prove_claim(self, expr: Expr) -> bool | None:
        """Attempt to prove a boolean expression.

        Returns True (proven), False (disproven), or None (indeterminate).
        """
        # Direct boolean literal
        if isinstance(expr, BooleanLit):
            return expr.value

        # Binary comparison with constants
        if isinstance(expr, BinaryExpr):
            return self._prove_binary(expr)

        # Unary negation
        if isinstance(expr, UnaryExpr) and expr.op in ("!", "not"):
            inner = self.prove_claim(expr.operand)
            if inner is not None:
                return not inner

        return None

    def _prove_binary(self, expr: BinaryExpr) -> bool | None:
        """Prove a binary expression."""
        op = expr.op

        # Boolean combinators
        if op in ("&&", "and"):
            left = self.prove_claim(expr.left)
            right = self.prove_claim(expr.right)
            if left is False or right is False:
                return False
            if left is True and right is True:
                return True
            return None

        if op in ("||", "or"):
            left = self.prove_claim(expr.left)
            right = self.prove_claim(expr.right)
            if left is True or right is True:
                return True
            if left is False and right is False:
                return False
            return None

        # Comparison with constant values
        left_val = self._eval_const(expr.left)
        right_val = self._eval_const(expr.right)

        if left_val is not None and right_val is not None:
            if op == "==":
                return left_val == right_val
            if op == "!=":
                return left_val != right_val
            if op == ">":
                return left_val > right_val
            if op == ">=":
                return left_val >= right_val
            if op == "<":
                return left_val < right_val
            if op == "<=":
                return left_val <= right_val

        # Algebraic identity: x == x → true
        if op == "==" and self._exprs_structurally_equal(expr.left, expr.right):
            return True

        # Algebraic identity: x != x → false
        if op == "!=" and self._exprs_structurally_equal(expr.left, expr.right):
            return False

        # Algebraic identity: x - x == 0
        if op == "==" and isinstance(expr.left, BinaryExpr) and expr.left.op == "-":
            if self._exprs_structurally_equal(expr.left.left, expr.left.right):
                right_val = self._eval_const(expr.right)
                if right_val == 0:
                    return True

        # Type-based proof: check if identifier has a refinement type
        # that makes the claim trivially true
        if self._symbols is not None and op in (">=", ">", "<=", "<", "!=", "=="):
            result = self._prove_from_refinement(expr.left, op, expr.right)
            if result is not None:
                return result

        return None

    def _eval_const(self, expr: Expr) -> int | float | str | bool | None:
        """Extract a constant value from an expression."""
        if isinstance(expr, IntegerLit):
            return int(expr.value)
        if isinstance(expr, DecimalLit):
            return float(expr.value)
        if isinstance(expr, FloatLit):
            return float(expr.value[:-1])
        if isinstance(expr, BooleanLit):
            return expr.value

        # Constant folding for simple arithmetic
        if isinstance(expr, BinaryExpr):
            left = self._eval_const(expr.left)
            right = self._eval_const(expr.right)
            if left is not None and right is not None:
                if isinstance(left, (int, float)) and isinstance(right, (int, float)):
                    op = expr.op
                    if op == "+":
                        return left + right
                    if op == "-":
                        return left - right
                    if op == "*":
                        return left * right
                    if op == "%" and right != 0:
                        return left % right

        if isinstance(expr, UnaryExpr) and expr.op == "-":
            inner = self._eval_const(expr.operand)
            if isinstance(inner, (int, float)):
                return -inner

        return None

    def _exprs_structurally_equal(self, a: Expr, b: Expr) -> bool:
        """Check structural equality of two expressions."""
        if type(a) is not type(b):
            return False
        if isinstance(a, IdentifierExpr) and isinstance(b, IdentifierExpr):
            return a.name == b.name
        if isinstance(a, IntegerLit) and isinstance(b, IntegerLit):
            return a.value == b.value
        if isinstance(a, FieldExpr) and isinstance(b, FieldExpr):
            return a.field == b.field and self._exprs_structurally_equal(a.obj, b.obj)
        if isinstance(a, BinaryExpr) and isinstance(b, BinaryExpr):
            return (
                a.op == b.op
                and self._exprs_structurally_equal(a.left, b.left)
                and self._exprs_structurally_equal(a.right, b.right)
            )
        return False

    def _prove_from_refinement(self, expr: Expr, op: str, bound: Expr) -> bool | None:
        """Try to prove a comparison from a variable's refinement type."""
        if not isinstance(expr, IdentifierExpr) or self._symbols is None:
            return None

        sym = self._symbols.lookup(expr.name)
        if sym is None:
            return None

        from prove.types import RefinementType

        ty = sym.resolved_type
        if not isinstance(ty, RefinementType) or ty.constraint is None:
            return None

        # Extract refinement bound: e.g., Integer where >= 1
        ref_op, ref_val = self._extract_refinement_bound(ty.constraint)
        if ref_op is None or ref_val is None:
            return None

        bound_val = self._eval_const(bound)
        if bound_val is None:
            return None

        # Now reason: if refinement says x >= 1, and claim is x > 0, then true
        if ref_op == ">=" and isinstance(ref_val, (int, float)):
            if op == ">=" and bound_val <= ref_val:
                return True
            if op == ">" and bound_val < ref_val:
                return True
            if op == "!=" and bound_val < ref_val:
                return True

        if ref_op == ">" and isinstance(ref_val, (int, float)):
            if op == ">=" and bound_val <= ref_val:
                return True
            if op == ">" and bound_val <= ref_val:
                return True
            if op == "!=" and bound_val <= ref_val:
                return True

        if ref_op == "!=" and ref_val == bound_val:
            if op == "!=":
                return True

        return None

    def _extract_refinement_bound(
        self, constraint: Expr
    ) -> tuple[str | None, int | float | None]:
        """Extract the operator and bound from a refinement constraint."""
        if isinstance(constraint, BinaryExpr):
            # self >= 0 → (">=", 0)
            if isinstance(constraint.left, IdentifierExpr) and constraint.left.name == "self":
                val = self._eval_const(constraint.right)
                return (constraint.op, val)
            # Range: 1..65535 → (">=", 1)
            if constraint.op == "..":
                val = self._eval_const(constraint.left)
                return (">=", val)
        return (None, None)
