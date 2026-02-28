"""Tests for the Prove semantic analyzer."""

from __future__ import annotations

from prove.types import (
    INTEGER,
    STRING,
    AlgebraicType,
    RecordType,
    RefinementType,
)
from tests.helpers import check, check_fails, check_warns


class TestTypeResolution:
    """Test that types resolve correctly."""

    def test_builtin_types_resolve(self):
        st = check(
            "transforms identity(x Integer) Integer\n"
            "    from\n"
            "        x\n"
        )
        ty = st.resolve_type("Integer")
        assert ty == INTEGER

    def test_string_type_resolves(self):
        st = check(
            "transforms greet(name String) String\n"
            "    from\n"
            "        name\n"
        )
        ty = st.resolve_type("String")
        assert ty == STRING

    def test_user_record_type_resolves(self):
        st = check(
            "type Point is\n"
            "    x Integer\n"
            "    y Integer\n"
            "transforms origin() Point\n"
            "    from\n"
            "        Point(0, 0)\n"
        )
        ty = st.resolve_type("Point")
        assert isinstance(ty, RecordType)
        assert ty.name == "Point"
        assert "x" in ty.fields
        assert "y" in ty.fields

    def test_undefined_type_error(self):
        check_fails(
            "transforms bad(x Nonexistent) Integer\n"
            "    from\n"
            "        0\n",
            "E300",
        )

    def test_generic_type_resolves(self):
        check(
            "transforms wrap(x Integer) List<Integer>\n"
            "    from\n"
            "        [x]\n"
        )

    def test_modified_type_resolves(self):
        check(
            "transforms small(x Integer:[16 Unsigned]) Integer\n"
            "    from\n"
            "        x\n"
        )

    def test_duplicate_type_error(self):
        check_fails(
            "type Foo is\n"
            "    x Integer\n"
            "type Foo is\n"
            "    y String\n",
            "E301",
        )

    def test_algebraic_type_resolves(self):
        st = check(
            "type Shape is\n"
            "    Circle(radius Integer)\n"
            "    | Square(side Integer)\n"
            "transforms area(s Shape) Integer\n"
            "    from\n"
            "        0\n"
        )
        ty = st.resolve_type("Shape")
        assert isinstance(ty, AlgebraicType)
        assert len(ty.variants) == 2

    def test_refinement_type_resolves(self):
        st = check(
            "type Positive is Integer where >= 0\n"
            "transforms use_pos(x Positive) Integer\n"
            "    from\n"
            "        0\n"
        )
        ty = st.resolve_type("Positive")
        assert isinstance(ty, RefinementType)


class TestNameResolution:
    """Test name lookups in scope."""

    def test_params_in_scope(self):
        check(
            "transforms add(a Integer, b Integer) Integer\n"
            "    from\n"
            "        a\n"
        )

    def test_local_var_in_scope(self):
        check(
            "transforms compute(x Integer) Integer\n"
            "    from\n"
            "        result as Integer = x\n"
            "        result\n"
        )

    def test_undefined_name_error(self):
        check_fails(
            "transforms bad() Integer\n"
            "    from\n"
            "        unknown_var\n",
            "E310",
        )

    def test_forward_reference_function(self):
        """Functions registered in pass 1 can be called from other functions."""
        check(
            "transforms caller() Integer\n"
            "    from\n"
            "        callee(42)\n"
            "transforms callee(x Integer) Integer\n"
            "    from\n"
            "        x\n"
        )

    def test_duplicate_variable_error(self):
        check_fails(
            "transforms bad() Integer\n"
            "    from\n"
            "        x as Integer = 1\n"
            "        x as Integer = 2\n"
            "        x\n",
            "E302",
        )

    def test_constant_registered(self):
        """Constants are registered in the symbol table."""
        st = check(
            "MAX_SIZE as Integer = 100\n"
        )
        sym = st.lookup("MAX_SIZE")
        assert sym is not None
        assert sym.resolved_type == INTEGER


