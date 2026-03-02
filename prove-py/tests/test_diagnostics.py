"""Comprehensive tests for all Warning and Info diagnostics.

Each diagnostic is tested for:
1. It fires when it should (positive case)
2. It does NOT fire when the code is correct (negative case)
3. The diagnostic has a helpful note or suggestion
"""

from __future__ import annotations

from tests.helpers import check_all, check_info, check_warns


# ── Helpers ─────────────────────────────────────────────────────────


def _codes(diagnostics: list) -> set[str]:
    """Extract diagnostic codes from a list of diagnostics."""
    return {d.code for d in diagnostics}


def _has_notes(diagnostics: list) -> bool:
    """Check that at least one diagnostic has notes."""
    return any(d.notes for d in diagnostics)


# ── W304: match condition guaranteed by requires ────────────────────


class TestW304:
    """W304 fires when a match tests a condition identical to requires."""

    def test_fires_when_match_equals_requires(self):
        source = (
            "transforms f(n Integer) Integer\n"
            "  requires n >= 0\n"
            "from\n"
            "    match n >= 0\n"
            "        true => n\n"
            "        false => 0 - n\n"
        )
        diags = check_warns(source, "W304")
        assert len(diags) == 1

    def test_not_fired_when_condition_differs(self):
        source = (
            "transforms f(n Integer) Integer\n"
            "  requires n >= 0\n"
            "from\n"
            "    match n > 10\n"
            "        true => n\n"
            "        false => 0\n"
        )
        diags = check_all(source)
        assert "W304" not in _codes(diags)

    def test_not_fired_without_requires(self):
        source = (
            "transforms f(n Integer) Integer\n"
            "from\n"
            "    match n >= 0\n"
            "        true => n\n"
            "        false => 0 - n\n"
        )
        diags = check_all(source)
        assert "W304" not in _codes(diags)

    def test_has_note(self):
        source = (
            "transforms f(n Integer) Integer\n"
            "  requires n >= 0\n"
            "from\n"
            "    match n >= 0\n"
            "        true => n\n"
            "        false => 0 - n\n"
        )
        diags = check_warns(source, "W304")
        assert _has_notes(diags), "W304 should have a note explaining the fix"

    def test_matches_complex_expression(self):
        source = (
            "transforms f(a Integer, b Integer) Integer\n"
            "  requires a + b > 0\n"
            "from\n"
            "    match a + b > 0\n"
            "        true => a + b\n"
            "        false => 0\n"
        )
        diags = check_warns(source, "W304")
        assert len(diags) == 1


# ── W311: intent without contracts ──────────────────────────────────


class TestW311:
    """W311 fires when a function has intent but no ensures/requires."""

    def test_fires_with_intent_no_contracts(self):
        source = (
            "transforms f(n Integer) Integer\n"
            '  intent: "double n"\n'
            "from\n"
            "    n * 2\n"
        )
        diags = check_warns(source, "W311")
        assert len(diags) == 1

    def test_not_fired_with_ensures(self):
        source = (
            "transforms f(n Integer) Integer\n"
            '  intent: "double n"\n'
            "  ensures result == n * 2\n"
            "from\n"
            "    n * 2\n"
        )
        diags = check_all(source)
        assert "W311" not in _codes(diags)

    def test_not_fired_with_requires(self):
        source = (
            "transforms f(n Integer) Integer\n"
            '  intent: "double n"\n'
            "  requires n >= 0\n"
            "from\n"
            "    n * 2\n"
        )
        diags = check_all(source)
        assert "W311" not in _codes(diags)

    def test_not_fired_without_intent(self):
        source = (
            "transforms f(n Integer) Integer\n"
            "from\n"
            "    n * 2\n"
        )
        diags = check_all(source)
        assert "W311" not in _codes(diags)

    def test_has_note(self):
        source = (
            "transforms f(n Integer) Integer\n"
            '  intent: "double n"\n'
            "from\n"
            "    n * 2\n"
        )
        diags = check_warns(source, "W311")
        assert _has_notes(diags), "W311 should have a note explaining the fix"


# ── W321: explain text missing concept references ───────────────────


