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
            "module Main\n"
            "  System outputs console\n"
            "main() Result<Unit, Error>!\n"
            "    from\n"
            '        console("Hello from Prove!")\n'
        )
        c_code = _emit(source)
        assert "int main(" in c_code
        assert "prove_println" in c_code
        assert "Hello from Prove!" in c_code
        assert "return 0;" in c_code

    def test_includes_runtime_headers(self):
        source = (
            "module Main\n"
            "  System outputs console\n"
            "main() Result<Unit, Error>!\n"
            "    from\n"
            '        console("test")\n'
        )
        c_code = _emit(source)
        assert '#include "prove_runtime.h"' in c_code
        assert '#include "prove_string.h"' in c_code


class TestVarDecl:
    def test_integer_var(self):
        source = "transforms compute() Integer\n    from\n        x as Integer = 42\n        x\n"
        c_code = _emit(source)
        assert "int64_t x = 42L;" in c_code

    def test_string_var(self):
        source = (
            "module Main\n"
            "  System outputs console\n"
            "outputs greet()\n"
            "    from\n"
            '        name as String = "world"\n'
            "        console(name)\n"
        )
        c_code = _emit(source)
        assert "Prove_String*" in c_code
        assert 'prove_string_from_cstr("world")' in c_code


class TestBinaryExpr:
    def test_arithmetic(self):
        source = "transforms compute() Integer\n    from\n        x as Integer = 1 + 2\n        x\n"
        c_code = _emit(source)
        assert "(1L + 2L)" in c_code

    def test_string_concat(self):
        source = (
            "module Main\n"
            "  System outputs console\n"
            "outputs greet()\n"
            "    from\n"
            '        s as String = "hello" + " world"\n'
            "        console(s)\n"
        )
        c_code = _emit(source)
        assert "prove_string_concat" in c_code


class TestFunctionDef:
    def test_simple_function(self):
        source = (
            "module Main\n"
            "  System outputs console\n"
            "transforms add(a Integer, b Integer) Integer\n"
            "    from\n"
            "        a + b\n"
            "\n"
            "main()\n"
            "    from\n"
            "        console(to_string(add(1, 2)))\n"
        )
        c_code = _emit(source)
        assert "prv_transforms_add_Integer_Integer" in c_code
        assert "int64_t a" in c_code
        assert "int64_t b" in c_code


class TestStringInterp:
    def test_string_interpolation(self):
        source = 'transforms describe(x Integer) String\n    from\n        f"value is {x}"\n'
        c_code = _emit(source)
        assert "prove_string_concat" in c_code
        assert "prove_string_from_int" in c_code

    def test_raw_string_emit(self):
        source = 'transforms pattern() String\n    from\n        r"^[A-Z]+$"\n'
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
            "module Main\n"
            "  System outputs console\n"
            "outputs show()\n"
            "    from\n"
            '        s as String = "test"\n'
            "        console(s)\n"
        )
        c_code = _emit(source)
        assert "prove_release(s)" in c_code


class TestBuiltinDispatch:
    def test_to_string_integer(self):
        source = "transforms show(x Integer) String\n    from\n        to_string(x)\n"
        c_code = _emit(source)
        assert "prove_string_from_int" in c_code

    def test_to_string_boolean(self):
        source = "transforms show(x Boolean) String\n    from\n        to_string(x)\n"
        c_code = _emit(source)
        assert "prove_string_from_bool" in c_code

    def test_to_string_decimal(self):
        source = "transforms show(x Decimal) String\n    from\n        to_string(x)\n"
        c_code = _emit(source)
        assert "prove_string_from_double" in c_code

    def test_len_list(self):
        source = "transforms count() Integer\n    from\n        len([1, 2, 3])\n"
        c_code = _emit(source)
        assert "prove_list_len" in c_code

    def test_readln_emits(self):
        source = (
            "module Main\n"
            "  System inputs console\n"
            "inputs get_name() String\n"
            "    from\n"
            "        console()\n"
        )
        c_code = _emit(source)
        assert "prove_readln" in c_code

    def test_clamp_emits(self):
        source = "transforms safe(x Integer) Integer\n    from\n        clamp(x, 0, 100)\n"
        c_code = _emit(source)
        assert "prove_clamp" in c_code


