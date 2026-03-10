"""Tests for the Prove semantic analyzer."""

from __future__ import annotations

from prove.source import Span
from prove.symbols import FunctionSignature, SymbolTable
from prove.types import (
    INTEGER,
    STRING,
)
from tests.helpers import check, check_fails, check_info, check_warns


class TestNameResolution:
    """Test name lookups in scope."""

    def test_params_in_scope(self):
        check("transforms add(a Integer, b Integer) Integer\n    from\n        a\n")

    def test_local_var_in_scope(self):
        check(
            "transforms compute(x Integer) Integer\n"
            "    from\n"
            "        result as Integer = x\n"
            "        result\n"
        )

    def test_undefined_name_error(self):
        check_fails(
            "transforms bad() Integer\n    from\n        unknown_var\n",
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
        st = check("module M\n  MAX_SIZE as Integer = 100\n")
        sym = st.lookup("MAX_SIZE")
        assert sym is not None
        assert sym.resolved_type == INTEGER


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
            '        needs_int("hello")\n',
            "E331",
        )

    def test_undefined_function_error(self):
        check_fails(
            "transforms bad() Integer\n    from\n        nonexistent_func(42)\n",
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

    def test_imported_console(self):
        check(
            "module Main\n"
            "  System outputs console\n"
            "main() Unit\n"
            "    from\n"
            '        console("hello")\n'
        )

    def test_builtin_len(self):
        check("transforms count() Integer\n    from\n        len([1, 2, 3])\n")


class TestFieldAccess:
    """Test field access on records."""

    def test_valid_field(self):
        check(
            "module M\n"
            "  type Point is\n"
            "    x Integer\n"
            "    y Integer\n"
            "transforms get_x(p Point) Integer\n"
            "    from\n"
            "        p.x\n"
        )

    def test_invalid_field(self):
        check_fails(
            "module M\n"
            "  type Point is\n"
            "    x Integer\n"
            "    y Integer\n"
            "transforms bad(p Point) Integer\n"
            "    from\n"
            "        p.z\n",
            "E340",
        )


class TestLambdaCapture:
    """Test closure capture detection."""

    def test_lambda_capture_rejected(self):
        """Lambda capturing a local variable -> E364."""
        check_fails(
            "transforms compute() List<Integer>\n"
            "    from\n"
            "        y as Integer = 10\n"
            "        map([1, 2, 3], |x| x + y)\n",
            "E364",
        )

    def test_lambda_param_capture_ok(self):
        """Lambda capturing a function parameter is allowed."""
        check(
            "transforms compute(y Integer) List<Integer>\n"
            "    from\n"
            "        map([1, 2, 3], |x| x + y)\n"
        )

    def test_lambda_no_capture_ok(self):
        """Lambda using only its own params is fine."""
        check("transforms doubled() List<Integer>\n    from\n        map([1, 2, 3], |x| x * 2)\n")


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
            "module Main\n"
            "  System outputs console\n"
            "main() Unit\n"
            "    from\n"
            '        console("Hello from Prove!")\n'
        )

    def test_multiple_declarations(self):
        st = check(
            "module M\n"
            "  type Point is\n"
            "    x Integer\n"
            "    y Integer\n"
            "  MAX_COORD as Integer = 1000\n"
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
            "module M\n"
            "  type MyResult is\n"
            "    Ok(value Integer)\n"
            "    | Err(message String)\n"
            "matches safe_divide(a Integer, b Integer) MyResult\n"
            "    from\n"
            "        match b == 0\n"
            '            true => Err("division by zero")\n'
            "            false => Ok(a)\n"
        )

    def test_list_operations(self):
        check("transforms total(nums List<Integer>) Integer\n    from\n        len(nums)\n")

    def test_lambda_expression(self):
        check(
            "transforms apply(xs List<Integer>) List<Integer>\n"
            "    from\n"
            "        map(xs, |x| x + 1)\n"
        )

    def test_imports_unknown_module(self):
        check_fails(
            "module Main\n"
            "  Quantum transforms spin flip\n"
            "transforms angle(x Integer) Integer\n"
            "    from\n"
            "        spin(x)\n",
            "I314",
        )

    def test_imports_known_module(self):
        check(
            "module Main\n"
            '  narrative: "test"\n'
            "  System outputs console\n"
            "main() Unit\n"
            "    from\n"
            '        System.console("hello")\n'
        )

    def test_string_interpolation(self):
        check('transforms greet(name String) String\n    from\n        f"Hello, {name}!"\n')

    def test_fstring_non_stringable_type_error(self):
        check_fails(
            "module Test\n"
            "  type Point is\n"
            "    x Integer\n"
            "    y Integer\n"
            "transforms show(p Point) String\n"
            "    from\n"
            '        f"point: {p}"\n',
            "E325",
        )

    def test_validates_function(self):
        check("validates is_valid(x Integer)\n    from\n        x > 0\n")

    def test_main_with_result(self):
        check(
            "module Main\n"
            "  System outputs console\n"
            "main() Result<Unit, Error>!\n"
            "    from\n"
            '        console("starting")\n'
        )