class TestW321:
    """W321 fires when explain text doesn't reference function concepts."""

    def test_fires_with_no_concept_reference(self):
        source = (
            "transforms f(n Integer) Integer\n"
            "  ensures result == n\n"
            "  requires n == n\n"
            "  explain\n"
            "      step_one: hello world\n"
            "from\n"
            "    n\n"
        )
        diags = check_warns(source, "W321")
        assert len(diags) == 1

    def test_not_fired_when_param_referenced(self):
        source = (
            "transforms f(n Integer) Integer\n"
            "  ensures result == n\n"
            "  requires n == n\n"
            "  explain\n"
            "      step_one: return n directly\n"
            "from\n"
            "    n\n"
        )
        diags = check_all(source)
        assert "W321" not in _codes(diags)

    def test_not_fired_when_result_referenced(self):
        source = (
            "transforms f(n Integer) Integer\n"
            "  ensures result == n\n"
            "  requires n == n\n"
            "  explain\n"
            "      step_one: set result to input\n"
            "from\n"
            "    n\n"
        )
        diags = check_all(source)
        assert "W321" not in _codes(diags)

    def test_has_note(self):
        source = (
            "transforms f(n Integer) Integer\n"
            "  ensures result == n\n"
            "  requires n == n\n"
            "  explain\n"
            "      step_one: hello world\n"
            "from\n"
            "    n\n"
        )
        diags = check_warns(source, "W321")
        assert _has_notes(diags), "W321 should have a note explaining the fix"


# ── W322: duplicate near-miss inputs ────────────────────────────────


class TestW322:
    """W322 fires when two near_miss declarations have identical inputs."""

    def test_fires_with_duplicate_inputs(self):
        source = (
            "transforms f(n Integer) Integer\n"
            "  ensures result >= 0\n"
            "  requires n >= 0\n"
            "  near_miss: 0 => 0\n"
            "  near_miss: 0 => 1\n"
            "  explain\n"
            "      return n\n"
            "from\n"
            "    n\n"
        )
        diags = check_warns(source, "W322")
        assert len(diags) == 1

    def test_not_fired_with_different_inputs(self):
        source = (
            "transforms f(n Integer) Integer\n"
            "  ensures result >= 0\n"
            "  requires n >= 0\n"
            "  near_miss: 0 => 0\n"
            "  near_miss: 1 => 1\n"
            "  explain\n"
            "      return n\n"
            "from\n"
            "    n\n"
        )
        diags = check_all(source)
        assert "W322" not in _codes(diags)

    def test_has_note(self):
        source = (
            "transforms f(n Integer) Integer\n"
            "  ensures result >= 0\n"
            "  requires n >= 0\n"
            "  near_miss: 0 => 0\n"
            "  near_miss: 0 => 1\n"
            "  explain\n"
            "      return n\n"
            "from\n"
            "    n\n"
        )
        diags = check_warns(source, "W322")
        assert _has_notes(diags), "W322 should have a note explaining the fix"


# ── W323: ensures without explain ───────────────────────────────────


class TestW323:
    """W323 fires when a function has ensures but no explain block."""

    def test_fires_with_ensures_no_explain(self):
        source = (
            "transforms f(n Integer) Integer\n"
            "  ensures result >= 0\n"
            "from\n"
            "    n\n"
        )
        diags = check_warns(source, "W323")
        assert len(diags) >= 1

    def test_not_fired_with_explain(self):
        source = (
            "transforms f(n Integer) Integer\n"
            "  ensures result >= 0\n"
            "  requires n >= 0\n"
            "  explain\n"
            "      return n\n"
            "from\n"
            "    n\n"
        )
        diags = check_all(source)
        assert "W323" not in _codes(diags)

    def test_not_fired_with_trusted(self):
        source = (
            "transforms f(n Integer) Integer\n"
            "  ensures result >= 0\n"
            "  trusted\n"
            "from\n"
            "    n\n"
        )
        diags = check_all(source)
        assert "W323" not in _codes(diags)

    def test_has_note(self):
        source = (
            "transforms f(n Integer) Integer\n"
            "  ensures result >= 0\n"
            "from\n"
            "    n\n"
        )
        diags = check_warns(source, "W323")
        assert _has_notes(diags), "W323 should have a note explaining the fix"


# ── W324: ensures without requires ──────────────────────────────────