class TestMatchExpression:
    def test_match_algebraic_switch(self):
        source = (
            "module Test\n"
            "    type Color is\n"
            "        Red\n"
            "        Green\n"
            "        Blue\n"
            "\n"
            "matches name(c Color) String\n"
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
            "module Test\n"
            "    type Shape is\n"
            "        Circle(radius Integer)\n"
            "        Square(side Integer)\n"
            "\n"
            "matches area(s Shape) Integer\n"
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
            "module Test\n"
            "    type Route is\n"
            "        Get(path String)\n"
            "        Post(path String)\n"
            "\n"
            "matches handle(route Route) String\n"
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
            "module Test\n"
            "    type Color is\n"
            "        Red\n"
            "        Blue\n"
            "\n"
            "main()\n"
            "    from\n"
            "        x as Color = Red()\n"
            "        to_string(0)\n"
        )
        c_code = _emit(source)
        assert "static inline Prove_Color Red(void)" in c_code
        assert "static inline Prove_Color Blue(void)" in c_code

    def test_data_variant_constructor(self):
        source = (
            "module Test\n"
            "    type Expr is\n"
            "        Num(val Integer)\n"
            "        Add(left Integer, right Integer)\n"
            "\n"
            "main()\n"
            "    from\n"
            "        x as Expr = Num(42)\n"
            "        to_string(0)\n"
        )
        c_code = _emit(source)
        assert "static inline Prove_Expr Num(int64_t val)" in c_code
        assert "static inline Prove_Expr Add(int64_t left, int64_t right)" in c_code
        assert "_v.tag = Prove_Expr_TAG_NUM;" in c_code


class TestRecordFieldAccess:
    def test_record_field(self):
        source = (
            "module Test\n"
            "    type Point is\n"
            "        x Integer\n"
            "        y Integer\n"
            "\n"
            "transforms get_x(p Point) Integer\n"
            "    from\n"
            "        p.x\n"
        )
        c_code = _emit(source)
        assert "p.x" in c_code