class TestShadowing:
    """Test E316 and E317 shadowing errors."""

    def test_function_shadows_builtin(self):
        """E316: function name shadows builtin with same param types."""
        check_fails(
            "transforms clamp(a Integer, b Integer, c Integer) Integer\n    from\n        a\n",
            "E316",
        )

    def test_function_overload_allowed(self):
        """Overloads with different param types should not trigger E316."""
        check(
            "transforms clamp(a Float, b Float, c Float) Float\n    from\n        a\n",
        )

    def test_parameter_shadows_builtin(self):
        """E316: parameter name shadows builtin function."""
        check_fails(
            "transforms foo(len Integer) Integer\n    from\n        len\n",
            "E316",
        )

    def test_type_shadows_builtin(self):
        """E317: type name shadows builtin type."""
        check_fails(
            "module M\n  type Integer is\n    value String\n",
            "E317",
        )

    def test_stdlib_module_exempt_from_e316(self):
        """Stdlib modules may redefine builtins with same types (they provide them)."""
        check(
            "module Math\n"
            "    narrative: \"math stdlib\"\n"
            "\n"
            "transforms clamp(value Integer, minimum Integer, maximum Integer) Integer\n"
            "    from\n"
            "        value\n",
        )

    def test_no_shadow_for_normal_names(self):
        """Normal names should not trigger E316 or E317."""
        check("transforms add(a Integer, b Integer) Integer\n    from\n        a + b\n")


class TestUnusedType:
    """Test W303 unused type definition warning."""

    def test_unused_type_info(self):
        """W303: type defined but never used (info — formatter removes it)."""
        check_info(
            "module M\n"
            "  type Unused is\n"
            "    x Integer\n"
            "\n"
            "transforms one() Integer\n"
            "    from\n"
            "        1\n",
            "I303",
        )

    def test_used_type_no_warning(self):
        """Used type should not trigger W303."""
        check(
            "module M\n"
            "  type Point is\n"
            "    x Integer\n"
            "    y Integer\n"
            "\n"
            "transforms origin() Point\n"
            "    from\n"
            "        Point(0, 0)\n",
        )


