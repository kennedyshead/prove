"""Tests for match expressions and pattern matching in the Prove semantic analyzer."""

from __future__ import annotations

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


class TestGenericPatternMatching:
    """Test E372/E373: invalid variants and exhaustiveness on Result/Option."""

    def test_result_ok_err_valid(self):
        """Ok/Err patterns on Result pass."""
        check(
            "matches handle(r Result<String, Error>) String\n"
            "    from\n"
            "        match r\n"
            "            Ok(value) => value\n"
            '            Err(e) => "error"\n'
        )

    def test_result_wrong_variant(self):
        """Some(x) on Result gives E372."""
        check_fails(
            "matches handle(r Result<String, Error>) String\n"
            "    from\n"
            "        match r\n"
            '            Some(value) => value\n'
            '            _ => "error"\n',
            "E372",
        )

    def test_option_wrong_variant(self):
        """Ok(x) on Option gives E372."""
        check_fails(
            "matches handle(o Option<String>) String\n"
            "    from\n"
            "        match o\n"
            '            Ok(value) => value\n'
            '            _ => "error"\n',
            "E372",
        )

    def test_result_non_exhaustive(self):
        """Ok(x) only, no wildcard gives E373."""
        check_fails(
            "matches handle(r Result<String, Error>) String\n"
            "    from\n"
            "        match r\n"
            '            Ok(value) => value\n',
            "E373",
        )

    def test_option_non_exhaustive(self):
        """Some(x) only, no wildcard gives E373."""
        check_fails(
            "matches handle(o Option<String>) String\n"
            "    from\n"
            "        match o\n"
            '            Some(value) => value\n',
            "E373",
        )

    def test_result_wildcard_covers(self):
        """Ok(x) + _ passes (wildcard covers Err)."""
        check(
            "matches handle(r Result<String, Error>) String\n"
            "    from\n"
            "        match r\n"
            "            Ok(value) => value\n"
            '            _ => "error"\n'
        )

    def test_option_exhaustive(self):
        """Some(x) + None passes."""
        check(
            "matches handle(o Option<String>) String\n"
            "    from\n"
            "        match o\n"
            "            Some(value) => value\n"
            '            None => "nothing"\n'
        )


class TestMatchRestriction:
    """Test I367: match expression suggestion for non-matches verbs."""

    def test_match_in_transforms_info(self):
        """I367: match in transforms body produces info (4+ arms)."""
        check_info(
            "module M\n"
            "  type Dir is North | South | East | West\n"
            "transforms bad(d Dir) String\n"
            "    from\n"
            "        match d\n"
            "            North => \"n\"\n"
            "            South => \"s\"\n"
            "            East => \"e\"\n"
            "            West => \"w\"\n",
            "I367",
        )

    def test_match_in_matches_ok(self):
        """match in matches body is allowed (no I367)."""
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

    def test_match_in_validates_info(self):
        """I367: match in validates body produces info (4+ arms)."""
        check_info(
            "module M\n"
            "  type Dir is North | South | East | West\n"
            "validates bad(d Dir)\n"
            "    from\n"
            "        match d\n"
            "            North => true\n"
            "            South => true\n"
            "            East => false\n"
            "            West => false\n",
            "I367",
        )

    def test_match_in_reads_info(self):
        """I367: match in reads body produces info (4+ arms)."""
        check_info(
            "module M\n"
            "  type Dir is North | South | East | West\n"
            "reads bad(d Dir) Integer\n"
            "    from\n"
            "        match d\n"
            "            North => 1\n"
            "            South => 2\n"
            "            East => 3\n"
            "            West => 4\n",
            "I367",
        )

    def test_match_in_creates_info(self):
        """I367: match in creates body produces info (4+ arms)."""
        check_info(
            "module M\n"
            "  type Dir is North | South | East | West\n"
            "creates bad(d Dir) Integer\n"
            "    from\n"
            "        match d\n"
            "            North => 1\n"
            "            South => 2\n"
            "            East => 3\n"
            "            West => 4\n",
            "I367",
        )

    def test_match_in_inputs_info(self):
        """I367: match in inputs body produces info (4+ arms)."""
        check_info(
            "module M\n"
            "  type Dir is North | South | East | West\n"
            "inputs bad(d Dir) Integer\n"
            "    from\n"
            "        match d\n"
            "            North => 1\n"
            "            South => 2\n"
            "            East => 3\n"
            "            West => 4\n",
            "I367",
        )

    def test_match_in_outputs_info(self):
        """I367: match in outputs body produces info (4+ arms)."""
        check_info(
            "module M\n"
            "  type Dir is North | South | East | West\n"
            "outputs bad(d Dir) Integer\n"
            "    from\n"
            "        match d\n"
            "            North => 1\n"
            "            South => 2\n"
            "            East => 3\n"
            "            West => 4\n",
            "I367",
        )

    def test_match_in_main_ok(self):
        """match in main is exempt from I367."""
        check(
            "module M\n"
            "  type Color is Red | Green\n"
            "main() Unit\n"
            "    from\n"
            "        match true\n"
            "            true => 0\n"
            "            false => 1\n"
        )


class TestMatchArmTypeMismatch:
    """Test E400 — match arm returns Unit while others return value."""

    def test_e400_unit_arm_with_value_arms(self):
        check_fails(
            "module M\n"
            "  Log detached info\n"
            "  type Choice is A | B\n"
            "matches pick(c Choice) String\n"
            "    from\n"
            "        match c\n"
            '            A => "hello"\n'
            '            B =>\n'
            '                info("log")&\n',
            "E400",
        )

    def test_e400_all_unit_arms_ok(self):
        """All arms returning Unit is fine — no E400."""
        check(
            "module M\n"
            "  Log detached info\n"
            "  type Choice is A | B\n"
            "matches pick(c Choice) Unit\n"
            "    from\n"
            "        match c\n"
            '            A => info("a")&\n'
            '            B => info("b")&\n'
        )

    def test_e400_all_value_arms_ok(self):
        """All arms returning same value type — no E400."""
        check(
            "module M\n"
            "  type Choice is A | B\n"
            "matches pick(c Choice) String\n"
            "    from\n"
            "        match c\n"
            '            A => "hello"\n'
            '            B => "world"\n'
        )