class TestTypeChecking:
    """Test type inference and checking."""

    def test_integer_literal(self):
        check(
            "transforms num() Integer\n"
            "    from\n"
            "        42\n"
        )

    def test_decimal_literal(self):
        check(
            "transforms dec() Decimal\n"
            "    from\n"
            "        3.14\n"
        )

    def test_string_literal(self):
        check(
            "transforms greeting() String\n"
            "    from\n"
            "        \"hello\"\n"
        )

    def test_boolean_literal(self):
        check(
            "transforms flag() Boolean\n"
            "    from\n"
            "        true\n"
        )

    def test_binary_arithmetic(self):
        check(
            "transforms add(a Integer, b Integer) Integer\n"
            "    from\n"
            "        a + b\n"
        )

    def test_binary_comparison(self):
        check(
            "transforms bigger(a Integer, b Integer) Boolean\n"
            "    from\n"
            "        a > b\n"
        )

    def test_binary_logical(self):
        check(
            "transforms both(a Boolean, b Boolean) Boolean\n"
            "    from\n"
            "        a && b\n"
        )

    def test_type_mismatch_binary(self):
        check_fails(
            "transforms bad(a Integer, b String) Integer\n"
            "    from\n"
            "        a + b\n",
            "E320",
        )

    def test_type_mismatch_var_decl(self):
        check_fails(
            "transforms bad() Integer\n"
            "    from\n"
            "        x as String = 42\n"
            "        0\n",
            "E321",
        )

    def test_var_decl_inference(self):
        check(
            "transforms compute() Integer\n"
            "    from\n"
            "        x as Integer = 42\n"
            "        x\n"
        )

    def test_return_type_mismatch(self):
        check_fails(
            "transforms bad() String\n"
            "    from\n"
            "        42\n",
            "E322",
        )


class TestCallChecking:
    """Test function call checking."""

    def test_valid_call(self):
        check(
            "transforms double(x Integer) Integer\n"
            "    from\n"
            "        x + x\n"
            "transforms use_double() Integer\n"
            "    from\n"
            "        double(5)\n"
        )

    def test_wrong_arg_count(self):
        check_fails(
            "transforms one_arg(x Integer) Integer\n"
            "    from\n"
            "        x\n"
            "transforms bad() Integer\n"
            "    from\n"
            "        one_arg(1, 2)\n",
            "E330",
        )

    def test_arg_type_mismatch(self):
        check_fails(
            "transforms needs_int(x Integer) Integer\n"
            "    from\n"
            "        x\n"
            "transforms bad() Integer\n"
            "    from\n"
            "        needs_int(\"hello\")\n",
            "E331",
        )

    def test_undefined_function_error(self):
        check_fails(
            "transforms bad() Integer\n"
            "    from\n"
            "        nonexistent_func(42)\n",
            "E311",
        )

    def test_pipe_call(self):
        check(
            "transforms double(x Integer) Integer\n"
            "    from\n"
            "        x + x\n"
            "transforms piped() Integer\n"
            "    from\n"
            "        5 |> double\n"
        )

    def test_builtin_println(self):
        check(
            "main() Unit\n"
            "    from\n"
            "        println(\"hello\")\n"
        )

    def test_builtin_len(self):
        check(
            "transforms count() Integer\n"
            "    from\n"
            "        len([1, 2, 3])\n"
        )


class TestFieldAccess:
    """Test field access on records."""

    def test_valid_field(self):
        check(
            "type Point is\n"
            "    x Integer\n"
            "    y Integer\n"
            "transforms get_x(p Point) Integer\n"
            "    from\n"
            "        p.x\n"
        )

    def test_invalid_field(self):
        check_fails(
            "type Point is\n"
            "    x Integer\n"
            "    y Integer\n"
            "transforms bad(p Point) Integer\n"
            "    from\n"
            "        p.z\n",
            "E340",
        )


class TestVerbEnforcement:
    """Test verb purity constraints."""

    def test_transforms_is_pure(self):
        check(
            "transforms pure_fn(x Integer) Integer\n"
            "    from\n"
            "        x + 1\n"
        )

    def test_validates_implicit_boolean(self):
        check(
            "validates is_positive(x Integer)\n"
            "    from\n"
            "        x > 0\n"
        )

    def test_validates_explicit_return_error(self):
        check_fails(
            "validates bad(x Integer) String\n"
            "    from\n"
            "        \"oops\"\n",
            "E360",
        )

    def test_pure_failable_error(self):
        check_fails(
            "transforms bad(x Integer) Integer!\n"
            "    from\n"
            "        x\n",
            "E361",
        )

    def test_pure_calls_io_error(self):
        check_fails(
            "transforms bad() Integer\n"
            "    from\n"
            "        println(\"side effect\")\n"
            "        0\n",
            "E362",
        )

    def test_main_allows_io(self):
        check(
            "main() Unit\n"
            "    from\n"
            "        println(\"hello from main\")\n"
        )

    def test_inputs_allows_io(self):
        check(
            "inputs read_input() String\n"
            "    from\n"
            "        readln()\n"
        )

    def test_outputs_allows_io(self):
        check(
            "outputs write_output(msg String) Unit\n"
            "    from\n"
            "        println(msg)\n"
        )


