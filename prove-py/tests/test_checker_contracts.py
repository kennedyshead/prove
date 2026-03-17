"""Tests for contract checking in the Prove semantic analyzer."""

from __future__ import annotations

from prove.ast_nodes import BinaryExpr, BooleanLit, IntegerLit, IdentifierExpr, UnaryExpr
from prove.prover import ClaimProver, ProofContext
from prove.source import Span
from tests.helpers import check, check_coherence_ok, check_coherence_warns, check_fails, check_warns


class TestContractChecking:
    """Test type-checking of ensures/requires/know/assume/believe contracts."""

    def test_ensures_boolean_ok(self):
        check(
            "transforms add(a Integer, b Integer) Integer\n"
            "    ensures result == a + b\n"
            "    explain\n"
            "        sum a and b\n"
            "    from\n"
            "        a + b\n"
        )

    def test_ensures_non_boolean_error(self):
        check_fails(
            "transforms bad(a Integer) Integer\n"
            "    ensures result + 1\n"
            "    from\n"
            "        a\n",
            "E380",
        )

    def test_requires_boolean_ok(self):
        check(
            "transforms safe_div(a Integer, b Integer) Integer\n"
            "    requires b != 0\n"
            "    from\n"
            "        a\n"
        )

    def test_requires_non_boolean_error(self):
        check_fails(
            "transforms bad(a Integer) Integer\n"
            "    requires a + 1\n"
            "    from\n"
            "        a\n",
            "E381",
        )

    def test_know_boolean_ok(self):
        check(
            "transforms safe(a Integer) Integer\n"
            "    know: a > 0\n"
            "    from\n"
            "        a\n"
        )

    def test_know_non_boolean_error(self):
        check_fails(
            "transforms bad(a Integer) Integer\n"
            "    know: a + 1\n"
            "    from\n"
            "        a\n",
            "E384",
        )

    def test_assume_boolean_ok(self):
        check(
            "transforms safe(a Integer) Integer\n"
            "    assume: a > 0\n"
            "    from\n"
            "        a\n"
        )

    def test_assume_non_boolean_error(self):
        check_fails(
            "transforms bad(a Integer) Integer\n"
            "    assume: a + 1\n"
            "    from\n"
            "        a\n",
            "E385",
        )

    def test_believe_boolean_ok(self):
        check(
            "matches abs_val(n Integer) Integer\n"
            "    ensures result >= 0\n"
            "    believe: result >= 0\n"
            "    explain\n"
            "        negate if negative\n"
            "    from\n"
            "        match n >= 0\n"
            "            true => n\n"
            "            false => 0 - n\n"
        )

    def test_believe_non_boolean_error(self):
        check_fails(
            "transforms bad(a Integer) Integer\n"
            "    believe: result + 1\n"
            "    from\n"
            "        a\n",
            "E386",
        )

    def test_satisfies_undefined_type_error(self):
        check_fails(
            "transforms bad(a Integer) Integer\n"
            "    satisfies Nonexistent\n"
            "    from\n"
            "        a\n",
            "E382",
        )

    def test_satisfies_valid_type(self):
        check(
            "module M\n"
            "  type Positive is Integer where >= 0\n"
            "transforms identity(a Integer) Integer\n"
            "    satisfies Positive\n"
            "    from\n"
            "        a\n"
        )

    def test_intent_without_contracts_warning(self):
        check_warns(
            "transforms add(a Integer, b Integer) Integer\n"
            "    intent: \"add two numbers\"\n"
            "    from\n"
            "        a + b\n",
            "W311",
        )


class TestNearMissTypeChecking:
    """Test type-checking of near_miss expected expressions (E383)."""

    def test_near_miss_expected_type_mismatch(self):
        """near_miss 1 => false on Integer-returning function → E383."""
        check_fails(
            "transforms f(n Integer) Integer\n"
            "    near_miss 1 => false\n"
            "    from\n"
            "        n\n",
            "E383",
        )

    def test_near_miss_expected_type_ok(self):
        """near_miss 1 => 42 on Integer-returning function → passes."""
        check(
            "transforms f(n Integer) Integer\n"
            "    near_miss 1 => 42\n"
            "    from\n"
            "        n\n"
        )

    def test_near_miss_validates_boolean_ok(self):
        """near_miss 0 => false on validates function → passes (returns Boolean)."""
        check(
            "validates f(n Integer)\n"
            "    near_miss 0 => false\n"
            "    from\n"
            "        n > 0\n"
        )

    def test_near_miss_string_mismatch(self):
        """near_miss 1 => 'hello' on Integer-returning function → E383."""
        check_fails(
            "transforms f(n Integer) Integer\n"
            '    near_miss 1 => "hello"\n'
            "    from\n"
            "        n\n",
            "E383",
        )


