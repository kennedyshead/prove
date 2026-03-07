"""Tests for verb and purity enforcement in the Prove semantic analyzer."""

from __future__ import annotations

from tests.helpers import check, check_fails, check_info, check_warns


class TestVerbEnforcement:
    """Test verb purity constraints."""

    def test_transforms_is_pure(self):
        check("transforms pure_fn(x Integer) Integer\n    from\n        x + 1\n")

    def test_validates_implicit_boolean(self):
        check("validates is_positive(x Integer)\n    from\n        x > 0\n")

    def test_validates_explicit_return_info(self):
        check_info(
            'validates bad(x Integer) String\n    from\n        "oops"\n',
            "I360",
        )

    def test_pure_failable_error(self):
        check_fails(
            "transforms bad(x Integer) Integer!\n    from\n        x\n",
            "E361",
        )

    def test_pure_calls_io_error(self):
        check_fails(
            "module M\n"
            "  InputOutput outputs console\n"
            "transforms bad() Integer\n"
            "    from\n"
            '        console("side effect")\n'
            "        0\n",
            "E362",
        )

    def test_reads_is_pure(self):
        check("reads get(key String) String\n    from\n        key\n")

    def test_creates_is_pure(self):
        check("creates make() Integer\n    from\n        0\n")

    def test_matches_is_pure(self):
        check(
            "module M\n"
            "  type Shape is\n"
            "    Circle(radius Integer)\n"
            "    | Square(side Integer)\n"
            "matches kind(s Shape) Integer\n"
            "    from\n"
            "        0\n"
        )

    def test_reads_rejects_io(self):
        check_fails(
            "module M\n"
            "  InputOutput outputs console\n"
            "reads bad() Integer\n"
            "    from\n"
            '        console("side effect")\n'
            "        0\n",
            "E362",
        )

    def test_pure_field_mutation_error(self):
        check_fails(
            "module M\n"
            "  type Pair is\n"
            "    x Integer\n"
            "    y Integer\n"
            "transforms bad(p Pair) Pair\n"
            "    from\n"
            "        p.x = 0\n"
            "        p\n",
            "E331",
        )

    def test_io_verb_field_mutation_allowed(self):
        check(
            "module M\n"
            "  type Pair is\n"
            "    x Integer\n"
            "    y Integer\n"
            "outputs mutate(p Pair) Pair\n"
            "    from\n"
            "        p.x = 0\n"
            "        p\n",
        )

    def test_pure_field_mutation_in_match_arm(self):
        check_fails(
            "module M\n"
            "  type Shape is\n"
            "    Circle(radius Integer)\n"
            "    | Square(side Integer)\n"
            "  type Pair is\n"
            "    x Integer\n"
            "    y Integer\n"
            "matches bad(s Shape, p Pair) Pair\n"
            "    from\n"
            "        match s\n"
            "            Circle(r) =>\n"
            "                p.x = r\n"
            "                p\n"
            "            _ => p\n",
            "E331",
        )

    def test_main_allows_io(self):
        check(
            "module Main\n"
            "  InputOutput outputs console\n"
            "main() Unit\n"
            "    from\n"
            '        console("hello from main")\n'
        )

    def test_inputs_allows_io(self):
        check(
            "module Main\n"
            "  InputOutput inputs console\n"
            "inputs read_input() String\n"
            "    from\n"
            "        console()\n"
        )


class TestChannelDispatch:
    """Test same-name functions with different verbs."""

    def test_same_name_different_verbs(self):
        """Two functions with same name but different verbs should coexist."""
        check(
            "module Main\n"
            "  InputOutput inputs console\n"
            "  InputOutput outputs console\n"
            "inputs load() String\n"
            "    from\n"
            "        console()\n"
            "\n"
            "outputs load(data String) Unit\n"
            "    from\n"
            "        console(data)\n"
        )

    def test_verb_context_resolves_correct_overload(self):
        """Calling same-name function should resolve via verb context."""
        check(
            "module Main\n"
            "  InputOutput inputs console\n"
            "inputs fetch() String\n"
            "    from\n"
            "        console()\n"
            "\n"
            "inputs process() String\n"
            "    from\n"
            "        fetch()\n"
        )

    def test_validates_channel(self):
        """validates verb functions should coexist with other verbs."""
        check(
            "transforms format(n Integer) String\n"
            "    from\n"
            "        to_string(n)\n"
            "\n"
            "validates format(n Integer)\n"
            "    from\n"
            "        n > 0\n"
        )

    def test_outputs_allows_io(self):
        check(
            "module Main\n"
            "  InputOutput outputs console\n"
            "outputs write_output(msg String) Unit\n"
            "    from\n"
            "        console(msg)\n"
        )

    def test_transitive_purity_error(self):
        """transforms calling a user-defined outputs function -> E363."""
        check_fails(
            "module Main\n"
            "  InputOutput outputs console\n"
            "outputs log_msg(msg String) Unit\n"
            "    from\n"
            "        console(msg)\n"
            "transforms bad(x Integer) Integer\n"
            "    from\n"
            '        log_msg("side effect")\n'
            "        x\n",
            "E363",
        )

    def test_transitive_purity_inputs_error(self):
        """transforms calling a user-defined inputs function -> E363."""
        check_fails(
            "module Main\n"
            "  InputOutput inputs console\n"
            "inputs get_data() String\n"
            "    from\n"
            "        console()\n"
            "transforms bad() Integer\n"
            "    from\n"
            "        get_data()\n"
            "        0\n",
            "E363",
        )
