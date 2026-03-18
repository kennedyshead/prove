"""Tests for par_map / par_filter / par_reduce / par_each checker support."""

from __future__ import annotations

from tests.helpers import check, check_all, check_fails


class TestParMapChecker:
    """par_map type inference and purity enforcement."""

    def test_par_map_infers_list_return(self):
        """par_map(List<Integer>, fn) -> List<Integer>."""
        check(
            "transforms double(n Integer) Integer\n"
            "    from\n"
            "        n + n\n"
            "\n"
            "transforms caller(xs List<Integer>) Integer\n"
            "    from\n"
            "        result as List<Integer> = par_map(xs, double)\n"
            "        len(result)\n"
        )

    def test_par_map_with_lambda(self):
        """par_map with lambda callback."""
        check(
            "transforms caller(xs List<Integer>) Integer\n"
            "    from\n"
            "        result as List<Integer> = par_map(xs, |n| n + 1)\n"
            "        len(result)\n"
        )

    def test_par_map_rejects_io_callback(self):
        """par_map with IO verb callback emits E368."""
        check_fails(
            "outputs show(n Integer) Unit\n"
            "    from\n"
            "        n\n"
            "\n"
            "transforms caller(xs List<Integer>) Integer\n"
            "    from\n"
            "        par_map(xs, show)\n"
            "        0\n",
            "E368",
        )


class TestParFilterChecker:
    """par_filter type inference and purity enforcement."""

    def test_par_filter_infers_list_return(self):
        """par_filter(List<Integer>, pred) -> List<Integer>."""
        check(
            "validates positive(n Integer) Boolean\n"
            "    from\n"
            "        n > 0\n"
            "\n"
            "transforms caller(xs List<Integer>) Integer\n"
            "    from\n"
            "        result as List<Integer> = par_filter(xs, positive)\n"
            "        len(result)\n"
        )

    def test_par_filter_with_lambda(self):
        """par_filter with lambda predicate."""
        check(
            "transforms caller(xs List<Integer>) Integer\n"
            "    from\n"
            "        result as List<Integer> = par_filter(xs, |n| n > 1)\n"
            "        len(result)\n"
        )

    def test_par_filter_rejects_io_callback(self):
        """par_filter with IO verb callback emits E368."""
        check_fails(
            "inputs check_remote(n Integer) Boolean\n"
            "    from\n"
            "        n > 0\n"
            "\n"
            "transforms caller(xs List<Integer>) Integer\n"
            "    from\n"
            "        par_filter(xs, check_remote)\n"
            "        0\n",
            "E368",
        )


class TestParReduceChecker:
    """par_reduce type inference and purity enforcement."""

    def test_par_reduce_infers_output_type(self):
        """par_reduce(List<Integer>, init, fn) -> Integer."""
        check(
            "transforms add(a Integer, b Integer) Integer\n"
            "    from\n"
            "        a + b\n"
            "\n"
            "transforms caller(xs List<Integer>) Integer\n"
            "    from\n"
            "        par_reduce(xs, 0, add)\n"
        )

    def test_par_reduce_with_lambda(self):
        """par_reduce with lambda callback."""
        check(
            "transforms caller(xs List<Integer>) Integer\n"
            "    from\n"
            "        par_reduce(xs, 0, |a, b| a + b)\n"
        )

    def test_par_reduce_rejects_io_callback(self):
        """par_reduce with IO verb callback emits E368."""
        check_fails(
            "outputs accumulate(a Integer, b Integer) Integer\n"
            "    from\n"
            "        a + b\n"
            "\n"
            "transforms caller(xs List<Integer>) Integer\n"
            "    from\n"
            "        par_reduce(xs, 0, accumulate)\n"
            "        0\n",
            "E368",
        )