class TestEnsuresWithoutResult:
    """Test W328: ensures clause doesn't reference result."""

    def test_ensures_without_result_warns(self):
        """ensures a > 0 doesn't reference result → W328."""
        check_warns(
            "transforms f(a Integer) Integer\n"
            "    ensures a > 0\n"
            "    explain\n"
            "        check a\n"
            "    from\n"
            "        a\n",
            "W328",
        )

    def test_ensures_with_result_ok(self):
        """ensures result > 0 references result → no W328."""
        check(
            "transforms f(a Integer) Integer\n"
            "    ensures result > 0\n"
            "    explain\n"
            "        check result\n"
            "    from\n"
            "        a\n"
        )

    def test_ensures_result_in_field_ok(self):
        """ensures result.x > 0 references result via field → no W328."""
        check(
            "module M\n"
            "  type Point is\n"
            "    x Integer\n"
            "    y Integer\n"
            "\n"
            "transforms make_point(n Integer) Point\n"
            "    ensures result.x > 0\n"
            "    explain\n"
            "        check result x\n"
            "    from\n"
            "        Point(n, n)\n"
        )

    def test_ensures_result_in_call_ok(self):
        """ensures len(result) > 0 references result in call arg → no W328."""
        check(
            "transforms f(a List<Integer>) List<Integer>\n"
            "    ensures len(result) > 0\n"
            "    explain\n"
            "        check result length\n"
            "    from\n"
            "        a\n"
        )

    def test_ensures_validates_no_result_ok(self):
        """validates ensures without result is OK — validates checks input conditions."""
        check(
            "validates positive(n Integer)\n"
            "    ensures n > 0\n"
            "    from\n"
            "        n > 0\n"
        )

    def test_ensures_valid_expr_no_result_ok(self):
        """ensures valid expr without result is OK — validation postconditions."""
        check(
            "validates ok(s String)\n"
            "    from\n"
            "        true\n"
            "\n"
            "transforms f(s String) String\n"
            "    ensures valid ok(s)\n"
            "    explain\n"
            "        check s\n"
            "    from\n"
            "        s\n"
        )


class TestExplainConditionChecking:
    """Test type-checking of explain entry conditions."""

    def test_boolean_condition_ok(self):
        check(
            "transforms abs(n Integer) Integer\n"
            "    ensures result >= 0\n"
            "    explain\n"
            "        positive: identity when n >= 0\n"
            "        negative: deducted when n < 0\n"
            "    from\n"
            "        n\n"
            "        0 - n\n"
        )

    def test_non_boolean_condition_error(self):
        check_fails(
            "transforms bad(n Integer) Integer\n"
            "    ensures result >= 0\n"
            "    explain\n"
            "        wrong: bad when n + 1\n"
            "    from\n"
            "        n\n",
            "E394",
        )

    def test_undefined_name_in_condition(self):
        check_fails(
            "transforms bad(n Integer) Integer\n"
            "    ensures result >= 0\n"
            "    explain\n"
            "        wrong: bad when x > 0\n"
            "    from\n"
            "        n\n",
            "E310",
        )