class TestW324:
    """W324 fires when a function has ensures but no requires."""

    def test_fires_with_ensures_no_requires(self):
        source = (
            "transforms f(n Integer) Integer\n"
            "  ensures result >= 0\n"
            "from\n"
            "    n\n"
        )
        diags = check_warns(source, "W324")
        assert len(diags) >= 1

    def test_not_fired_with_requires(self):
        source = (
            "transforms f(n Integer) Integer\n"
            "  ensures result >= 0\n"
            "  requires n >= 0\n"
            "  explain\n"
            "      return n\n"
            "from\n"
            "    n\n"
        )
        diags = check_all(source)
        assert "W324" not in _codes(diags)

    def test_has_note(self):
        source = (
            "transforms f(n Integer) Integer\n"
            "  ensures result >= 0\n"
            "from\n"
            "    n\n"
        )
        diags = check_warns(source, "W324")
        assert _has_notes(diags), "W324 should have a note explaining the fix"


# ── W325: explain without ensures ───────────────────────────────────


class TestW325:
    """W325 fires when a function has explain but no ensures."""

    def test_fires_with_explain_no_ensures(self):
        source = (
            "transforms f(n Integer) Integer\n"
            "  explain\n"
            "      just return n\n"
            "from\n"
            "    n\n"
        )
        diags = check_warns(source, "W325")
        assert len(diags) >= 1

    def test_not_fired_with_ensures(self):
        source = (
            "transforms f(n Integer) Integer\n"
            "  ensures result == n\n"
            "  requires n == n\n"
            "  explain\n"
            "      return n directly\n"
            "from\n"
            "    n\n"
        )
        diags = check_all(source)
        assert "W325" not in _codes(diags)

    def test_not_fired_with_trusted(self):
        source = (
            "transforms f(n Integer) Integer\n"
            "  explain\n"
            "      just return n\n"
            "  trusted\n"
            "from\n"
            "    n\n"
        )
        diags = check_all(source)
        assert "W325" not in _codes(diags)

    def test_has_note(self):
        source = (
            "transforms f(n Integer) Integer\n"
            "  explain\n"
            "      just return n\n"
            "from\n"
            "    n\n"
        )
        diags = check_warns(source, "W325")
        assert _has_notes(diags), "W325 should have a note explaining the fix"


# ── W326: recursion depth may be unbounded ──────────────────────────


class TestW326:
    """W326 fires when recursive function may have unbounded call depth."""

    def test_fires_for_simple_recursion(self):
        source = (
            "transforms f(n Integer) Integer\n"
            "  terminates: n\n"
            "from\n"
            "    match n\n"
            "        0 => 0\n"
            "        _ => f(n - 1)\n"
        )
        diags = check_warns(source, "W326")
        assert len(diags) == 1

    def test_not_fired_with_believe(self):
        source = (
            "transforms f(n Integer) Integer\n"
            "  ensures result >= 0\n"
            "  terminates: n\n"
            "  believe: result >= 0\n"
            "from\n"
            "    match n\n"
            "        0 => 0\n"
            "        _ => f(n - 1)\n"
        )
        diags = check_all(source)
        assert "W326" not in _codes(diags)

    def test_not_fired_without_recursion(self):
        source = (
            "transforms f(n Integer) Integer\n"
            "from\n"
            "    n * 2\n"
        )
        diags = check_all(source)
        assert "W326" not in _codes(diags)


# ── I301: unreachable match arm ─────────────────────────────────────


class TestI301:
    """I301 fires when a match arm appears after a wildcard."""

    def test_fires_after_wildcard(self):
        source = (
            "module M\n"
            "  type Color is Red | Green\n"
            "transforms f(c Color) String\n"
            "from\n"
            "    match c\n"
            '        _ => "any"\n'
            '        Red => "red"\n'
        )
        diags = check_info(source, "I301")
        assert len(diags) == 1

    def test_not_fired_without_wildcard_first(self):
        source = (
            "module M\n"
            "  type Color is Red | Green\n"
            "transforms f(c Color) String\n"
            "from\n"
            "    match c\n"
            '        Red => "red"\n'
            '        _ => "other"\n'
        )
        diags = check_all(source)
        assert "I301" not in _codes(diags)


# ── I302: unused import ─────────────────────────────────────────────


