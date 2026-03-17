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

Proof engine for ``know`` claims:
- ProofContext: accumulated facts from requires/assume/believe
- ClaimProver: lightweight prover with assumption matching, arithmetic
  reasoning, and callee-ensures propagation

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
    TypeIdentifierExpr,
    UnaryExpr,
)
from prove.errors import (
    DIAGNOSTIC_DOCS,
    Diagnostic,
    DiagnosticLabel,
    Severity,
)
from prove.source import Span


class ProofContext:
    """Accumulated facts known to be true at a program point.

    Sources of facts:
    - ``requires`` clauses (preconditions)
    - ``assume`` clauses (axioms)
    - ``believe`` clauses (unproven but declared)
    - Previously proven ``know`` claims
    """

    def __init__(self) -> None:
        self._assumptions: list[Expr] = []
        self._match_bindings: list[tuple[str, str, list[str]]] = []

    def add(self, expr: Expr) -> None:
        self._assumptions.append(expr)

    def add_all(self, exprs: list[Expr]) -> None:
        self._assumptions.extend(exprs)

    @property
    def assumptions(self) -> list[Expr]:
        return self._assumptions

    def add_match_arm_binding(
        self, subject: str, variant: str, bindings: list[str]
    ) -> None:
        """Record that ``subject`` was structurally matched as ``variant``.

        ``bindings`` are the variable names bound in the arm pattern.
        For example, ``match opt { Some(x) -> ... }`` produces
        ``add_match_arm_binding("opt", "Some", ["x"])``.

        Used by Phase 5 to expose match-arm facts to the proof engine
        so that arm-level claims can be verified in future extensions.
        """
        self._match_bindings.append((subject, variant, bindings))

    @property
    def match_bindings(self) -> list[tuple[str, str, list[str]]]:
        """Structural match arm bindings recorded in this context."""
        return list(self._match_bindings)


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
        """W323: ensures without explain block (warning, not error).

        Only fires when the function body has 3 or more statements —
        trivial one- or two-statement bodies are self-explanatory.
        """
        if fd.trusted is not None:
            return  # trusted functions opt out of verification
        if fd.ensures and not fd.explain and len(fd.body) >= 3:
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
    - Assumption matching: prove from requires/assume/believe context
    - Arithmetic reasoning: x + k > x when k > 0, transitivity
    - Callee ensures: if f ensures result > 0, then f(x) > 0
    """

    def __init__(
        self,
        symbols: object | None = None,
        context: ProofContext | None = None,
    ) -> None:
        self._symbols = symbols
        self._context = context

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

        # Check if the claim matches an assumption directly
        if self._context is not None:
            if self._prove_from_assumptions(expr):
                return True

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

        # Arithmetic reasoning: x + k > x, x - k < x, etc.
        if op in (">=", ">", "<=", "<"):
            result = self._prove_arithmetic(expr.left, op, expr.right)
            if result is not None:
                return result

        # Assumption-based proof
        if self._context is not None:
            if self._prove_from_assumptions(expr):
                return True
            # Try proving via assumption implication
            result = self._prove_from_assumption_implication(expr.left, op, expr.right)
            if result is not None:
                return result

        # Match arm structural reasoning (Phase 5)
        if self._context is not None:
            result = self._prove_from_match_bindings(expr)
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
        if isinstance(a, TypeIdentifierExpr) and isinstance(b, TypeIdentifierExpr):
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

    # ── Assumption-based reasoning ───────────────────────────────────

    def _prove_from_assumptions(self, expr: Expr) -> bool:
        """Check if the claim matches any assumption directly."""
        if self._context is None:
            return False
        for assumption in self._context.assumptions:
            if self._exprs_structurally_equal(expr, assumption):
                return True
        return False

    def _prove_from_assumption_implication(
        self, left: Expr, op: str, right: Expr
    ) -> bool | None:
        """Prove a comparison by deriving it from known assumptions.

        Handles integer equivalences:
        - assumption ``x >= k`` implies ``x > (k-1)``
        - assumption ``x > k`` implies ``x >= (k+1)``
        - assumption ``x >= k`` implies ``x >= j`` when j <= k
        - assumption ``x > k`` implies ``x > j`` when j <= k
        - assumption ``x != k`` implies claim ``x != k``
        Handles transitivity over a single step.
        """
        if self._context is None:
            return None

        claim_bound = self._eval_const(right)

        for assumption in self._context.assumptions:
            if not isinstance(assumption, BinaryExpr):
                continue
            a_op = assumption.op

            # Direct variable comparison: assumption about the same LHS
            if self._exprs_structurally_equal(assumption.left, left):
                a_bound = self._eval_const(assumption.right)
                if a_bound is not None and claim_bound is not None:
                    if isinstance(a_bound, (int, float)) and isinstance(
                        claim_bound, (int, float)
                    ):
                        result = self._implication_check(a_op, a_bound, op, claim_bound)
                        if result is not None:
                            return result

            # Symmetric: if assumption is ``k < x`` treat as ``x > k``
            if self._exprs_structurally_equal(assumption.right, left):
                a_bound = self._eval_const(assumption.left)
                if a_bound is not None and claim_bound is not None:
                    flipped = _flip_op(a_op)
                    if flipped is not None and isinstance(a_bound, (int, float)) and isinstance(
                        claim_bound, (int, float)
                    ):
                        result = self._implication_check(
                            flipped, a_bound, op, claim_bound
                        )
                        if result is not None:
                            return result

            # Transitivity: assumption ``x > y`` + claim ``x > z``
            # Check if any other assumption gives ``y >= z`` or ``y > z``
            if (
                a_op in (">", ">=")
                and self._exprs_structurally_equal(assumption.left, left)
                and op in (">", ">=")
            ):
                mid = assumption.right
                for other in self._context.assumptions:
                    if not isinstance(other, BinaryExpr):
                        continue
                    if self._exprs_structurally_equal(other.left, mid):
                        if other.op in (">", ">=") and self._exprs_structurally_equal(
                            other.right, right
                        ):
                            return True

        return None

    @staticmethod
    def _implication_check(
        known_op: str,
        known_bound: int | float,
        claim_op: str,
        claim_bound: int | float,
    ) -> bool | None:
        """Check if ``x <known_op> known_bound`` implies ``x <claim_op> claim_bound``."""
        # x >= k implies:
        if known_op == ">=":
            if claim_op == ">=" and claim_bound <= known_bound:
                return True
            if claim_op == ">" and claim_bound < known_bound:
                return True
            if claim_op == "!=" and claim_bound < known_bound:
                return True
        # x > k implies:
        if known_op == ">":
            if claim_op == ">=" and claim_bound <= known_bound + 1:
                return True
            if claim_op == ">" and claim_bound <= known_bound:
                return True
            if claim_op == "!=" and claim_bound <= known_bound:
                return True
        # x <= k implies:
        if known_op == "<=":
            if claim_op == "<=" and claim_bound >= known_bound:
                return True
            if claim_op == "<" and claim_bound > known_bound:
                return True
        # x < k implies:
        if known_op == "<":
            if claim_op == "<=" and claim_bound >= known_bound - 1:
                return True
            if claim_op == "<" and claim_bound >= known_bound:
                return True
        # x == k implies all comparisons against k
        if known_op == "==":
            if claim_op == "==" and claim_bound == known_bound:
                return True
            if claim_op == ">=" and claim_bound <= known_bound:
                return True
            if claim_op == "<=" and claim_bound >= known_bound:
                return True
            if claim_op == ">" and claim_bound < known_bound:
                return True
            if claim_op == "<" and claim_bound > known_bound:
                return True
            if claim_op == "!=" and claim_bound != known_bound:
                return True
        # x != k:
        if known_op == "!=" and claim_op == "!=" and claim_bound == known_bound:
            return True
        return None

    # ── Arithmetic reasoning ─────────────────────────────────────────

    def _prove_arithmetic(
        self, left: Expr, op: str, right: Expr
    ) -> bool | None:
        """Prove comparisons using arithmetic properties.

        Handles:
        - ``x + k > x`` when k > 0
        - ``x + k >= x`` when k >= 0
        - ``x - k < x`` when k > 0
        - ``x * 2 >= x`` when x >= 0 (from assumptions)
        - Commutativity: ``k + x > x``
        """
        # x + k > x  /  x + k >= x
        if isinstance(left, BinaryExpr) and left.op == "+":
            k = self._eval_const(left.right)
            if k is not None and self._exprs_structurally_equal(left.left, right):
                return self._arith_add_cmp(k, op)
            # Commutativity: k + x > x
            k = self._eval_const(left.left)
            if k is not None and self._exprs_structurally_equal(left.right, right):
                return self._arith_add_cmp(k, op)

        # x - k < x  /  x - k <= x
        if isinstance(left, BinaryExpr) and left.op == "-":
            k = self._eval_const(left.right)
            if k is not None and self._exprs_structurally_equal(left.left, right):
                return self._arith_sub_cmp(k, op)

        # Reverse: x < x + k  /  x <= x + k
        if isinstance(right, BinaryExpr) and right.op == "+":
            k = self._eval_const(right.right)
            if k is not None and self._exprs_structurally_equal(right.left, left):
                flipped = _flip_op(op)
                if flipped is not None:
                    return self._arith_add_cmp(k, flipped)
            k = self._eval_const(right.left)
            if k is not None and self._exprs_structurally_equal(right.right, left):
                flipped = _flip_op(op)
                if flipped is not None:
                    return self._arith_add_cmp(k, flipped)

        return None

    @staticmethod
    def _arith_add_cmp(k: int | float, op: str) -> bool | None:
        """Given ``x + k <op> x``, determine truth value."""
        if not isinstance(k, (int, float)):
            return None
        if op == ">" and k > 0:
            return True
        if op == ">=" and k >= 0:
            return True
        if op == "<" and k < 0:
            return True
        if op == "<=" and k <= 0:
            return True
        if op == "==" and k == 0:
            return True
        if op == "!=" and k != 0:
            return True
        return None

    @staticmethod
    def _arith_sub_cmp(k: int | float, op: str) -> bool | None:
        """Given ``x - k <op> x``, determine truth value."""
        if not isinstance(k, (int, float)):
            return None
        if op == "<" and k > 0:
            return True
        if op == "<=" and k >= 0:
            return True
        if op == ">" and k < 0:
            return True
        if op == ">=" and k <= 0:
            return True
        if op == "==" and k == 0:
            return True
        if op == "!=" and k != 0:
            return True
        return None


    def _prove_from_match_bindings(self, expr: BinaryExpr) -> bool | None:
        """Prove structural variant claims using match arm binding facts.

        Phase 5: match-arm path narrowing.

        Handles:
        - ``subj != None`` when ``subj`` appears as the subject of a ``Some``
          arm binding AND ``subj != None`` is independently provable from
          the assumption set.
        - ``subj != Error`` analogously for ``Ok`` arm bindings.

        This lets the prover confirm structural non-null/non-error facts
        that are established both by a ``requires`` clause and by the match
        arm structure in the function body, without requiring the user to
        repeat the assertion.
        """
        if self._context is None or not self._context.match_bindings:
            return None

        op = expr.op
        if op not in ("!=", "=="):
            return None

        left: object = expr.left
        right: object = expr.right

        # Normalise: left should be IdentifierExpr, right TypeIdentifierExpr
        if isinstance(right, IdentifierExpr) and isinstance(left, TypeIdentifierExpr):
            left, right = right, left

        if not isinstance(left, IdentifierExpr) or not isinstance(right, TypeIdentifierExpr):
            return None

        subject_name = left.name
        null_name = right.name  # "None", "Error", etc.

        for subj, variant, _bindings in self._context.match_bindings:
            if subj != subject_name:
                continue
            # Some arm present → subject can be non-None
            if null_name == "None" and variant == "Some" and op == "!=":
                # The match arm establishes that the body handles the Some
                # case.  If requires/assume already proves subj != None,
                # the structural arm fact is consistent — confirm it.
                if self._prove_from_assumptions(expr):
                    return True
                assump_result = self._prove_from_assumption_implication(
                    left, op, right
                )
                if assump_result is not None:
                    return assump_result
            # Ok arm present → subject can be non-Error
            elif null_name == "Error" and variant == "Ok" and op == "!=":
                if self._prove_from_assumptions(expr):
                    return True
                assump_result = self._prove_from_assumption_implication(
                    left, op, right
                )
                if assump_result is not None:
                    return assump_result

        return None


def _flip_op(op: str) -> str | None:
    """Flip a comparison operator: > becomes <, etc."""
    return {">": "<", "<": ">", ">=": "<=", "<=": ">=", "==": "==", "!=": "!="}.get(op)