class TestRequiresOptionNarrowing:
    """Test that requires Table.has(k, t) narrows Table.get(k, t) from Option<Value> to Value."""

    def test_narrowed_get_infers_inner_type(self):
        """With requires Table.has(k, t), Table.get(k, t) should narrow to Value."""
        # If narrowing works, assigning Table.get result to a String var should pass
        check(
            "module Main\n"
            "  Table types Table Value, creates new, validates has,"
            " reads get, transforms add\n"
            "\n"
            "reads lookup(key String, table Table<String>) String\n"
            "    requires Table.has(key, table)\n"
            "    from\n"
            "        Table.get(key, table)\n"
        )

    def test_no_narrowing_without_requires(self):
        """Without requires, Table.get returns Option<Value> — E322 mismatch."""
        check_fails(
            "module Main\n"
            "  Table types Table Value, creates new, validates has, reads get\n"
            "\n"
            "reads lookup(key String, table Table<String>) String\n"
            "    from\n"
            "        Table.get(key, table)\n",
            "E322",
        )

    def test_unqualified_narrowing(self):
        """Unqualified has/get should narrow when sig.module matches."""
        check(
            "module Main\n"
            "  Table types Table Value, creates new, validates has,"
            " reads get, transforms add\n"
            "\n"
            "reads lookup(key String, table Table<String>) String\n"
            "    requires has(key, table)\n"
            "    from\n"
            "        get(key, table)\n"
        )

    def test_narrowing_requires_mismatched_args(self):
        """Narrowing only applies when call args match requires args."""
        # Different arg names → no narrowing → E322
        check_fails(
            "module Main\n"
            "  Table types Table Value, creates new, validates has, reads get\n"
            "\n"
            "reads lookup(k1 String, k2 String, table Table<String>) String\n"
            "    requires Table.has(k1, table)\n"
            "    from\n"
            "        Table.get(k2, table)\n",
            "E322",
        )


# ── requires valid type checking ─────────────────────────────────────


class TestRequiresValidTypeChecking:
    """Test that requires valid clauses type-check their arguments."""

    def test_incompatible_param_type_error(self):
        """E331: requires valid expects Integer but receives String — genuinely incompatible."""
        check_fails(
            "module M\n"
            "\n"
            "validates positive(n Integer) Boolean\n"
            "    from\n"
            "        n > 0\n"
            "\n"
            "transforms extract(data String) String\n"
            "    requires valid positive(data)\n"
            "    from\n"
            "        data\n",
            "E331",
        )

    def test_matching_type_no_error(self):
        """No E331 when requires valid argument type matches the validator parameter."""
        check(
            "module M\n"
            "  type Payload is\n"
            "    data String\n"
            "\n"
            "validates object(v Payload) Boolean\n"
            "    from\n"
            "        true\n"
            "\n"
            "transforms extract(data Payload) String\n"
            "    requires valid object(data)\n"
            "    from\n"
            "        data.data\n"
        )


# ── ClaimProver unit tests ─────────────────────────────────────────────


def _span() -> Span:
    return Span(file="test", start_line=1, start_col=1, end_line=1, end_col=1)


def _int(val: int) -> IntegerLit:
    return IntegerLit(value=str(val), span=_span())


def _bool(val: bool) -> BooleanLit:
    return BooleanLit(value=val, span=_span())


def _ident(name: str) -> IdentifierExpr:
    return IdentifierExpr(name=name, span=_span())


def _binop(left, op: str, right) -> BinaryExpr:
    return BinaryExpr(left=left, op=op, right=right, span=_span())


def _unary(op: str, operand) -> UnaryExpr:
    return UnaryExpr(op=op, operand=operand, span=_span())