class TestI302:
    """I302 fires when an imported name is never used."""

    def test_fires_for_unused_import(self):
        source = (
            "module Main\n"
            "  Text transforms trim\n"
            "transforms f(s String) String\n"
            "from\n"
            "    s\n"
        )
        diags = check_info(source, "I302")
        assert len(diags) == 1

    def test_fires_for_each_unused_import_on_same_line(self):
        source = (
            "module Main\n"
            "  Text transforms trim upper replace\n"
            "transforms f(s String) String\n"
            "from\n"
            "    s\n"
        )
        diags = check_info(source, "I302")
        assert len(diags) == 3, f"Expected 3 I302 but got {len(diags)}"

    def test_fires_for_partial_unused(self):
        source = (
            "module Main\n"
            "  Text transforms trim upper\n"
            "transforms f(s String) String\n"
            "from\n"
            "    Text.upper(s)\n"
        )
        diags = check_info(source, "I302")
        assert len(diags) == 1
        assert "trim" in diags[0].message

    def test_not_fired_when_all_used(self):
        source = (
            "module Main\n"
            "  Text transforms upper\n"
            "transforms f(s String) String\n"
            "from\n"
            "    Text.upper(s)\n"
        )
        diags = check_all(source)
        assert "I302" not in _codes(diags)


# ── I303: unused type definition ────────────────────────────────────


class TestI303:
    """I303 fires when a user-defined type is never referenced."""

    def test_fires_for_unused_type(self):
        source = (
            "module M\n"
            "  type Unused is\n"
            "    x Integer\n"
            "transforms f() Integer\n"
            "from\n"
            "    1\n"
        )
        diags = check_info(source, "I303")
        assert len(diags) == 1

    def test_not_fired_when_type_used(self):
        source = (
            "module M\n"
            "  type Point is\n"
            "    x Integer\n"
            "    y Integer\n"
            "transforms origin() Point\n"
            "from\n"
            "    Point(0, 0)\n"
        )
        diags = check_all(source)
        assert "I303" not in _codes(diags)


# ── I310: implicitly typed variable ─────────────────────────────────


class TestI310:
    """I310 fires when a variable is declared without an explicit type."""

    def test_fires_for_implicit_type(self):
        source = (
            "transforms f(n Integer) Integer\n"
            "from\n"
            "    result = n * 2\n"
            "    result\n"
        )
        diags = check_info(source, "I310")
        assert len(diags) == 1

    def test_has_suggestion(self):
        source = (
            "transforms f(n Integer) Integer\n"
            "from\n"
            "    result = n * 2\n"
            "    result\n"
        )
        diags = check_info(source, "I310")
        assert diags[0].suggestions, "I310 should have a suggestion"

    def test_not_fired_with_explicit_type(self):
        source = (
            "transforms f(n Integer) Integer\n"
            "from\n"
            "    result as Integer = n * 2\n"
            "    result\n"
        )
        diags = check_all(source)
        assert "I310" not in _codes(diags)


# ── I314: unknown module in import ──────────────────────────────────


class TestI314:
    """I314 fires when an import references an unknown module."""

    def test_fires_for_unknown_module(self):
        source = (
            "module Main\n"
            "  FakeModule transforms fake\n"
            "transforms f() Integer\n"
            "from\n"
            "    1\n"
        )
        diags = check_info(source, "I314")
        assert len(diags) == 1

    def test_not_fired_for_known_module(self):
        source = (
            "module Main\n"
            "  Text transforms upper\n"
            "transforms f(s String) String\n"
            "from\n"
            "    Text.upper(s)\n"
        )
        diags = check_all(source)
        assert "I314" not in _codes(diags)


# ── I360: validates with explicit Boolean return ────────────────────


class TestI360:
    """I360 fires when validates has an explicit Boolean return type."""

    def test_fires_with_explicit_boolean(self):
        source = (
            "validates f(x Integer) Boolean\n"
            "from\n"
            "    x > 0\n"
        )
        diags = check_info(source, "I360")
        assert len(diags) == 1

    def test_has_suggestion(self):
        source = (
            "validates f(x Integer) Boolean\n"
            "from\n"
            "    x > 0\n"
        )
        diags = check_info(source, "I360")
        assert diags[0].suggestions, "I360 should have a suggestion"

    def test_not_fired_without_return_type(self):
        source = (
            "validates f(x Integer)\n"
            "from\n"
            "    x > 0\n"
        )
        diags = check_all(source)
        assert "I360" not in _codes(diags)

    def test_not_fired_for_transforms(self):
        source = (
            "transforms f(x Integer) Boolean\n"
            "from\n"
            "    x > 0\n"
        )
        diags = check_all(source)
        assert "I360" not in _codes(diags)
