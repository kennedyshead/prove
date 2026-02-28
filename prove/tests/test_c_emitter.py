"""Tests for c_emitter — C source generation from Prove AST."""

from prove.c_emitter import CEmitter
from prove.checker import Checker
from prove.lexer import Lexer
from prove.parser import Parser


def _emit(source: str) -> str:
    """Parse, check, and emit C for a Prove source string."""
    tokens = Lexer(source, "<test>").lex()
    module = Parser(tokens, "<test>").parse()
    checker = Checker()
    symbols = checker.check(module)
    assert not checker.has_errors(), [d.message for d in checker.diagnostics]
    emitter = CEmitter(module, symbols)
    return emitter.emit()


class TestHelloWorld:
    def test_hello_world_emits(self):
        source = (
            "main() Result<Unit, Error>!\n"
            "    from\n"
            '        println("Hello from Prove!")\n'
        )
        c_code = _emit(source)
        assert "int main(" in c_code
        assert "prove_println" in c_code
        assert "Hello from Prove!" in c_code
        assert "return 0;" in c_code

    def test_includes_runtime_headers(self):
        source = (
            "main() Result<Unit, Error>!\n"
            "    from\n"
            '        println("test")\n'
        )
        c_code = _emit(source)
        assert '#include "prove_runtime.h"' in c_code
        assert '#include "prove_string.h"' in c_code


class TestVarDecl:
    def test_integer_var(self):
        source = (
            "transforms compute() Integer\n"
            "    from\n"
            "        x as Integer = 42\n"
            "        x\n"
        )
        c_code = _emit(source)
        assert "int64_t x = 42L;" in c_code

    def test_string_var(self):
        source = (
            "outputs greet()\n"
            "    from\n"
            '        name as String = "world"\n'
            "        println(name)\n"
        )
        c_code = _emit(source)
        assert "Prove_String*" in c_code
        assert 'prove_string_from_cstr("world")' in c_code


class TestBinaryExpr:
    def test_arithmetic(self):
        source = (
            "transforms compute() Integer\n"
            "    from\n"
            "        x as Integer = 1 + 2\n"
            "        x\n"
        )
        c_code = _emit(source)
        assert "(1L + 2L)" in c_code

    def test_string_concat(self):
        source = (
            "outputs greet()\n"
            "    from\n"
            '        s as String = "hello" + " world"\n'
            "        println(s)\n"
        )
        c_code = _emit(source)
        assert "prove_string_concat" in c_code


class TestFunctionDef:
    def test_simple_function(self):
        source = (
            "transforms add(a Integer, b Integer) Integer\n"
            "    from\n"
            "        a + b\n"
            "\n"
            "main()\n"
            "    from\n"
            "        println(to_string(add(1, 2)))\n"
        )
        c_code = _emit(source)
        assert "transforms_add_Integer_Integer" in c_code
        assert "int64_t a" in c_code
        assert "int64_t b" in c_code


class TestStringInterp:
    def test_string_interpolation(self):
        source = (
            "transforms describe(x Integer) String\n"
            "    from\n"
            '        f"value is {x}"\n'
        )
        c_code = _emit(source)
        assert "prove_string_concat" in c_code
        assert "prove_string_from_int" in c_code

    def test_raw_string_emit(self):
        source = (
            "transforms pattern() String\n"
            "    from\n"
            '        r"^[A-Z]+$"\n'
        )
        c_code = _emit(source)
        assert "prove_string_from_cstr" in c_code


class TestRetainRelease:
    def test_string_var_retained(self):
        source = (
            "transforms greet(name String) String\n"
            "    from\n"
            '        msg as String = "hello"\n'
            "        msg\n"
        )
        c_code = _emit(source)
        assert "prove_retain(msg)" in c_code

    def test_pointer_released_before_return(self):
        source = (
            "outputs show()\n"
            "    from\n"
            '        s as String = "test"\n'
            "        println(s)\n"
        )
        c_code = _emit(source)
        assert "prove_release(s)" in c_code