class TestClaimProver:
    """Unit tests for ClaimProver proof engine."""

    def test_true_literal(self):
        prover = ClaimProver()
        assert prover.prove_claim(_bool(True)) is True

    def test_false_literal(self):
        prover = ClaimProver()
        assert prover.prove_claim(_bool(False)) is False

    def test_constant_equality_true(self):
        prover = ClaimProver()
        expr = _binop(_int(2), "==", _int(2))
        assert prover.prove_claim(expr) is True

    def test_constant_equality_false(self):
        prover = ClaimProver()
        expr = _binop(_int(2), "==", _int(3))
        assert prover.prove_claim(expr) is False

    def test_constant_inequality(self):
        prover = ClaimProver()
        expr = _binop(_int(2), "!=", _int(3))
        assert prover.prove_claim(expr) is True

    def test_constant_greater(self):
        prover = ClaimProver()
        assert prover.prove_claim(_binop(_int(5), ">", _int(3))) is True
        assert prover.prove_claim(_binop(_int(3), ">", _int(5))) is False

    def test_constant_less_equal(self):
        prover = ClaimProver()
        assert prover.prove_claim(_binop(_int(3), "<=", _int(5))) is True
        assert prover.prove_claim(_binop(_int(5), "<=", _int(3))) is False

    def test_arithmetic_folding(self):
        prover = ClaimProver()
        # 2 + 2 == 4
        add = _binop(_int(2), "+", _int(2))
        expr = _binop(add, "==", _int(4))
        assert prover.prove_claim(expr) is True

    def test_arithmetic_folding_false(self):
        prover = ClaimProver()
        # 2 + 2 == 5
        add = _binop(_int(2), "+", _int(2))
        expr = _binop(add, "==", _int(5))
        assert prover.prove_claim(expr) is False

    def test_algebraic_identity_x_eq_x(self):
        prover = ClaimProver()
        expr = _binop(_ident("x"), "==", _ident("x"))
        assert prover.prove_claim(expr) is True

    def test_algebraic_identity_x_neq_x(self):
        prover = ClaimProver()
        expr = _binop(_ident("x"), "!=", _ident("x"))
        assert prover.prove_claim(expr) is False

    def test_algebraic_identity_x_minus_x_eq_0(self):
        prover = ClaimProver()
        sub = _binop(_ident("x"), "-", _ident("x"))
        expr = _binop(sub, "==", _int(0))
        assert prover.prove_claim(expr) is True

    def test_boolean_and_both_true(self):
        prover = ClaimProver()
        expr = _binop(_bool(True), "&&", _bool(True))
        assert prover.prove_claim(expr) is True

    def test_boolean_and_one_false(self):
        prover = ClaimProver()
        expr = _binop(_bool(True), "&&", _bool(False))
        assert prover.prove_claim(expr) is False

    def test_boolean_or_one_true(self):
        prover = ClaimProver()
        expr = _binop(_bool(False), "||", _bool(True))
        assert prover.prove_claim(expr) is True

    def test_boolean_or_both_false(self):
        prover = ClaimProver()
        expr = _binop(_bool(False), "||", _bool(False))
        assert prover.prove_claim(expr) is False

    def test_unary_not_true(self):
        prover = ClaimProver()
        expr = _unary("!", _bool(True))
        assert prover.prove_claim(expr) is False

    def test_unary_not_false(self):
        prover = ClaimProver()
        expr = _unary("!", _bool(False))
        assert prover.prove_claim(expr) is True

    def test_indeterminate_variable(self):
        prover = ClaimProver()
        # x > 0 with no symbol table → indeterminate
        expr = _binop(_ident("x"), ">", _int(0))
        assert prover.prove_claim(expr) is None

    def test_negation_of_indeterminate(self):
        prover = ClaimProver()
        # !(x > 0) → indeterminate
        inner = _binop(_ident("x"), ">", _int(0))
        expr = _unary("!", inner)
        assert prover.prove_claim(expr) is None


class TestProofContext:
    """Unit tests for ProofContext-based assumption matching."""

    def test_direct_assumption_match(self):
        """Claim matches assumption exactly."""
        ctx = ProofContext()
        ctx.add(_binop(_ident("x"), ">", _int(0)))
        prover = ClaimProver(context=ctx)
        assert prover.prove_claim(_binop(_ident("x"), ">", _int(0))) is True

    def test_no_match_without_assumption(self):
        """Claim with no matching assumption remains indeterminate."""
        ctx = ProofContext()
        prover = ClaimProver(context=ctx)
        assert prover.prove_claim(_binop(_ident("x"), ">", _int(0))) is None

    def test_implication_ge_implies_gt(self):
        """x >= 1 implies x > 0."""
        ctx = ProofContext()
        ctx.add(_binop(_ident("x"), ">=", _int(1)))
        prover = ClaimProver(context=ctx)
        assert prover.prove_claim(_binop(_ident("x"), ">", _int(0))) is True

    def test_implication_gt_implies_ge(self):
        """x > 0 implies x >= 1."""
        ctx = ProofContext()
        ctx.add(_binop(_ident("x"), ">", _int(0)))
        prover = ClaimProver(context=ctx)
        assert prover.prove_claim(_binop(_ident("x"), ">=", _int(1))) is True

    def test_implication_ge_weaker_bound(self):
        """x >= 5 implies x >= 3."""
        ctx = ProofContext()
        ctx.add(_binop(_ident("x"), ">=", _int(5)))
        prover = ClaimProver(context=ctx)
        assert prover.prove_claim(_binop(_ident("x"), ">=", _int(3))) is True

    def test_implication_gt_weaker_bound(self):
        """x > 5 implies x > 3."""
        ctx = ProofContext()
        ctx.add(_binop(_ident("x"), ">", _int(5)))
        prover = ClaimProver(context=ctx)
        assert prover.prove_claim(_binop(_ident("x"), ">", _int(3))) is True

    def test_implication_eq_implies_ge(self):
        """x == 5 implies x >= 3."""
        ctx = ProofContext()
        ctx.add(_binop(_ident("x"), "==", _int(5)))
        prover = ClaimProver(context=ctx)
        assert prover.prove_claim(_binop(_ident("x"), ">=", _int(3))) is True

    def test_implication_neq_from_neq(self):
        """x != 0 implies x != 0."""
        ctx = ProofContext()
        ctx.add(_binop(_ident("x"), "!=", _int(0)))
        prover = ClaimProver(context=ctx)
        assert prover.prove_claim(_binop(_ident("x"), "!=", _int(0))) is True

    def test_no_false_implication(self):
        """x >= 3 does NOT imply x >= 5."""
        ctx = ProofContext()
        ctx.add(_binop(_ident("x"), ">=", _int(3)))
        prover = ClaimProver(context=ctx)
        assert prover.prove_claim(_binop(_ident("x"), ">=", _int(5))) is None

    def test_multiple_assumptions(self):
        """Multiple assumptions, second one matches."""
        ctx = ProofContext()
        ctx.add(_binop(_ident("y"), ">", _int(10)))
        ctx.add(_binop(_ident("x"), "!=", _int(0)))
        prover = ClaimProver(context=ctx)
        assert prover.prove_claim(_binop(_ident("x"), "!=", _int(0))) is True