class TestMatchExhaustiveness:
    """Test match exhaustiveness checking."""

    def test_exhaustive_match(self):
        check(
            "type Color is Red | Green | Blue\n"
            "transforms name(c Color) String\n"
            "    from\n"
            "        match c\n"
            "            Red => \"red\"\n"
            "            Green => \"green\"\n"
            "            Blue => \"blue\"\n"
        )

    def test_non_exhaustive_match(self):
        check_fails(
            "type Color is Red | Green | Blue\n"
            "transforms name(c Color) String\n"
            "    from\n"
            "        match c\n"
            "            Red => \"red\"\n"
            "            Green => \"green\"\n",
            "E371",
        )

    def test_wildcard_covers_all(self):
        check(
            "type Color is Red | Green | Blue\n"
            "transforms name(c Color) String\n"
            "    from\n"
            "        match c\n"
            "            Red => \"red\"\n"
            "            _ => \"other\"\n"
        )

    def test_unknown_variant_error(self):
        check_fails(
            "type Color is Red | Green\n"
            "transforms bad(c Color) String\n"
            "    from\n"
            "        match c\n"
            "            Red => \"red\"\n"
            "            Green => \"green\"\n"
            "            Purple => \"purple\"\n",
            "E370",
        )

    def test_unreachable_after_wildcard(self):
        check_warns(
            "type Color is Red | Green\n"
            "transforms name(c Color) String\n"
            "    from\n"
            "        match c\n"
            "            _ => \"any\"\n"
            "            Red => \"red\"\n",
            "W301",
        )


class TestFailPropagation:
    """Test fail propagation (!) checking."""

    def test_valid_fail_prop(self):
        check(
            "inputs may_fail(x Integer) Result<Integer, Error>!\n"
            "    from\n"
            "        x\n"
            "main() Result<Unit, Error>!\n"
            "    from\n"
            "        may_fail(42)!\n"
        )

    def test_fail_in_non_failable(self):
        check_fails(
            "inputs may_fail(x Integer) Result<Integer, Error>!\n"
            "    from\n"
            "        x\n"
            "transforms bad() Integer\n"
            "    from\n"
            "        may_fail(42)!\n",
            "E350",
        )


class TestIntegration:
    """Integration tests with realistic programs."""

    def test_hello_world(self):
        check(
            "main() Unit\n"
            "    from\n"
            "        println(\"Hello from Prove!\")\n"
        )

    def test_multiple_declarations(self):
        st = check(
            "type Point is\n"
            "    x Integer\n"
            "    y Integer\n"
            "MAX_COORD as Integer = 1000\n"
            "transforms origin() Point\n"
            "    from\n"
            "        Point(0, 0)\n"
            "transforms manhattan(p Point) Integer\n"
            "    from\n"
            "        p.x + p.y\n"
        )
        assert st.resolve_type("Point") is not None
        assert st.lookup("MAX_COORD") is not None

    def test_complex_function(self):
        check(
            "type MyResult is\n"
            "    Ok(value Integer)\n"
            "    | Err(message String)\n"
            "transforms safe_divide(a Integer, b Integer) MyResult\n"
            "    from\n"
            "        match b == 0\n"
            "            true => Err(\"division by zero\")\n"
            "            false => Ok(a)\n"
        )

    def test_list_operations(self):
        check(
            "transforms total(nums List<Integer>) Integer\n"
            "    from\n"
            "        len(nums)\n"
        )

    def test_if_expression(self):
        check(
            "transforms abs_val(x Integer) Integer\n"
            "    from\n"
            "        if x > 0\n"
            "            x\n"
            "        else\n"
            "            0 - x\n"
        )

    def test_lambda_expression(self):
        check(
            "transforms apply(xs List<Integer>) List<Integer>\n"
            "    from\n"
            "        map(xs, |x| x + 1)\n"
        )

    def test_imports(self):
        check(
            "with Math use transforms sin, transforms cos\n"
            "transforms angle(x Integer) Integer\n"
            "    from\n"
            "        sin(x)\n"
        )

    def test_string_interpolation(self):
        check(
            "transforms greet(name String) String\n"
            "    from\n"
            "        \"Hello, {name}!\"\n"
        )

    def test_validates_function(self):
        check(
            "validates is_valid(x Integer)\n"
            "    from\n"
            "        x > 0\n"
        )

    def test_main_with_result(self):
        check(
            "main() Result<Unit, Error>!\n"
            "    from\n"
            "        println(\"starting\")\n"
        )