class TestListLiteralAndIndex:
    def test_list_literal(self):
        source = "transforms nums() List<Integer>\n    from\n        [10, 20, 30]\n"
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
        assert "prv_transforms_double_Integer(5L)" in c_code

    def test_pipe_to_builtin(self):
        source = (
            "module Main\n"
            "  System outputs console\n"
            "outputs show()\n"
            "    from\n"
            '        "hello" |> console\n'
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
        source = 'transforms msg(n Integer) String\n    from\n        f"count: {n}"\n'
        c_code = _emit(source)
        assert "prove_string_from_int(n)" in c_code
        assert "prove_string_concat" in c_code

    def test_interp_with_boolean(self):
        source = 'transforms msg(b Boolean) String\n    from\n        f"flag: {b}"\n'
        c_code = _emit(source)
        assert "prove_string_from_bool(b)" in c_code

    def test_interp_with_string_var(self):
        source = 'transforms msg(name String) String\n    from\n        f"hello {name}"\n'
        c_code = _emit(source)
        # String vars should be used directly, not converted
        assert "prove_string_concat" in c_code
        # Should NOT call prove_string_from_int on a string
        assert "prove_string_from_int(name)" not in c_code


class TestHigherOrderFunctions:
    def test_map_integer_list(self):
        source = "transforms doubled() List<Integer>\n    from\n        map([1, 2, 3], |x| x * 2)\n"
        c_code = _emit(source)
        assert "prove_list_map" in c_code
        assert "_lambda_" in c_code
        assert '#include "prove_hof.h"' in c_code

    def test_filter_integer_list(self):
        source = (
            "transforms evens() List<Integer>\n    from\n        filter([1, 2, 3, 4], |x| x > 2)\n"
        )
        c_code = _emit(source)
        assert "prove_list_filter" in c_code
        assert "_lambda_" in c_code

    def test_reduce_integer_list(self):
        source = (
            "transforms total() Integer\n    from\n        reduce([1, 2, 3], 0, |acc, x| acc + x)\n"
        )
        c_code = _emit(source)
        # Lambda reduce is inlined as a for-loop with direct array access
        assert "for (int64_t" in c_code
        assert "->data[" in c_code
        assert "acc" in c_code


class TestExplainBranching:
    def test_two_branch_explain(self):
        source = (
            "transforms abs(n Integer) Integer\n"
            "    ensures result >= 0\n"
            "    explain\n"
            "        positive: identity when n >= 0\n"
            "        negative: deducted when n < 0\n"
            "    from\n"
            "        n\n"
            "        0 - n\n"
        )
        c_code = _emit(source)
        assert "if ((" in c_code
        assert "n >= 0L" in c_code
        assert "return n;" in c_code
        assert "else if ((" in c_code
        assert "n < 0L" in c_code
        assert "return (0L - n);" in c_code

    def test_no_condition_fallback(self):
        """Explain block without when conditions falls through to regular body."""
        source = (
            "transforms identity(x Integer) Integer\n"
            "    ensures result == x\n"
            "    explain\n"
            "        trivial: x is returned unchanged\n"
            "    from\n"
            "        x\n"
        )
        c_code = _emit(source)
        # Should NOT have if/else branches — just regular body emission
        assert "else if" not in c_code
        assert "= x;" in c_code  # regular return through temp


class TestRequiresOptionNarrowing:
    """Test that requires-based option narrowing emits .value unwrap."""

    def test_narrowed_call_emits_value_unwrap(self):
        """Table.get with requires Table.has should emit .value cast."""
        source = (
            "module Main\n"
            "  Table types Table Value, creates new, validates has,"
            " reads get, transforms add\n"
            "\n"
            "reads lookup(key String, table Table<String>) String\n"
            "    requires Table.has(key, table)\n"
            "    from\n"
            "        Table.get(key, table)\n"
        )
        c_code = _emit(source)
        assert ".value" in c_code

    def test_unqualified_narrowed_call_emits_value_unwrap(self):
        """Unqualified get with requires has should emit .value cast."""
        source = (
            "module Main\n"
            "  Table types Table Value, creates new, validates has,"
            " reads get, transforms add\n"
            "\n"
            "reads lookup(key String, table Table<String>) String\n"
            "    requires has(key, table)\n"
            "    from\n"
            "        get(key, table)\n"
        )
        c_code = _emit(source)
        assert ".value" in c_code

    def test_non_narrowed_call_no_value_unwrap(self):
        """Table.get without requires should NOT emit .value."""
        source = (
            "module Main\n"
            "  Table types Table Value, creates new, validates has, reads get\n"
            "\n"
            "reads lookup(key String, table Table<String>) Option<String>\n"
            "    from\n"
            "        Table.get(key, table)\n"
        )
        c_code = _emit(source)
        # Should use the Option type, not .value
        assert ".value" not in c_code

    def test_narrowed_var_decl_type(self):
        """Narrowed call in var decl should use inner type, not Option."""
        source = (
            "module Main\n"
            "  Table types Table Value, creates new, validates has,"
            " reads get, transforms add\n"
            "  System outputs console\n"
            "\n"
            "outputs show(key String, table Table<String>)\n"
            "    requires Table.has(key, table)\n"
            "    from\n"
            "        val as String = Table.get(key, table)\n"
            "        console(val)\n"
        )
        c_code = _emit(source)
        # The var should be Prove_String*, not Prove_Option_*
        assert "Prove_String* val" in c_code
        assert ".value" in c_code


class TestRequiresValidRuntimeGuard:
    """Test that requires valid X(...) supports option narrowing and call-site guards."""

    def test_requires_valid_option_narrowing(self):
        """requires valid ok(id) should trigger .value unwrap on Option param."""
        source = (
            "module Main\n"
            "  Types validates integer\n"
            "\n"
            "validates ok(id Option<Integer>)\n"
            "    requires valid integer(id)\n"
            "    from\n"
            "        id > 0\n"
        )
        c_code = _emit(source)
        assert ".value" in c_code

    def test_requires_valid_result_param_narrowing(self):
        """requires valid toml(data) should narrow Result<String,Error> to String for overload."""
        source = (
            "module Main\n"
            "  Parse creates toml, validates toml\n"
            "\n"
            "transforms config(data Result<String, Error>) Table<Value>\n"
            "    requires valid toml(data)\n"
            "    from\n"
            "        toml(data)\n"
        )
        c_code = _emit(source)
        # Should resolve to creates toml (prove_parse_toml) not reads toml (prove_emit_toml)
        assert "prove_parse_toml" in c_code
        assert "prove_emit_toml" not in c_code

    def test_requires_valid_result_return_unwrap(self):
        """requires valid toml(data) should unwrap Result return to inner type."""
        source = (
            "module Main\n"
            "  Parse creates toml, validates toml\n"
            "\n"
            "transforms config(data Result<String, Error>) Table<Value>\n"
            "    requires valid toml(data)\n"
            "    from\n"
            "        toml(data)\n"
        )
        c_code = _emit(source)
        # Result should be unwrapped via prove_result_unwrap_*
        assert "prove_result_unwrap_ptr" in c_code


class TestModuleConstants:
    """Test that module constants emit #define macros."""

    def test_string_constant(self):
        source = (
            "module Test\n"
            '  MY_FILE as String = "data.json"\n'
            "\n"
            "transforms get_path() String\n"
            "    from\n"
            "        MY_FILE\n"
        )
        c_code = _emit(source)
        assert '#define MY_FILE prove_string_from_cstr("data.json")' in c_code

    def test_integer_constant(self):
        source = (
            "module Test\n"
            "  MAX_SIZE as Integer = 100\n"
            "\n"
            "transforms limit() Integer\n"
            "    from\n"
            "        MAX_SIZE\n"
        )
        c_code = _emit(source)
        assert "#define MAX_SIZE 100L" in c_code

    def test_boolean_constant(self):
        source = (
            "module Test\n"
            "  DEBUG as Boolean = true\n"
            "\n"
            "transforms flag() Boolean\n"
            "    from\n"
            "        DEBUG\n"
        )
        c_code = _emit(source)
        assert "#define DEBUG true" in c_code


class TestFailableNonResultReturn:
    """Test failable functions with non-Result return types."""

    def test_failable_returns_prove_result(self):
        """A failable function with concrete return should use Prove_Result."""
        source = (
            "module Main\n"
            "  System inputs console\n"
            "\n"
            "inputs greeting() String!\n"
            "    from\n"
            "        console()\n"
        )
        c_code = _emit(source)
        assert "Prove_Result prv_inputs_greeting" in c_code

    def test_failable_unit_return(self):
        """A failable function with unit return should use Prove_Result."""
        source = (
            "module Main\n"
            "  System outputs console\n"
            "\n"
            "outputs greet()!\n"
            "    from\n"
            '        console("hi")\n'
        )
        c_code = _emit(source)
        assert "Prove_Result prv_outputs_greet" in c_code
        assert "return prove_result_ok();" in c_code


class TestTableFieldAccess:
    """Test field access on Table<Value> types."""

    def test_table_field_emits_prove_table_get(self):
        source = (
            "module Main\n"
            "  Table types Table Value, creates new, validates has,"
            " reads get, transforms add\n"
            "  Parse reads object, validates object\n"
            "\n"
            "transforms extract(data Table<Integer>) Integer\n"
            "    from\n"
            "        data.count\n"
        )
        c_code = _emit(source)
        assert "prove_table_get" in c_code
        assert '"count"' in c_code


class TestOptionUnwrap:
    """Test Option unwrapping in binary ops and field assignments."""

    def test_option_unwrap_in_comparison(self):
        """Option<Integer> compared to Integer should unwrap."""
        source = (
            "module Main\n"
            "  Table types Table Value, creates new, validates has,"
            " reads get, transforms add\n"
            "  Types validates integer\n"
            "\n"
            "validates check(id Option<Integer>)\n"
            "    requires valid integer(id)\n"
            "    from\n"
            "        id > 0\n"
        )
        c_code = _emit(source)
        assert ".value" in c_code


class TestRegionCleanup:
    """Test that prove_region_exit is emitted before return statements."""

    def test_pure_function_region_elided(self):
        source = (
            "transforms double(x Integer) Integer\n"
            "    from\n"
            "        x * 2\n"
        )
        c_code = _emit(source)
        # Pure numeric function should not emit region enter/exit
        fn_start = c_code.index("prv_transforms_double")
        fn_end = c_code.index("}", fn_start)
        fn_code = c_code[fn_start:fn_end]
        assert "prove_region_enter" not in fn_code
        assert "prove_region_exit" not in fn_code

    def test_allocating_function_region_exit_before_return(self):
        source = (
            'transforms greet(name String) String\n'
            '    from\n'
            '        "hello " + name\n'
        )
        c_code = _emit(source)
        fn_start = c_code.index("prv_transforms_greet")
        fn_code = c_code[fn_start:]
        # Function with string literal should have region enter/exit
        assert "prove_region_enter" in fn_code
        exit_idx = fn_code.index("prove_region_exit")
        return_idx = fn_code.index("return", exit_idx)
        assert exit_idx < return_idx

    def test_failable_error_prop_region_exit(self):
        """Error propagation should exit region before returning error when region is active."""
        source = (
            'inputs risky() String!\n'
            '    from\n'
            '        "hello"\n'
            '\n'
            'inputs caller() String!\n'
            '    from\n'
            '        x as String = risky()!\n'
            '        "got: " + x\n'
        )
        c_code = _emit(source)
        # Find the caller function
        fn_start = c_code.index("prv_inputs_caller")
        fn_code = c_code[fn_start:]
        # Should have region_exit inside error check block (string literals trigger region)
        assert "prove_region_exit" in fn_code
        err_check = fn_code.index("prove_result_is_err")
        exit_after_err = fn_code.index("prove_region_exit", err_check)
        return_after_err = fn_code.index("return", exit_after_err)
        assert exit_after_err < return_after_err


class TestVariantPatternNonAlgebraic:
    """Test VariantPattern in non-algebraic match (e.g. match on String)."""

    def test_variant_pattern_some_on_string(self):
        """matches verb with String param and Some/wildcard patterns."""
        source = (
            "matches check(raw String) Integer\n    from\n        Some(r) => 1\n        _ => 0\n"
        )
        c_code = _emit(source)
        # Should emit Some check as pointer null check (String is pointer)
        assert "!= NULL" in c_code or ".tag == 1" in c_code


class TestRefinementTypeValidation:
    """Test numeric refinement type constraint emission."""

    def test_range_constraint(self):
        """Range constraint like Integer where 1..65535."""
        source = (
            "module M\n"
            "  type Port is Integer where 1..65535\n"
            "transforms use_port(p Integer) Integer\n"
            "    from\n"
            "        port as Port = p\n"
            "        port\n"
        )
        c_code = _emit(source)
        assert "prove_panic" in c_code
        assert "port < 1" in c_code or "port > 65535" in c_code

    def test_not_equal_constraint(self):
        """Comparison constraint like Integer where != 0."""
        source = (
            "module M\n"
            "  type NonZero is Integer where != 0\n"
            "transforms use_nz(n Integer) Integer\n"
            "    from\n"
            "        nz as NonZero = n\n"
            "        nz\n"
        )
        c_code = _emit(source)
        assert "prove_panic" in c_code
        assert "!=" in c_code

    def test_greater_equal_constraint(self):
        """Comparison constraint like Integer where >= 0."""
        source = (
            "module M\n"
            "  type Natural is Integer where >= 0\n"
            "transforms use_nat(n Integer) Integer\n"
            "    from\n"
            "        nat as Natural = n\n"
            "        nat\n"
        )
        c_code = _emit(source)
        assert "prove_panic" in c_code
        assert ">=" in c_code