class TestArithmeticReasoning:
    """Unit tests for arithmetic reasoning in ClaimProver."""

    def test_x_plus_k_gt_x(self):
        """x + 1 > x is always true."""
        prover = ClaimProver()
        left = _binop(_ident("x"), "+", _int(1))
        assert prover.prove_claim(_binop(left, ">", _ident("x"))) is True

    def test_x_plus_k_ge_x(self):
        """x + 0 >= x is always true."""
        prover = ClaimProver()
        left = _binop(_ident("x"), "+", _int(0))
        assert prover.prove_claim(_binop(left, ">=", _ident("x"))) is True

    def test_x_plus_negative_lt_x(self):
        """x + (-1) < x is always true."""
        prover = ClaimProver()
        left = _binop(_ident("x"), "+", _unary("-", _int(1)))
        assert prover.prove_claim(_binop(left, "<", _ident("x"))) is True

    def test_x_minus_k_lt_x(self):
        """x - 1 < x is always true."""
        prover = ClaimProver()
        left = _binop(_ident("x"), "-", _int(1))
        assert prover.prove_claim(_binop(left, "<", _ident("x"))) is True

    def test_x_minus_k_le_x(self):
        """x - 0 <= x is always true."""
        prover = ClaimProver()
        left = _binop(_ident("x"), "-", _int(0))
        assert prover.prove_claim(_binop(left, "<=", _ident("x"))) is True

    def test_k_plus_x_gt_x_commutativity(self):
        """1 + x > x (commutative) is always true."""
        prover = ClaimProver()
        left = _binop(_int(1), "+", _ident("x"))
        assert prover.prove_claim(_binop(left, ">", _ident("x"))) is True

    def test_x_lt_x_plus_k(self):
        """x < x + 1 (reversed form) is always true."""
        prover = ClaimProver()
        right = _binop(_ident("x"), "+", _int(1))
        assert prover.prove_claim(_binop(_ident("x"), "<", right)) is True

    def test_x_plus_zero_neq_x_false(self):
        """x + 0 != x is false (k == 0)."""
        prover = ClaimProver()
        left = _binop(_ident("x"), "+", _int(0))
        # This should not be provable as true (k=0, != requires k!=0)
        assert prover.prove_claim(_binop(left, "!=", _ident("x"))) is None


