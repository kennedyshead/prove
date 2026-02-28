"""Tests for the testing module — property test generation."""

from pathlib import Path

from prove.testing import TestGenerator, run_tests
from tests.helpers import parse_check as _parse_check


class TestTestGenerator:
    def test_generates_from_ensures(self):
        source = (
            "transforms add(a Integer, b Integer) Integer\n"
            "    ensures result == a + b\n"
            "    proof\n"
            '        correctness: "result is sum of a and b"\n'
            "    from\n"
            "        a + b\n"
        )
        module, symbols = _parse_check(source)
        gen = TestGenerator(module, symbols, property_rounds=10)
        suite = gen.generate()
        assert len(suite.cases) > 0
        # Should have property test + boundary test
        names = [tc.name for tc in suite.cases]
        assert any("prop" in n for n in names)
        assert any("boundary" in n for n in names)

    def test_generates_from_believe(self):
        source = (
            "transforms abs_val(n Integer) Integer\n"
            "    ensures result >= 0\n"
            "    believe: result >= 0\n"
            "    proof\n"
            '        non_negative: "result is abs so >= 0"\n'
            "    from\n"
            "        match n >= 0\n"
            "            true => n\n"
            "            false => 0 - n\n"
        )
        module, symbols = _parse_check(source)
        gen = TestGenerator(module, symbols, property_rounds=10)
        suite = gen.generate()
        names = [tc.name for tc in suite.cases]
        assert any("believe" in n for n in names)

    def test_no_tests_for_void_functions(self):
        source = (
            "outputs greet()\n"
            "    from\n"
            '        println("hi")\n'
        )
        module, symbols = _parse_check(source)
        gen = TestGenerator(module, symbols)
        suite = gen.generate()
        assert len(suite.cases) == 0

    def test_strip_main(self):
        c_code = (
            "void foo(void) {}\n"
            "int main(int argc, char **argv) {\n"
            "    foo();\n"
            "    return 0;\n"
            "}\n"
        )
        result = TestGenerator._strip_main(c_code)
        assert "int main(" not in result
        assert "void foo" in result

    def test_emits_valid_c(self):
        source = (
            "transforms add(a Integer, b Integer) Integer\n"
            "    ensures result == a + b\n"
            "    proof\n"
            '        correctness: "result is sum of a and b"\n'
            "    from\n"
            "        a + b\n"
        )
        module, symbols = _parse_check(source)
        gen = TestGenerator(module, symbols, property_rounds=10)
        suite = gen.generate()
        c_code = gen.emit_test_c(suite)
        assert "int main(" in c_code
        assert "_tests_run" in c_code
        assert "_tests_passed" in c_code


class TestRunTests:
    def test_run_math_example(self, needs_cc):
        examples_dir = Path(__file__).resolve().parent.parent / "examples" / "math"
        source = (examples_dir / "src" / "main.prv").read_text()
        module, symbols = _parse_check(source)
        result = run_tests(
            examples_dir, [(module, symbols)], property_rounds=50,
        )
        assert result.ok, f"Tests failed: {result.output} {result.c_error}"
        assert result.tests_run > 0
        assert result.tests_passed > 0
        assert result.tests_failed == 0