class TestBuiltinDispatch:
    def test_to_string_integer(self):
        source = (
            "transforms show(x Integer) String\n"
            "    from\n"
            "        to_string(x)\n"
        )
        c_code = _emit(source)
        assert "prove_string_from_int" in c_code

    def test_to_string_boolean(self):
        source = (
            "transforms show(x Boolean) String\n"
            "    from\n"
            "        to_string(x)\n"
        )
        c_code = _emit(source)
        assert "prove_string_from_bool" in c_code

    def test_to_string_decimal(self):
        source = (
            "transforms show(x Decimal) String\n"
            "    from\n"
            "        to_string(x)\n"
        )
        c_code = _emit(source)
        assert "prove_string_from_double" in c_code

    def test_len_list(self):
        source = (
            "transforms count() Integer\n"
            "    from\n"
            "        len([1, 2, 3])\n"
        )
        c_code = _emit(source)
        assert "prove_list_len" in c_code

    def test_readln_emits(self):
        source = (
            "inputs get_name() String\n"
            "    from\n"
            "        readln()\n"
        )
        c_code = _emit(source)
        assert "prove_readln" in c_code

    def test_clamp_emits(self):
        source = (
            "transforms safe(x Integer) Integer\n"
            "    from\n"
            "        clamp(x, 0, 100)\n"
        )
        c_code = _emit(source)
        assert "prove_clamp" in c_code


class TestMatchExpression:
    def test_match_algebraic_switch(self):
        source = (
            "type Color is\n"
            "    Red\n"
            "    Green\n"
            "    Blue\n"
            "\n"
            "transforms name(c Color) String\n"
            "    from\n"
            "        match c\n"
            '            Red => "red"\n'
            '            Green => "green"\n'
            '            Blue => "blue"\n'
        )
        c_code = _emit(source)
        assert "switch" in c_code
        assert "Prove_Color_TAG_RED" in c_code
        assert "Prove_Color_TAG_GREEN" in c_code
        assert "Prove_Color_TAG_BLUE" in c_code

    def test_match_with_binding(self):
        source = (
            "type Shape is\n"
            "    Circle(radius Integer)\n"
            "    Square(side Integer)\n"
            "\n"
            "transforms area(s Shape) Integer\n"
            "    from\n"
            "        match s\n"
            "            Circle(r) => r * r\n"
            "            Square(s) => s * s\n"
        )
        c_code = _emit(source)
        assert "switch" in c_code
        assert "Prove_Shape_TAG_CIRCLE" in c_code
        assert "Prove_Shape_TAG_SQUARE" in c_code
        # Bindings should be declared inside case blocks
        assert "int64_t r =" in c_code
        # Match arm bindings should NOT leak to function-level releases
        assert "prove_release(r)" not in c_code
        assert "prove_release(s)" not in c_code

    def test_match_string_binding_no_leak(self):
        source = (
            "type Route is\n"
            "    Get(path String)\n"
            "    Post(path String)\n"
            "\n"
            "transforms handle(route Route) String\n"
            "    from\n"
            "        match route\n"
            '            Get(path) => "GET " + path\n'
            '            Post(path) => "POST " + path\n'
        )
        c_code = _emit(source)
        assert "switch" in c_code
        # path is declared inside case blocks, should not be released at function scope
        assert "prove_release(path)" not in c_code


class TestAlgebraicConstructors:
    def test_unit_variant_constructor(self):
        source = (
            "type Color is\n"
            "    Red\n"
            "    Blue\n"
            "\n"
            "main()\n"
            "    from\n"
            "        x as Color = Red()\n"
            '        println("done")\n'
        )
        c_code = _emit(source)
        assert "static inline Prove_Color Red(void)" in c_code
        assert "static inline Prove_Color Blue(void)" in c_code

    def test_data_variant_constructor(self):
        source = (
            "type Expr is\n"
            "    Num(val Integer)\n"
            "    Add(left Integer, right Integer)\n"
            "\n"
            "main()\n"
            "    from\n"
            "        x as Expr = Num(42)\n"
            '        println("done")\n'
        )
        c_code = _emit(source)
        assert "static inline Prove_Expr Num(int64_t val)" in c_code
        assert "static inline Prove_Expr Add(int64_t left, int64_t right)" in c_code
        assert "_v.tag = Prove_Expr_TAG_NUM;" in c_code


class TestRecordFieldAccess:
    def test_record_field(self):
        source = (
            "type Point is\n"
            "    x Integer\n"
            "    y Integer\n"
            "\n"
            "transforms get_x(p Point) Integer\n"
            "    from\n"
            "        p.x\n"
        )
        c_code = _emit(source)
        assert "p.x" in c_code