class TestKnowClaimProving:
    """Integration tests: know claims through the checker."""

    def test_know_provably_true_no_warning(self):
        """know 2 + 2 == 4 should produce no diagnostic."""
        check(
            "transforms id(n Integer) Integer\n"
            "    know: 2 + 2 == 4\n"
            "    from\n"
            "        n\n"
        )

    def test_know_provably_false_error(self):
        """know 2 + 2 == 5 should emit E356."""
        check_fails(
            "transforms id(n Integer) Integer\n"
            "    know: 2 + 2 == 5\n"
            "    from\n"
            "        n\n",
            "E356",
        )

    def test_know_indeterminate_warning(self):
        """know n > 0 (runtime variable) should emit W327."""
        check_warns(
            "transforms id(n Integer) Integer\n"
            "    know: n > 0\n"
            "    from\n"
            "        n\n",
            "W327",
        )

    def test_know_from_requires(self):
        """know n > 0 with requires n > 0 should be provable (no W327)."""
        check(
            "transforms safe(n Integer) Integer\n"
            "    requires n > 0\n"
            "    know: n > 0\n"
            "    from\n"
            "        n\n"
        )

    def test_know_from_requires_implication(self):
        """know n > 0 with requires n >= 1 should be provable."""
        check(
            "transforms safe(n Integer) Integer\n"
            "    requires n >= 1\n"
            "    know: n > 0\n"
            "    from\n"
            "        n\n"
        )

    def test_know_from_assume(self):
        """know n > 0 with assume n > 0 should be provable."""
        check(
            "transforms safe(n Integer) Integer\n"
            "    assume: n > 0\n"
            "    know: n > 0\n"
            "    from\n"
            "        n\n"
        )

    def test_know_from_believe(self):
        """know n >= 0 with believe n >= 0 should be provable."""
        check(
            "transforms safe(n Integer) Integer\n"
            "    ensures result >= 0\n"
            "    believe: n >= 0\n"
            "    know: n >= 0\n"
            "    explain\n"
            "        check result\n"
            "    from\n"
            "        n\n"
        )

    def test_know_chaining(self):
        """First know proven, second uses it as assumption."""
        check(
            "transforms safe(n Integer) Integer\n"
            "    know: 2 + 2 == 4\n"
            "    know: 2 + 2 == 4\n"
            "    from\n"
            "        n\n"
        )

    def test_know_arithmetic_x_plus_1_gt_x(self):
        """know n + 1 > n should be provable via arithmetic reasoning."""
        check(
            "transforms inc(n Integer) Integer\n"
            "    know: n + 1 > n\n"
            "    from\n"
            "        n + 1\n"
        )

    def test_know_requires_ne_zero(self):
        """know b != 0 with requires b != 0 should be provable."""
        check(
            "transforms safe_div(a Integer, b Integer) Integer\n"
            "    requires b != 0\n"
            "    know: b != 0\n"
            "    from\n"
            "        a\n"
        )


class TestCalleeEnsuresPropagation:
    """Phase 4: callee ensures propagation into caller proof context."""

    def test_callee_ensures_propagated_to_know(self):
        """y = f(n) where f ensures result > 0 lets caller know y > 0."""
        check(
            "transforms positive(n Integer) Integer\n"
            "    requires n > 0\n"
            "    ensures result > 0\n"
            "    explain\n"
            "        n is positive so result is positive\n"
            "    from\n"
            "        n\n"
            "\n"
            "transforms caller(n Integer) Integer\n"
            "    requires n > 0\n"
            "    know: y > 0\n"
            "    from\n"
            "        y as Integer = positive(n)\n"
            "        y\n"
        )

    def test_callee_ensures_multiple_clauses(self):
        """Multiple ensures clauses are all propagated."""
        check(
            "transforms bounded(n Integer) Integer\n"
            "    requires n > 0\n"
            "    ensures result > 0\n"
            "    ensures result >= 1\n"
            "    explain\n"
            "        n bounds result\n"
            "    from\n"
            "        n\n"
            "\n"
            "transforms caller(n Integer) Integer\n"
            "    requires n > 0\n"
            "    know: y > 0\n"
            "    know: y >= 1\n"
            "    from\n"
            "        y as Integer = bounded(n)\n"
            "        y\n"
        )

    def test_no_callee_ensures_still_indeterminate(self):
        """Without callee ensures, know still emits W327."""
        check_warns(
            "transforms plain(n Integer) Integer\n"
            "    from\n"
            "        n\n"
            "\n"
            "transforms caller(n Integer) Integer\n"
            "    know: y > 0\n"
            "    from\n"
            "        y as Integer = plain(n)\n"
            "        y\n",
            "W327",
        )

    def test_callee_ensures_with_implication(self):
        """Callee ensures result >= 1 implies caller can know y > 0."""
        check(
            "transforms safe(n Integer) Integer\n"
            "    requires n >= 1\n"
            "    ensures result >= 1\n"
            "    explain\n"
            "        n is at least 1\n"
            "    from\n"
            "        n\n"
            "\n"
            "transforms caller(n Integer) Integer\n"
            "    requires n >= 1\n"
            "    know: y > 0\n"
            "    from\n"
            "        y as Integer = safe(n)\n"
            "        y\n"
        )