class TestLookupTable:
    """Tests for [Lookup] type modifier checking (E375, E376, E377, E378)."""

    def test_valid_lookup(self):
        """A valid [Lookup] type should produce no errors."""
        check(
            "module M\n"
            "\n"
            "  type TokenKind:[Lookup] is String where\n"
            '      Main | "main"\n'
            '      From | "from"\n'
            '      Type | "type"\n'
            "\n"
            "main()\n"
            "    from\n"
            "        0\n"
        )

    def test_e375_duplicate_value(self):
        """E375: duplicate value in lookup table."""
        check_fails(
            "module M\n"
            "\n"
            "  type TokenKind:[Lookup] is String where\n"
            '      Main | "main"\n'
            '      From | "main"\n'
            "\n"
            "main()\n"
            "    from\n"
            "        0\n",
            "E375",
        )

    def test_many_to_one_mapping_allowed(self):
        """Many-to-one: same variant with stacked values is allowed."""
        check(
            "module M\n"
            "\n"
            "  type BoolLit:[Lookup] is String where\n"
            '      True | "true"\n'
            '           | "yes"\n'
            '      False | "false"\n'
            "\n"
            "main()\n"
            "    from\n"
            "        0\n"
        )

    def test_e376_variable_operand(self):
        """E376: TypeName:variable (not a literal or variant)."""
        check_fails(
            "module M\n"
            "\n"
            "  type TokenKind:[Lookup] is String where\n"
            '      Main | "main"\n'
            '      From | "from"\n'
            "\n"
            "transforms resolve(s String) String\n"
            "    from\n"
            "        TokenKind:s\n",
            "E376",
        )

    def test_e377_value_not_found(self):
        """E377: TypeName:"unknown" not in the table."""
        check_fails(
            "module M\n"
            "\n"
            "  type TokenKind:[Lookup] is String where\n"
            '      Main | "main"\n'
            '      From | "from"\n'
            "\n"
            "main()\n"
            "    from\n"
            '        TokenKind:"unknown"\n',
            "E377",
        )

    def test_e377_variant_not_found(self):
        """E377: TypeName:Missing variant not in table."""
        check_fails(
            "module M\n"
            "\n"
            "  type TokenKind:[Lookup] is String where\n"
            '      Main | "main"\n'
            '      From | "from"\n'
            "\n"
            "main()\n"
            "    from\n"
            "        TokenKind:Type\n",
            "E377",
        )

    def test_forward_lookup_returns_algebraic_type(self):
        """TokenKind:"main" should resolve to the algebraic type."""
        check(
            "module M\n"
            "\n"
            "  type TokenKind:[Lookup] is String where\n"
            '      Main | "main"\n'
            '      From | "from"\n'
            "\n"
            "main()\n"
            "    from\n"
            '        TokenKind:"main"\n'
        )

    def test_reverse_lookup_returns_value_type(self):
        """TokenKind:Main should resolve to String."""
        check(
            "module M\n"
            "\n"
            "  type TokenKind:[Lookup] is String where\n"
            '      Main | "main"\n'
            '      From | "from"\n'
            "\n"
            "main()\n"
            "    from\n"
            "        TokenKind:Main\n"
        )

    def test_e378_reverse_stacked_variant(self):
        """E378: reverse lookup on stacked variant is ambiguous."""
        check_fails(
            "module M\n"
            "\n"
            "  type BoolLit:[Lookup] is String where\n"
            '      BooleanLit | "true"\n'
            '                 | "false"\n'
            "\n"
            "main()\n"
            "    from\n"
            "        BoolLit:BooleanLit\n",
            "E378",
        )

    def test_e377_not_a_lookup_type(self):
        """E377: accessing a type that is not [Lookup]."""
        check_fails(
            'module M\n\n  type Color is Red | Blue\n\nmain()\n    from\n        Color:"red"\n',
            "E377",
        )


class TestFunctionResolutionArity:
    """resolve_function should prefer arity-matching verb over arity-mismatched verb."""

    def test_arity_match_across_verbs(self):
        dummy_span = Span("<test>", 0, 0, 1, 1)
        st = SymbolTable()
        sig1 = FunctionSignature(
            verb="transforms",
            name="process",
            param_names=["a", "b"],
            param_types=[INTEGER, INTEGER],
            return_type=INTEGER,
            can_fail=False,
            span=dummy_span,
        )
        sig2 = FunctionSignature(
            verb=None,
            name="process",
            param_names=["a"],
            param_types=[INTEGER],
            return_type=STRING,
            can_fail=False,
            span=dummy_span,
        )
        st.define_function(sig1)
        st.define_function(sig2)
        result = st.resolve_function("transforms", "process", 1)
        assert result is sig2


# ── Fix: arity mismatch falls through to resolve_function_any ────────


class TestArityMismatchFallthrough:
    """Test that function resolution tries resolve_function_any on arity mismatch."""

    def test_resolves_correct_arity_overload(self):
        """When verb-based resolution returns wrong arity, fall through to any."""
        # Two functions with the same name but different arities and verbs.
        # Calling with 1 arg from an inputs context should NOT match
        # inputs fetch() (0-arg) — it should fall through and find
        # outputs fetch(msg String).
        check(
            "module Main\n"
            "  System inputs console\n"
            "  System outputs console\n"
            "inputs fetch() String\n"
            "    from\n"
            "        console()\n"
            "\n"
            "outputs fetch(msg String) Unit\n"
            "    from\n"
            "        console(msg)\n"
            "\n"
            "inputs run() Unit\n"
            "    from\n"
            '        fetch("hello")\n'
        )


# ── User-defined function overloads ──────────────────────────────


