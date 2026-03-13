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
            "  System outputs console\n"
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
            "  System outputs console\n"
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
            "  System outputs console\n"
            "main() Unit\n"
            "    from\n"
            '        console("hello from main")\n'
        )

    def test_inputs_allows_io(self):
        check(
            "module Main\n"
            "  System inputs console\n"
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
            "  System inputs console\n"
            "  System outputs console\n"
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
            "  System inputs console\n"
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
            "  System outputs console\n"
            "outputs write_output(msg String) Unit\n"
            "    from\n"
            "        console(msg)\n"
        )

    def test_transitive_purity_error(self):
        """transforms calling a user-defined outputs function -> E363."""
        check_fails(
            "module Main\n"
            "  System outputs console\n"
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
            "  System inputs console\n"
            "inputs get_data() String\n"
            "    from\n"
            "        console()\n"
            "transforms bad() Integer\n"
            "    from\n"
            "        get_data()\n"
            "        0\n",
            "E363",
        )


class TestAsyncVerbs:
    """Test async verb (detached/attached/listens) enforcement."""

    def test_detached_parses(self):
        check(
            "detached fire(x Integer)\n"
            "    from\n"
            "        y as Integer = x + 1\n"
        )

    def test_attached_requires_return_type(self):
        check_fails(
            "attached no_ret(x Integer)\n"
            "    from\n"
            "        x\n",
            "E370",
        )

    def test_attached_with_return_type_passes(self):
        check(
            "attached get(x Integer) Integer\n"
            "    from\n"
            "        x\n"
        )

    def test_detached_allows_io(self):
        check(
            "module M\n"
            "  System outputs console\n"
            "detached log(msg String)\n"
            "    from\n"
            "        console(msg)\n"
        )

    def test_attached_can_call_blocking_io(self):
        check(
            "module M\n"
            '  narrative: """Test"""\n'
            "  System inputs console\n"
            "attached reader() String\n"
            "    from\n"
            "        console()\n"
        )

    def test_attached_with_io_from_listens_ok(self):
        check(
            "module M\n"
            '  narrative: """Test"""\n'
            "  System inputs console\n"
            "  type Cmd is Go | Exit\n"
            "attached reader() Cmd\n"
            "    from\n"
            "        Go()\n"
            "listens loop(workers List<Attached>)\n"
            "    event_type Cmd\n"
            "    from\n"
            "        Exit  => loop\n"
            "        Go    => _ as Cmd = reader()&\n"
        )

    def test_attached_with_io_outside_async_context_e377(self):
        check_fails(
            "module M\n"
            '  narrative: """Test"""\n'
            "  System inputs console\n"
            "attached reader() String\n"
            "    from\n"
            "        console()\n"
            "detached worker()\n"
            "    from\n"
            "        reader()&\n",
            "E398",
        )

    def test_attached_without_io_from_detached_ok(self):
        check(
            "module M\n"
            '  narrative: """Test"""\n'
            "attached compute(x Integer) Integer\n"
            "    from\n"
            "        x + 1\n"
            "detached worker()\n"
            "    from\n"
            "        _ as Integer = compute(42)&\n"
        )

    def test_attached_with_ampersand_outside_listens_info(self):
        """attached& in a non-listens body gives I377 info."""
        check_info(
            "attached helper(x Integer) Integer\n"
            "    from\n"
            "        x\n"
            "transforms bad(x Integer) Integer\n"
            "    from\n"
            "        helper(x)&\n",
            "I377",
        )

    def test_detached_with_return_type_error(self):
        check_fails(
            "detached fire(x Integer) Integer\n"
            "    from\n"
            "        x\n",
            "E374",
        )

    def test_listens_with_return_type_error(self):
        check_fails(
            "module M\n"
            '  narrative: """Test"""\n'
            "  type Ev is Done | Exit\n"
            "listens loop(workers List<Attached>) Integer\n"
            "    event_type Ev\n"
            "    from\n"
            "        Exit => loop\n"
            "        Done => loop\n",
            "E374",
        )

    def test_ampersand_on_pure_fn_info(self):
        check_info(
            "transforms add_one(x Integer) Integer\n"
            "    from\n"
            "        x + 1\n"
            "attached caller(x Integer) Integer\n"
            "    from\n"
            "        add_one(x)&\n",
            "I375",
        )

    def test_attached_no_async_calls_info(self):
        check_info(
            "attached sync_fn(x Integer) Integer\n"
            "    from\n"
            "        x + 1\n",
            "I376",
        )

    def test_detached_with_ampersand_anywhere_ok(self):
        """detached& in a non-async body produces no error."""
        check(
            "detached fire()\n"
            "    from\n"
            "        _ as Integer = 1\n"
            "transforms caller() Integer\n"
            "    from\n"
            "        fire()&\n"
            "        42\n",
        )

    def test_detached_without_ampersand_info(self):
        """detached call without & anywhere gives I378 info."""
        check_info(
            "detached fire()\n"
            "    from\n"
            "        _ as Integer = 1\n"
            "transforms caller() Integer\n"
            "    from\n"
            "        fire()\n"
            "        42\n",
            "I378",
        )

    def test_attached_without_ampersand_error(self):
        """attached call without & in pure verb gives E372 error."""
        check_fails(
            "attached helper(x Integer) Integer\n"
            "    from\n"
            "        x\n"
            "transforms bad(x Integer) Integer\n"
            "    from\n"
            "        helper(x)\n",
            "E372",
        )

    def test_attached_with_ampersand_in_listens_ok(self):
        """attached& in listens body gives no I377 (standard await pattern)."""
        from tests.helpers import check_all
        diags = check_all(
            "module M\n"
            '  narrative: """Test"""\n'
            "  type Event is Work(n Integer) | Exit\n"
            "attached compute(x Integer) Event\n"
            "    from\n"
            "        Work(x + 1)\n"
            "listens handler(workers List<Attached>)\n"
            "    event_type Event\n"
            "    from\n"
            "        Exit => handler\n"
            "        Work(n) => _ as Integer = compute(n)&\n",
        )
        i377 = [d for d in diags if d.code == "I377"]
        assert not i377, f"Expected no I377 but got: {[d.message for d in i377]}"

    def test_attached_with_ampersand_in_streams_info(self):
        """attached& in streams body gives I377 info (not listens)."""
        check_info(
            "module M\n"
            '  narrative: """Test"""\n'
            "  System outputs console\n"
            "  type Line is Data(n Integer) | Exit\n"
            "attached compute(x Integer) Integer\n"
            "    from\n"
            "        x + 1\n"
            "streams process(line Line)!\n"
            "    from\n"
            "        Exit => line\n"
            "        Data(n) =>\n"
            "            _ as Integer = compute(n)&\n"
            "            console(n)\n",
            "I377",
        )

    def test_event_type_on_non_listens_error(self):
        """event_type annotation on non-listens verb gives E399."""
        check_fails(
            "module M\n"
            '  narrative: """Test"""\n'
            "  type Ev is Done | Exit\n"
            "transforms bad(x Integer) Integer\n"
            "    event_type Ev\n"
            "    from\n"
            "        x\n",
            "E399",
        )

    def test_listens_without_event_type_error(self):
        """listens without event_type gives E400."""
        check_fails(
            "module M\n"
            '  narrative: """Test"""\n'
            "  type Ev is Done | Exit\n"
            "listens loop(workers List<Attached>)\n"
            "    from\n"
            "        Done => loop\n"
            "        Exit => loop\n",
            "E400",
        )

    def test_event_type_must_be_algebraic(self):
        """event_type referencing non-algebraic type gives E401."""
        check_fails(
            "module M\n"
            '  narrative: """Test"""\n'
            "listens loop(workers List<Attached>)\n"
            "    event_type Integer\n"
            "    from\n"
            "        Exit => loop\n",
            "E401",
        )

    def test_listens_first_param_must_be_list_attached(self):
        """listens first param not List<Attached> gives E402."""
        check_fails(
            "module M\n"
            '  narrative: """Test"""\n'
            "  type Ev is Done | Exit\n"
            "listens loop(x Integer)\n"
            "    event_type Ev\n"
            "    from\n"
            "        Done => loop\n"
            "        Exit => loop\n",
            "E402",
        )

    def test_listens_worker_not_attached_error(self):
        """Non-attached function in listens worker list gives E403."""
        check_fails(
            "module M\n"
            '  narrative: """Test"""\n'
            "  type Ev is Done | Exit\n"
            "transforms bad(x Integer) Integer\n"
            "    from\n"
            "        x\n"
            "listens loop(workers List<Attached>)\n"
            "    event_type Ev\n"
            "    from\n"
            "        Done => loop\n"
            "        Exit => loop\n"
            "inputs caller()\n"
            "    from\n"
            "        loop([bad])&\n",
            "E403",
        )

    def test_listens_worker_return_type_mismatch(self):
        """Attached worker with wrong return type gives E404."""
        check_fails(
            "module M\n"
            '  narrative: """Test"""\n'
            "  type Ev is Done | Exit\n"
            "  type Other is Foo | Bar\n"
            "attached bad_worker(x Integer) Other\n"
            "    from\n"
            "        Foo\n"
            "listens loop(workers List<Attached>)\n"
            "    event_type Ev\n"
            "    from\n"
            "        Done => loop\n"
            "        Exit => loop\n"
            "inputs caller()\n"
            "    from\n"
            "        loop([bad_worker(1)])&\n",
            "E404",
        )

    def test_listens_attached_call_in_worker_list_ok(self):
        """Attached calls with args in listens worker list don't trigger E372."""
        check(
            "module M\n"
            '  narrative: """Test"""\n'
            "  type Ev is Done(n Integer) | Exit\n"
            "attached worker(x Integer) Done<Integer>\n"
            "    from\n"
            "        Done(x * 2)\n"
            "listens loop(workers List<Attached>)\n"
            "    event_type Ev\n"
            "    from\n"
            "        Done(n) => Unit\n"
            "        Exit => Unit\n"
            "inputs caller()\n"
            "    from\n"
            "        loop([worker(5)])&\n",
        )