class TestParHofPureVerbs:
    """All pure verbs should be accepted as par_* callbacks."""

    def test_transforms_accepted(self):
        """transforms verb accepted in par_map."""
        check(
            "transforms double(n Integer) Integer\n"
            "    from\n"
            "        n + n\n"
            "\n"
            "transforms caller(xs List<Integer>) Integer\n"
            "    from\n"
            "        par_map(xs, double)\n"
            "        0\n"
        )

    def test_validates_accepted(self):
        """validates verb accepted in par_filter."""
        check(
            "validates positive(n Integer) Boolean\n"
            "    from\n"
            "        n > 0\n"
            "\n"
            "transforms caller(xs List<Integer>) Integer\n"
            "    from\n"
            "        par_filter(xs, positive)\n"
            "        0\n"
        )

    def test_reads_accepted(self):
        """reads verb accepted in par_map."""
        check(
            "reads identity(n Integer) Integer\n"
            "    from\n"
            "        n\n"
            "\n"
            "transforms caller(xs List<Integer>) Integer\n"
            "    from\n"
            "        par_map(xs, identity)\n"
            "        0\n"
        )

    def test_creates_accepted(self):
        """creates verb accepted in par_map."""
        check(
            "creates make(n Integer) Integer\n"
            "    from\n"
            "        n\n"
            "\n"
            "transforms caller(xs List<Integer>) Integer\n"
            "    from\n"
            "        par_map(xs, make)\n"
            "        0\n"
        )

    def test_no_errors_in_diagnostics(self):
        """par_map with pure callback produces no E368."""
        diags = check_all(
            "transforms double(n Integer) Integer\n"
            "    from\n"
            "        n + n\n"
            "\n"
            "transforms caller(xs List<Integer>) Integer\n"
            "    from\n"
            "        par_map(xs, double)\n"
            "        0\n"
        )
        e368 = [d for d in diags if d.code == "E368"]
        assert not e368, f"Unexpected E368: {[d.message for d in e368]}"


class TestParEachChecker:
    """par_each type inference and verb enforcement."""

    def test_par_each_accepts_io_callback(self):
        """par_each allows IO verb callbacks (unlike par_map)."""
        check(
            "outputs log_item(n Integer) Integer\n"
            "    from\n"
            "        n\n"
            "\n"
            "outputs caller(xs List<Integer>) Unit\n"
            "    from\n"
            "        par_each(xs, log_item)\n"
        )

    def test_par_each_accepts_pure_callback(self):
        """par_each also accepts pure verb callbacks."""
        check(
            "transforms process(n Integer) Integer\n"
            "    from\n"
            "        n\n"
            "\n"
            "outputs caller(xs List<Integer>) Unit\n"
            "    from\n"
            "        par_each(xs, process)\n"
        )

    def test_par_each_with_lambda(self):
        """par_each with lambda callback passes type check."""
        check("outputs caller(xs List<Integer>) Unit\n    from\n        par_each(xs, |n| n)\n")

    def test_par_each_infers_unit_return(self):
        """par_each returns Unit regardless of callback return type."""
        check(
            "outputs log_item(n Integer) Integer\n"
            "    from\n"
            "        n\n"
            "\n"
            "outputs caller(xs List<Integer>) Unit\n"
            "    from\n"
            "        par_each(xs, log_item)\n"
        )

    def test_par_each_rejects_async_detached_callback(self):
        """par_each with detached verb callback emits E369."""
        check_fails(
            "detached fire_and_forget(n Integer) Integer\n"
            "    from\n"
            "        n\n"
            "\n"
            "outputs caller(xs List<Integer>) Unit\n"
            "    from\n"
            "        par_each(xs, fire_and_forget)\n",
            "E369",
        )

    def test_par_each_no_e368_for_io(self):
        """par_each with IO callback does not produce E368."""
        diags = check_all(
            "outputs log_item(n Integer) Integer\n"
            "    from\n"
            "        n\n"
            "\n"
            "outputs caller(xs List<Integer>) Unit\n"
            "    from\n"
            "        par_each(xs, log_item)\n"
        )
        e368 = [d for d in diags if d.code == "E368"]
        assert not e368, f"Unexpected E368: {[d.message for d in e368]}"