class TestUserDefinedOverloads:
    """Test that overloads (same verb+name, different param types) are allowed."""

    def test_overload_different_param_types_allowed(self):
        """Two functions with same verb/name but different param types should be allowed."""
        check(
            "transforms add(a Integer, b Integer) Integer\n"
            "    from\n"
            "        a + b\n"
            "\n"
            "transforms add(a Float, b Float) Float\n"
            "    from\n"
            "        a + b\n"
        )

    def test_overload_different_arity_allowed(self):
        """Same verb/name with different arity should be allowed."""
        check(
            "transforms double(n Integer) Integer\n"
            "    from\n"
            "        n * 2\n"
            "\n"
            "transforms double(a Integer, b Integer) Integer\n"
            "    from\n"
            "        (a + b) * 2\n"
        )

    def test_exact_duplicate_emits_e301(self):
        """Exact duplicate (same verb, name, param types) should emit E301."""
        check_fails(
            "transforms add(a Integer, b Integer) Integer\n"
            "    from\n"
            "        a + b\n"
            "\n"
            "transforms add(x Integer, y Integer) Integer\n"
            "    from\n"
            "        x + y\n",
            "E301",
        )

    def test_different_verb_same_name_allowed(self):
        """Same name with different verbs is channel dispatch, not overloading."""
        check(
            "transforms format(n Integer) String\n"
            "    from\n"
            "        to_string(n)\n"
            "\n"
            "validates format(n Integer)\n"
            "    from\n"
            "        n > 0\n"
        )

    def test_overload_call_resolves_correctly(self):
        """Calls should resolve to the correct overload by arg types."""
        check(
            "transforms double(n Integer) Integer\n"
            "    from\n"
            "        n * 2\n"
            "\n"
            "transforms double(n Float) Float\n"
            "    from\n"
            "        n * 2.0\n"
            "\n"
            "transforms test() Integer\n"
            "    from\n"
            "        double(5)\n"
        )


# ── Fix: verb-aware recursion detection ──────────────────────────────


class TestVerbAwareRecursion:
    """Test that recursion detection is verb-aware."""

    def test_same_verb_detected_as_recursive(self):
        """Calling same-name same-verb function is recursion → E366."""
        check_fails(
            "matches f(n Integer) Integer\n"
            "    from\n"
            "        match n\n"
            "            0 => 0\n"
            "            _ => f(n - 1)\n",
            "E366",
        )

    def test_same_verb_with_terminates_no_w326(self):
        """Recursive function with terminates → no W326."""
        check(
            "matches f(n Integer) Integer\n"
            "    terminates: n == 0\n"
            "    from\n"
            "        match n\n"
            "            0 => 0\n"
            "            _ => f(n - 1)\n",
        )

    def test_different_verb_not_recursive(self):
        """Calling same-name different-verb function is NOT recursion."""
        check(
            "module M\n"
            "  type Item is\n"
            "    name String\n"
            "\n"
            "transforms item(name String) Item\n"
            "    from\n"
            "        Item(name)\n"
            "\n"
            "reads item(i Item) String\n"
            "    from\n"
            "        i.name\n"
        )


class TestBinaryLookup:
    """Tests for binary lookup table checking (E379, E387, E389)."""

    def test_valid_binary_lookup(self):
        """A valid binary lookup type should produce no errors."""
        check(
            "module M\n"
            "\n"
            "  binary TokenKind String Integer where\n"
            '      First | "first" | 1\n'
            '      Second | "second" | 2\n'
            "\n"
            "main()\n"
            "    from\n"
            "        0\n"
        )

    def test_binary_lookup_forward_access(self):
        """Binary lookup with forward variant -> column access."""
        check(
            "module M\n"
            "\n"
            "  binary TokenKind String Integer where\n"
            '      First | "first" | 1\n'
            '      Second | "second" | 2\n'
            "\n"
            "transforms lookup_word(kind TokenKind) String\n"
            "    from\n"
            "        TokenKind:kind\n"
        )

    def test_binary_lookup_reverse_access(self):
        """Binary lookup with reverse string -> variant access."""
        check(
            "module M\n"
            "\n"
            "  binary TokenKind String Integer where\n"
            '      First | "first" | 1\n'
            '      Second | "second" | 2\n'
            "\n"
            "transforms lookup_kind(word String) TokenKind\n"
            "    from\n"
            "        TokenKind:word\n"
        )

    def test_binary_lookup_literal_access(self):
        """Binary lookup with literal access still works."""
        check(
            "module M\n"
            "\n"
            "  binary TokenKind String Integer where\n"
            '      First | "first" | 1\n'
            '      Second | "second" | 2\n'
            "\n"
            "main()\n"
            "    from\n"
            '        TokenKind:"first"\n'
        )

    def test_e379_column_count_mismatch(self):
        """E379: entry has wrong number of columns."""
        check_fails(
            "module M\n"
            "\n"
            "  binary TokenKind String Integer Decimal where\n"
            '      First | "first" | 1\n'
            "\n"
            "main()\n"
            "    from\n"
            "        0\n",
            "E379",
        )

    def test_e387_unsupported_column_type(self):
        """E387: unsupported type in binary lookup column."""
        check_fails(
            "module M\n"
            "\n"
            "  type Color is Red | Blue\n"
            "\n"
            "  binary TokenKind Color Integer where\n"
            '      First | "first" | 1\n'
            "\n"
            "main()\n"
            "    from\n"
            "        0\n",
            "E387",
        )

    def test_e389_return_type_mismatch(self):
        """E389: return type doesn't match any binary lookup column."""
        check_fails(
            "module M\n"
            "\n"
            "  binary TokenKind String Integer where\n"
            '      First | "first" | 1\n'
            '      Second | "second" | 2\n'
            "\n"
            "transforms lookup_bad(kind TokenKind) Decimal\n"
            "    from\n"
            "        TokenKind:kind\n",
            "E389",
        )

    def test_e397_binary_function_body_non_stdlib(self):
        """E397: binary function body in non-stdlib module."""
        check_fails(
            "module M\n"
            "\n"
            "transforms demo() Integer\n"
            "    binary\n",
            "E397",
        )

    def test_e397_binary_type_body_non_stdlib(self):
        """E397: binary type body in non-stdlib module."""
        check_fails(
            "module M\n"
            "\n"
            "  type OpaqueHandle is binary\n"
            "\n"
            "main()\n"
            "    from\n"
            "        0\n",
            "E397",
        )


