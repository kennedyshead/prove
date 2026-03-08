"""Tests for contract checking in the Prove semantic analyzer."""

from __future__ import annotations

from tests.helpers import check, check_fails, check_warns


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


# ── Fix: requires valid narrows parameter types ──────────────────────


class TestRequiresValidNarrowing:
    """Test that requires valid narrows Result/Option params in function body."""

    def test_result_param_narrowed(self):
        """requires valid object(json_data) should narrow Result<Value,Error> param to Value."""
        # We test this indirectly: if narrowing works, the body type-checks
        check(
            "module M\n"
            "  type Payload is\n"
            "    data String\n"
            "\n"
            "validates object(v Payload) Boolean\n"
            "    from\n"
            "        true\n"
            "\n"
            "transforms extract(data Result<Payload, String>) String\n"
            "    requires valid object(data)\n"
            "    from\n"
            "        data.data\n"
        )