class TestMatchArmNarrowing:
    """Phase 5: match arm structural binding facts in proof context."""

    def test_match_arm_bindings_tracked(self):
        """ProofContext records match arm bindings via add_match_arm_binding."""
        ctx = ProofContext()
        ctx.add_match_arm_binding("opt", "Some", ["x"])
        ctx.add_match_arm_binding("res", "Ok", ["v"])
        bindings = ctx.match_bindings
        assert ("opt", "Some", ["x"]) in bindings
        assert ("res", "Ok", ["v"]) in bindings

    def test_match_arm_binding_none_variant(self):
        """None variant arms are also tracked."""
        ctx = ProofContext()
        ctx.add_match_arm_binding("opt", "None", [])
        assert ctx.match_bindings == [("opt", "None", [])]

    def test_prove_ne_none_from_some_arm_and_assumption(self):
        """subj != None provable when Some arm exists + requires subj != None."""
        from prove.ast_nodes import TypeIdentifierExpr
        ctx = ProofContext()
        span = _span()
        # Add requires: opt != None as assumption
        none_expr = TypeIdentifierExpr(name="None", span=span)
        ne_none = BinaryExpr(
            left=_ident("opt"), op="!=", right=none_expr, span=span
        )
        ctx.add(ne_none)
        # Record the Some arm binding
        ctx.add_match_arm_binding("opt", "Some", ["x"])
        prover = ClaimProver(context=ctx)
        # know: opt != None should be provable (assumption + structural arm)
        assert prover.prove_claim(ne_none) is True

    def test_no_match_binding_still_indeterminate(self):
        """Without a match binding, opt != None remains indeterminate."""
        from prove.ast_nodes import TypeIdentifierExpr
        ctx = ProofContext()
        span = _span()
        none_expr = TypeIdentifierExpr(name="None", span=span)
        ne_none = BinaryExpr(
            left=_ident("opt"), op="!=", right=none_expr, span=span
        )
        prover = ClaimProver(context=ctx)
        # No assumption, no binding → indeterminate
        assert prover.prove_claim(ne_none) is None


class TestProseCoherence:
    """Tests for W501-W505 prose coherence checks."""

    def test_w501_verb_not_in_narrative(self) -> None:
        check_coherence_warns(
            'module Calc\n'
            '  narrative: """Reads numbers from input."""\n'
            'transforms add(a Integer, b Integer) Integer\n'
            'from\n'
            '    a + b\n',
            "W501",
        )

    def test_w501_verb_matches_narrative(self) -> None:
        # "validates" is in narrative — no W501
        check_coherence_ok(
            'module Auth\n'
            '  narrative: """Validates user credentials."""\n'
            'validates credential(user String) Boolean\n'
            'from\n'
            '    true\n',
        )

    def test_w501_synonym_in_narrative(self) -> None:
        # "converts" is a synonym for "transforms" — no W501
        check_coherence_ok(
            'module Converter\n'
            '  narrative: """Converts passwords into hashes."""\n'
            'transforms hash_password(password String) String\n'
            'from\n'
            '    password\n',
        )

    def test_w501_singular_verb_in_narrative(self) -> None:
        # "check" (singular) is a synonym for "validates" — no W501
        check_coherence_ok(
            'module Auth\n'
            '  narrative: """Check user credentials."""\n'
            'validates credential(user String) Boolean\n'
            'from\n'
            '    true\n',
        )

    def test_w503_chosen_without_why_not(self) -> None:
        check_coherence_warns(
            'transforms sort(items List<Integer>) List<Integer>\n'
            '    chosen: "merge sort for stability"\n'
            'from\n'
            '    items\n',
            "W503",
        )

    def test_w503_chosen_with_why_not_ok(self) -> None:
        check_coherence_ok(
            'transforms sort(items List<Integer>) List<Integer>\n'
            '    chosen: "merge sort for stability"\n'
            '    why_not: "quick_sort is unstable"\n'
            'from\n'
            '    items\n',
        )

    def test_w505_why_not_vague(self) -> None:
        check_coherence_warns(
            'transforms sort(items List<Integer>) List<Integer>\n'
            '    chosen: "merge sort"\n'
            '    why_not: "it was too slow"\n'
            'from\n'
            '    items\n',
            "W505",
        )

    def test_w502_explain_no_body_overlap(self) -> None:
        check_coherence_warns(
            'transforms compute(numbers List<Integer>) Integer\n'
            '    explain\n'
            '        perform the quick sort algorithm\n'
            'from\n'
            '    numbers\n',
            "W502",
        )

    def test_w502_explain_matches_body(self) -> None:
        # "sum the numbers" overlaps with param name "numbers" — no W502
        check_coherence_ok(
            'transforms compute(numbers List<Integer>) List<Integer>\n'
            '    explain\n'
            '        sum the numbers\n'
            'from\n'
            '    numbers\n',
        )

    def test_w504_chosen_no_body_overlap(self) -> None:
        check_coherence_warns(
            'transforms compute(numbers List<Integer>) Integer\n'
            '    chosen: "recursive approach"\n'
            '    why_not: "compute iteratively"\n'
            'from\n'
            '    numbers\n',
            "W504",
        )

    def test_w504_chosen_matches_body(self) -> None:
        # "numbers" in chosen text overlaps with param — no W504
        check_coherence_ok(
            'transforms compute(numbers List<Integer>) List<Integer>\n'
            '    chosen: "iterate over numbers"\n'
            '    why_not: "compute recursively"\n'
            'from\n'
            '    numbers\n',
        )

    def test_w505_why_not_with_known_name(self) -> None:
        # "sort" is the function name itself — anchor present, no W505
        check_coherence_ok(
            'transforms sort(items List<Integer>) List<Integer>\n'
            '    chosen: "merge sort"\n'
            '    why_not: "quick_sort is unstable for equal elements"\n'
            'from\n'
            '    items\n',
        )