class TestListLiteralAndIndex:
    def test_list_literal(self):
        source = (
            "transforms nums() List<Integer>\n"
            "    from\n"
            "        [10, 20, 30]\n"
        )
        c_code = _emit(source)
        assert "prove_list_new" in c_code
        assert "prove_list_push" in c_code
        assert "10L" in c_code

    def test_list_index(self):
        source = (
            "transforms first() Integer\n"
            "    from\n"
            "        xs as List<Integer> = [1, 2, 3]\n"
            "        xs[0]\n"
        )
        c_code = _emit(source)
        assert "prove_list_get" in c_code
        assert "0L" in c_code


class TestPipeExpression:
    def test_pipe_to_function(self):
        source = (
            "transforms double(x Integer) Integer\n"
            "    from\n"
            "        x * 2\n"
            "\n"
            "transforms compute() Integer\n"
            "    from\n"
            "        5 |> double\n"
        )
        c_code = _emit(source)
        assert "transforms_double_Integer(5L)" in c_code

    def test_pipe_to_builtin(self):
        source = (
            "outputs show()\n"
            "    from\n"
            '        "hello" |> println\n'
        )
        c_code = _emit(source)
        assert "prove_println" in c_code


class TestFailPropagation:
    def test_fail_prop_emits_result_check(self):
        source = (
            "inputs risky() Result<Integer, Error>!\n"
            "    from\n"
            "        42\n"
            "\n"
            "inputs caller() Result<Integer, Error>!\n"
            "    from\n"
            "        risky()!\n"
        )
        c_code = _emit(source)
        assert "Prove_Result" in c_code
        assert "prove_result_is_err" in c_code

    def test_fail_prop_unwraps_int(self):
        source = (
            "inputs risky() Result<Integer, Error>!\n"
            "    from\n"
            "        42\n"
            "\n"
            "inputs caller() Result<Integer, Error>!\n"
            "    from\n"
            "        risky()!\n"
        )
        c_code = _emit(source)
        assert "prove_result_unwrap_int" in c_code


class TestAssumeAssertion:
    def test_assume_emits_if_panic(self):
        source = (
            "transforms safe_div(a Integer, b Integer) Integer\n"
            "    assume: b != 0\n"
            "    from\n"
            "        a / b\n"
        )
        c_code = _emit(source)
        assert "prove_panic" in c_code
        assert "assumption violated" in c_code


class TestStringInterpolationEdgeCases:
    def test_interp_with_integer(self):
        source = (
            "transforms msg(n Integer) String\n"
            "    from\n"
            '        f"count: {n}"\n'
        )
        c_code = _emit(source)
        assert "prove_string_from_int(n)" in c_code
        assert "prove_string_concat" in c_code

    def test_interp_with_boolean(self):
        source = (
            "transforms msg(b Boolean) String\n"
            "    from\n"
            '        f"flag: {b}"\n'
        )
        c_code = _emit(source)
        assert "prove_string_from_bool(b)" in c_code

    def test_interp_with_string_var(self):
        source = (
            "transforms msg(name String) String\n"
            "    from\n"
            '        f"hello {name}"\n'
        )
        c_code = _emit(source)
        # String vars should be used directly, not converted
        assert "prove_string_concat" in c_code
        # Should NOT call prove_string_from_int on a string
        assert "prove_string_from_int(name)" not in c_code


class TestHigherOrderFunctions:
    def test_map_integer_list(self):
        source = (
            "transforms doubled() List<Integer>\n"
            "    from\n"
            "        map([1, 2, 3], |x| x * 2)\n"
        )
        c_code = _emit(source)
        assert "prove_list_map" in c_code
        assert "_lambda_" in c_code
        assert '#include "prove_hof.h"' in c_code

    def test_filter_integer_list(self):
        source = (
            "transforms evens() List<Integer>\n"
            "    from\n"
            "        filter([1, 2, 3, 4], |x| x > 2)\n"
        )
        c_code = _emit(source)
        assert "prove_list_filter" in c_code
        assert "_lambda_" in c_code

    def test_reduce_integer_list(self):
        source = (
            "transforms total() Integer\n"
            "    from\n"
            "        reduce([1, 2, 3], 0, |acc, x| acc + x)\n"
        )
        c_code = _emit(source)
        assert "prove_list_reduce" in c_code
        assert "_lambda_" in c_code