class TestImplicitValueReturn:
    """Test E395 implicit Value → concrete return type coercion."""

    def test_value_return_as_string(self):
        """E395: function returns Value but declares String."""
        check_fails(
            "module M\n"
            "  Parse creates json\n"
            "\n"
            "transforms name(source String) String\n"
            "    requires valid json(source)\n"
            "    from\n"
            "        json(source)\n",
            "E395",
        )

    def test_table_value_return_as_table_string(self):
        """E395: function returns Table<Value> but declares Table<String>."""
        check_fails(
            "module M\n"
            "  Parse creates toml\n"
            "\n"
            "transforms config(source String) Table<String>\n"
            "    requires valid toml(source)\n"
            "    from\n"
            "        toml(source)\n",
            "E395",
        )

    def test_table_value_return_ok(self):
        """No E395 when return type matches: Table<Value> → Table<Value>."""
        from tests.helpers import check_all

        diags = check_all(
            "module M\n"
            "  Parse creates toml\n"
            "\n"
            "transforms config(source String) Table<Value>\n"
            "    requires valid toml(source)\n"
            "    from\n"
            "        toml(source)\n",
        )
        assert not any(d.code == "E395" for d in diags)

    def test_validates_exempt(self):
        """No E395 for validates verb (implicit Boolean return)."""
        from tests.helpers import check_all

        diags = check_all(
            "module M\n"
            "  Parse validates value\n"
            "  type User is\n"
            "    id Integer\n"
            "    name String\n"
            "\n"
            "validates ok(u User)\n"
            "    from\n"
            "        value(u)\n",
        )
        assert not any(d.code == "E395" for d in diags)


class TestValueCoercion:
    """Test I311 Value → concrete type coercion diagnostics."""

    def test_value_to_table_coercion_info(self):
        """I311: Value → Table<Value> coercion emits info diagnostic."""
        check_info(
            "module M\n"
            "  Parse creates json\n"
            "\n"
            "outputs run(source String) Unit!\n"
            "    from\n"
            "        conf as Table<Value> = json(source)!\n"
            "        conf\n",
            "I311",
        )

    def test_value_to_string_coercion_info(self):
        """I311: Value → String coercion emits info diagnostic."""
        check_info(
            "module M\n"
            "  Parse creates json\n"
            "\n"
            "outputs run(source String) Unit!\n"
            "    from\n"
            "        val as String = json(source)!\n"
            "        val\n",
            "I311",
        )

    def test_value_to_value_no_info(self):
        """No I311 when target type is also Value (no coercion needed)."""
        from tests.helpers import check_all

        diags = check_all(
            "module M\n"
            "  Parse creates json\n"
            "\n"
            "outputs run(source String) Unit!\n"
            "    from\n"
            "        val as Value = json(source)!\n"
            "        val\n",
        )
        assert not any(d.code == "I311" for d in diags)