class TestCounterfactualChecks:
    """Tests for W503-W506 counterfactual annotation checks (always active)."""

    def test_w503_always_active(self) -> None:
        """W503 fires without --coherence flag."""
        check_warns(
            'transforms sort(items List<Integer>) List<Integer>\n'
            '    chosen: "merge sort for stability"\n'
            'from\n'
            '    items\n',
            "W503",
        )

    def test_w503_ok_with_why_not(self) -> None:
        """No W503 when why_not is present alongside chosen."""
        check(
            'transforms sort(items List<Integer>) List<Integer>\n'
            '    chosen: "merge sort"\n'
            '    why_not: "items-based quick sort is unstable"\n'
            'from\n'
            '    items\n',
        )

    def test_w504_always_active(self) -> None:
        """W504 fires without --coherence flag."""
        check_warns(
            'transforms compute(numbers List<Integer>) Integer\n'
            '    chosen: "recursive approach"\n'
            '    why_not: "compute iteratively"\n'
            'from\n'
            '    numbers\n',
            "W504",
        )

    def test_w505_always_active(self) -> None:
        """W505 fires without --coherence flag."""
        check_warns(
            'transforms sort(items List<Integer>) List<Integer>\n'
            '    chosen: "merge sort"\n'
            '    why_not: "it was too slow"\n'
            'from\n'
            '    items\n',
            "W505",
        )

    def test_w505_ok_when_anchored(self) -> None:
        """No W505 when why_not references a known name (param or type)."""
        check(
            'transforms sort(items List<Integer>) List<Integer>\n'
            '    chosen: "merge items"\n'
            '    why_not: "items-based bubble sort is unstable"\n'
            'from\n'
            '    items\n',
        )

    def test_w506_why_not_contradicts_body(self) -> None:
        """W506 fires when why_not rejects a function that the body actually calls."""
        check_warns(
            'transforms find(items List<Integer>, key Integer) Integer\n'
            '    why_not: "linear_search is O(n) and too slow"\n'
            '    chosen: "use first element"\n'
            'from\n'
            '    linear_search(items, key)\n',
            "W506",
        )

    def test_w506_no_contradiction_when_different_call(self) -> None:
        """No W506 when why_not mentions a different function than what body uses."""
        # Why_not mentions "items" (a param, not collected as a call), no call contradiction
        check(
            'transforms find(items List<Integer>, key Integer) Integer\n'
            '    why_not: "items-based approach has overhead"\n'
            '    chosen: "use direct indexing"\n'
            'from\n'
            '    items[0]\n',
        )

    def test_w506_not_fired_with_no_body_calls(self) -> None:
        """No W506 when function body has no function calls."""
        check(
            'transforms identity(items List<Integer>) List<Integer>\n'
            '    why_not: "sort the items first"\n'
            '    chosen: "return items unchanged"\n'
            'from\n'
            '    items\n',
        )
