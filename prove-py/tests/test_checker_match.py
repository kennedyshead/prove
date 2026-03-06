"""Tests for match expressions and pattern matching in the Prove semantic analyzer."""

from __future__ import annotations

from prove.source import Span
from prove.symbols import FunctionSignature, SymbolTable
from prove.types import (
    FLOAT,
    INTEGER,
    STRING,
    AlgebraicType,
    FunctionType,
    GenericInstance,
    PrimitiveType,
    RecordType,
    RefinementType,
    VariantInfo,
    is_json_serializable,
    types_compatible,
)
from tests.helpers import check, check_fails, check_info, check_warns


class TestMatchExhaustiveness:
    """Test match exhaustiveness checking."""

    def test_exhaustive_match(self):
        check(
            "module M\n"
            "  type Color is Red | Green | Blue\n"
            "matches name(c Color) String\n"
            "    from\n"
            "        match c\n"
            "            Red => \"red\"\n"
            "            Green => \"green\"\n"
            "            Blue => \"blue\"\n"
        )

    def test_non_exhaustive_match(self):
        check_fails(
            "module M\n"
            "  type Color is Red | Green | Blue\n"
            "matches name(c Color) String\n"
            "    from\n"
            "        match c\n"
            "            Red => \"red\"\n"
            "            Green => \"green\"\n",
            "E371",
        )

    def test_wildcard_covers_all(self):
        check(
            "module M\n"
            "  type Color is Red | Green | Blue\n"
            "matches name(c Color) String\n"
            "    from\n"
            "        match c\n"
            "            Red => \"red\"\n"
            "            _ => \"other\"\n"
        )

    def test_unknown_variant_error(self):
        check_fails(
            "module M\n"
            "  type Color is Red | Green\n"
            "matches bad(c Color) String\n"
            "    from\n"
            "        match c\n"
            "            Red => \"red\"\n"
            "            Green => \"green\"\n"
            "            Purple => \"purple\"\n",
            "E370",
        )

    def test_unreachable_after_wildcard(self):
        check_info(
            "module M\n"
            "  type Color is Red | Green\n"
            "matches name(c Color) String\n"
            "    from\n"
            "        match c\n"
            "            _ => \"any\"\n"
            "            Red => \"red\"\n",
            "I301",
        )


class TestRequiresRedundantMatch:
    """Test W304: match condition guaranteed by requires."""

    def test_match_on_requires_condition(self):
        check_warns(
            "module M\n"
            "  narrative: \"t\"\n"
            "matches abs_val(n Integer) Integer\n"
            "  requires n >= 0\n"
            "from\n"
            "    match n >= 0\n"
            "        true => n\n"
            "        false => 0 - n\n",
            "W304",
        )

    def test_match_on_different_condition_no_warning(self):
        check(
            "matches f(n Integer) Integer\n"
            "  requires n >= 0\n"
            "from\n"
            "    match n > 5\n"
            "        true => n\n"
            "        false => 0\n"
        )

    def test_match_without_requires_no_warning(self):
        check(
            "matches f(n Integer) Integer\n"
            "from\n"
            "    match n >= 0\n"
            "        true => n\n"
            "        false => 0 - n\n"
        )


class TestMatchesVerbRelaxation:
    """Test E365 relaxation: matches accepts String and Integer."""

    def test_matches_string_first_param(self):
        """matches verb accepts String as first parameter."""
        check(
            "matches greet(name String) String\n"
            "    from\n"
            "        match name == \"world\"\n"
            "            true => \"Hello, world!\"\n"
            "            false => \"Hello!\"\n"
        )

    def test_matches_integer_first_param(self):
        """matches verb accepts Integer as first parameter."""
        check(
            "matches classify(n Integer) String\n"
            "    from\n"
            "        match n > 0\n"
            "            true => \"positive\"\n"
            "            false => \"non-positive\"\n"
        )

    def test_matches_algebraic_first_param(self):
        """matches verb still accepts algebraic as first parameter."""
        check(
            "module M\n"
            "  type Shape is\n"
            "    Circle(radius Integer)\n"
            "    | Square(side Integer)\n"
            "matches area(s Shape) Integer\n"
            "    from\n"
            "        match s\n"
            "            Circle(r) => r\n"
            "            Square(s) => s\n"
        )

    def test_matches_boolean_first_param_rejected(self):
        """matches verb rejects Boolean as first parameter."""
        check_fails(
            "matches bad(flag Boolean) String\n"
            "    from\n"
            "        \"nope\"\n",
            "E365",
        )

    def test_matches_decimal_first_param_rejected(self):
        """matches verb rejects Decimal as first parameter."""
        check_fails(
            "matches bad(x Decimal) String\n"
            "    from\n"
            "        \"nope\"\n",
            "E365",
        )

    def test_matches_no_params_rejected(self):
        """matches verb still requires at least one parameter."""
        check_fails(
            "matches bad() String\n"
            "    from\n"
            "        \"nope\"\n",
            "E365",
        )


class TestMatchRestriction:
    """Test E367: match expression only allowed in matches verb."""

    def test_match_in_transforms_error(self):
        """E367: match in transforms body."""
        check_fails(
            "transforms bad(n Integer) String\n"
            "    from\n"
            "        match n > 0\n"
            "            true => \"yes\"\n"
            "            false => \"no\"\n",
            "E367",
        )

    def test_match_in_matches_ok(self):
        """match in matches body is allowed."""
        check(
            "module M\n"
            "  type Color is Red | Green | Blue\n"
            "matches name(c Color) String\n"
            "    from\n"
            "        match c\n"
            "            Red => \"red\"\n"
            "            Green => \"green\"\n"
            "            Blue => \"blue\"\n"
        )

    def test_match_in_validates_error(self):
        """E367: match in validates body."""
        check_fails(
            "validates bad(n Integer)\n"
            "    from\n"
            "        match n > 0\n"
            "            true => true\n"
            "            false => false\n",
            "E367",
        )

    def test_match_in_reads_error(self):
        """E367: match in reads body."""
        check_fails(
            "reads bad(n Integer) Integer\n"
            "    from\n"
            "        match n > 0\n"
            "            true => n\n"
            "            false => 0\n",
            "E367",
        )

    def test_match_in_creates_error(self):
        """E367: match in creates body."""
        check_fails(
            "creates bad(n Integer) Integer\n"
            "    from\n"
            "        match n > 0\n"
            "            true => n\n"
            "            false => 0\n",
            "E367",
        )

    def test_match_in_inputs_error(self):
        """E367: match in inputs body."""
        check_fails(
            "inputs bad(n Integer) Integer\n"
            "    from\n"
            "        match n > 0\n"
            "            true => n\n"
            "            false => 0\n",
            "E367",
        )

    def test_match_in_outputs_error(self):
        """E367: match in outputs body."""
        check_fails(
            "outputs bad(n Integer) Integer\n"
            "    from\n"
            "        match n > 0\n"
            "            true => n\n"
            "            false => 0\n",
            "E367",
        )

    def test_match_in_main_ok(self):
        """match in main is exempt from E367."""
        check(
            "module M\n"
            "  type Color is Red | Green\n"
            "main() Unit\n"
            "    from\n"
            "        match true\n"
            "            true => 0\n"
            "            false => 1\n"
        )
