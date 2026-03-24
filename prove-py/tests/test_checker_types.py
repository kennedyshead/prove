"""Tests for the Prove type system — resolution, checking, compatibility."""

from __future__ import annotations

from prove.types import (
    BOOLEAN,
    DECIMAL,
    INTEGER,
    STRING,
    AlgebraicType,
    EffectType,
    GenericInstance,
    PrimitiveType,
    RecordType,
    RefinementType,
    get_scale,
    type_name,
    types_compatible,
)
from tests.helpers import check, check_fails


class TestTypeResolution:
    """Test that types resolve correctly."""

    def test_builtin_types_resolve(self):
        st = check("transforms identity(x Integer) Integer\n    from\n        x\n")
        ty = st.resolve_type("Integer")
        assert ty == INTEGER

    def test_string_type_resolves(self):
        st = check("transforms greet(name String) String\n    from\n        name\n")
        ty = st.resolve_type("String")
        assert ty == STRING

    def test_user_record_type_resolves(self):
        st = check(
            "module M\n"
            "  type Point is\n"
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
            "transforms bad(x Nonexistent) Integer\n    from\n        0\n",
            "E300",
        )

    def test_generic_type_resolves(self):
        check("transforms wrap(x Integer) List<Integer>\n    from\n        [x]\n")

    def test_modified_type_resolves(self):
        check("transforms small(x Integer:[16 Unsigned]) Integer\n    from\n        x\n")

    def test_duplicate_type_error(self):
        check_fails(
            "module M\n  type Foo is\n    x Integer\n  type Foo is\n    y String\n",
            "E301",
        )

    def test_algebraic_type_resolves(self):
        st = check(
            "module M\n"
            "  type Shape is\n"
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
            "module M\n"
            "  type Positive is Integer where >= 0\n"
            "transforms use_pos(x Positive) Integer\n"
            "    from\n"
            "        0\n"
        )
        ty = st.resolve_type("Positive")
        assert isinstance(ty, RefinementType)

    def test_where_constraint_rejects_function_calls(self):
        check_fails(
            'module M\n  type Sku is String where matched(r"^[A-Z]+")\n',
            "E352",
        )

    def test_where_constraint_allows_comparison(self):
        check(
            "module M\n"
            "  type Positive is Integer where self >= 0\n"
            "transforms id(x Positive) Integer\n"
            "    from\n"
            "        0\n"
        )

    def test_where_constraint_allows_range(self):
        check(
            "module M\n"
            "  type Port is Integer where 1 .. 65535\n"
            "transforms id(x Port) Integer\n"
            "    from\n"
            "        0\n"
        )

    def test_verb_type_resolves(self):
        """Verb<Integer, String> resolves to FunctionType."""
        check(
            "transforms apply(fn Verb<Integer, String>, x Integer) String\n"
            "    from\n"
            "        fn(x)\n"
        )


class TestTypeChecking:
    """Test type inference and checking."""

    def test_integer_literal(self):
        check("transforms num() Integer\n    from\n        42\n")

    def test_decimal_literal(self):
        check("transforms dec() Decimal\n    from\n        3.14\n")

    def test_string_literal(self):
        check('transforms greeting() String\n    from\n        "hello"\n')

    def test_boolean_literal(self):
        check("transforms flag() Boolean\n    from\n        true\n")

    def test_binary_arithmetic(self):
        check("transforms add(a Integer, b Integer) Integer\n    from\n        a + b\n")

    def test_binary_comparison(self):
        check("transforms bigger(a Integer, b Integer) Boolean\n    from\n        a > b\n")

    def test_binary_logical(self):
        check("transforms both(a Boolean, b Boolean) Boolean\n    from\n        a && b\n")

    def test_type_mismatch_binary(self):
        check_fails(
            "transforms bad(a Integer, b String) Integer\n    from\n        a + b\n",
            "E320",
        )

    def test_type_mismatch_var_decl(self):
        check_fails(
            "transforms bad() Integer\n    from\n        x as String = 42\n        0\n",
            "E321",
        )

    def test_var_decl_inference(self):
        check("transforms compute() Integer\n    from\n        x as Integer = 42\n        x\n")

    def test_return_type_mismatch(self):
        check_fails(
            "transforms bad() String\n    from\n        42\n",
            "E322",
        )


class TestModifiedTypeCompat:
    """PrimitiveType with modifiers should be compatible with underlying named types."""

    def test_mutable_primitive_compat_with_record(self):
        rec = RecordType("User", {"name": STRING})
        prim = PrimitiveType("User", ((None, "Mutable"),))
        assert types_compatible(rec, prim)

    def test_record_compat_with_mutable_primitive(self):
        rec = RecordType("User", {"name": STRING})
        prim = PrimitiveType("User", ((None, "Mutable"),))
        assert types_compatible(prim, rec)

    def test_mutable_primitive_compat_with_algebraic(self):
        alg = AlgebraicType("Shape", [])
        prim = PrimitiveType("Shape", ((None, "Mutable"),))
        assert types_compatible(alg, prim)

    def test_name_mismatch_still_fails(self):
        rec = RecordType("User", {"name": STRING})
        prim = PrimitiveType("Admin", ((None, "Mutable"),))
        assert not types_compatible(rec, prim)

    def test_no_modifiers_still_incompatible(self):
        rec = RecordType("User", {"name": STRING})
        prim = PrimitiveType("User")
        assert not types_compatible(rec, prim)


# ── Fix: Option<Refinement(Value)> compatibility ─────────────────────────


class TestOptionRefinementCompat:
    """Test that Value → Option<Refinement(Value)> is allowed."""

    def test_option_refinement_compat(self):
        """String should be assignable to Option<Email> where Email = String where ..."""
        email = RefinementType(name="Email", base=STRING)
        option_email = GenericInstance(base_name="Option", args=[email])
        assert types_compatible(option_email, STRING) is True

    def test_option_plain_not_compat(self):
        """String should NOT be assignable to Option<String> (no refinement)."""
        option_string = GenericInstance(base_name="Option", args=[STRING])
        assert types_compatible(option_string, STRING) is False

    def test_option_refinement_wrong_base(self):
        """Integer should NOT be assignable to Option<Email> where Email = String."""
        email = RefinementType(name="Email", base=STRING)
        option_email = GenericInstance(base_name="Option", args=[email])
        assert types_compatible(option_email, INTEGER) is False


class TestStaticRefinementChecking:
    """Static refinement constraint checking at compile time."""

    def test_positive_literal_passes(self):
        check(
            "module M\n"
            "  type Positive is Integer where >= 0\n"
            "transforms use(n Integer) Integer\n"
            "    from\n"
            "        p as Positive = 42\n"
            "        n\n"
        )

    def test_negative_literal_rejected(self):
        check_fails(
            "module M\n"
            "  type Positive is Integer where >= 0\n"
            "transforms use(n Integer) Integer\n"
            "    from\n"
            "        p as Positive = -1\n"
            "        n\n",
            "E355",
        )

    def test_port_range_valid(self):
        check(
            "module M\n"
            "  type Port is Integer where 1 .. 65535\n"
            "transforms use(n Integer) Integer\n"
            "    from\n"
            "        p as Port = 8080\n"
            "        n\n"
        )

    def test_port_range_zero_rejected(self):
        check_fails(
            "module M\n"
            "  type Port is Integer where 1 .. 65535\n"
            "transforms use(n Integer) Integer\n"
            "    from\n"
            "        p as Port = 0\n"
            "        n\n",
            "E355",
        )

    def test_port_range_too_large_rejected(self):
        check_fails(
            "module M\n"
            "  type Port is Integer where 1 .. 65535\n"
            "transforms use(n Integer) Integer\n"
            "    from\n"
            "        p as Port = 70000\n"
            "        n\n",
            "E355",
        )

    def test_nonzero_rejects_zero(self):
        check_fails(
            "module M\n"
            "  type NonZero is Integer where != 0\n"
            "transforms use(n Integer) Integer\n"
            "    from\n"
            "        nz as NonZero = 0\n"
            "        n\n",
            "E355",
        )

    def test_nonzero_accepts_positive(self):
        check(
            "module M\n"
            "  type NonZero is Integer where != 0\n"
            "transforms use(n Integer) Integer\n"
            "    from\n"
            "        nz as NonZero = 42\n"
            "        n\n"
        )

    def test_constant_refinement_rejected(self):
        check_fails(
            "module M\n  type Positive is Integer where >= 0\n  BAD as Positive = -5\n",
            "E355",
        )

    def test_constant_refinement_accepted(self):
        check("module M\n  type Positive is Integer where >= 0\n  GOOD as Positive = 100\n")

    def test_non_literal_skips_static_check(self):
        """Non-literal values should not trigger static refinement errors."""
        check(
            "module M\n"
            "  type Positive is Integer where >= 0\n"
            "transforms add(a Integer, b Integer) Positive\n"
            "    from\n"
            "        result as Positive = a + b\n"
            "        result\n"
        )


class TestFieldAccessOnModifiedType:
    """Field access on User:[Mutable] should resolve through underlying RecordType."""

    def test_field_access_on_mutable_record(self):
        check(
            "module M\n"
            "  type Person is\n"
            "    name String\n"
            "    age Integer\n"
            "\n"
            "transforms get_name(p Person:[Mutable]) String\n"
            "    from\n"
            "        p.name\n"
        )


class TestEffectType:
    """Tests for the EffectType scaffolding."""

    def test_type_name_single_effect(self):
        t = EffectType(INTEGER, frozenset({"IO"}))
        assert type_name(t) == "Integer & IO"

    def test_type_name_multiple_effects(self):
        t = EffectType(STRING, frozenset({"Async", "IO"}))
        assert type_name(t) == "String & Async & IO"

    def test_compatible_effect_with_base(self):
        """EffectType is transparent — compatible with its base."""
        t = EffectType(INTEGER, frozenset({"IO"}))
        assert types_compatible(INTEGER, t)
        assert types_compatible(t, INTEGER)

    def test_compatible_effect_with_effect(self):
        """Two EffectTypes with same base are compatible."""
        t1 = EffectType(INTEGER, frozenset({"IO"}))
        t2 = EffectType(INTEGER, frozenset({"Async"}))
        assert types_compatible(t1, t2)

    def test_incompatible_different_base(self):
        """EffectTypes with different bases are incompatible."""
        t1 = EffectType(INTEGER, frozenset({"IO"}))
        t2 = EffectType(BOOLEAN, frozenset({"IO"}))
        assert not types_compatible(t1, t2)


# ── Scale:N enforcement ─────────────────────────────────────────


class TestScaleEnforcement:
    """Scale:N modifier enforcement (E407, E408)."""

    def test_get_scale_with_scale(self):
        ty = PrimitiveType("Decimal", (("Scale", "2"),))
        assert get_scale(ty) == 2

    def test_get_scale_without_scale(self):
        assert get_scale(DECIMAL) is None

    def test_get_scale_non_decimal(self):
        assert get_scale(INTEGER) is None

    def test_scale_types_compatible_same(self):
        t1 = PrimitiveType("Decimal", (("Scale", "2"),))
        t2 = PrimitiveType("Decimal", (("Scale", "2"),))
        assert types_compatible(t1, t2)

    def test_scale_types_incompatible_different(self):
        t1 = PrimitiveType("Decimal", (("Scale", "2"),))
        t2 = PrimitiveType("Decimal", (("Scale", "3"),))
        assert not types_compatible(t1, t2)

    def test_scale_compatible_with_plain_decimal(self):
        """Decimal:[Scale:2] is compatible with plain Decimal (no scale)."""
        t1 = PrimitiveType("Decimal", (("Scale", "2"),))
        assert types_compatible(t1, DECIMAL)

    def test_type_name_with_scale(self):
        ty = PrimitiveType("Decimal", (("Scale", "2"),))
        assert type_name(ty) == "Decimal:[Scale:2]"

    def test_literal_exceeds_scale_e407(self):
        check_fails(
            "reads demo() Unit\nfrom\n    x as Decimal:[Scale:2] = 3.14159\n",
            "E407",
        )

    def test_literal_within_scale_ok(self):
        check(
            "reads demo() Unit\nfrom\n    x as Decimal:[Scale:2] = 3.14\n",
        )

    def test_decimal_literal_one_place_scale_ok(self):
        check(
            "reads demo() Unit\nfrom\n    x as Decimal:[Scale:2] = 3.1\n",
        )

    def test_scale_mismatch_e408(self):
        check_fails(
            "reads demo() Unit\n"
            "from\n"
            "    a as Decimal:[Scale:3] = 1.123\n"
            "    b as Decimal:[Scale:2] = a\n",
            "E408",
        )

    def test_plain_decimal_no_scale_check(self):
        check(
            "reads demo() Unit\nfrom\n    x as Decimal = 3.14159\n",
        )


# ── Lambda capture ──────────────────────────────────────────────


class TestRecursiveVariantTypes:
    """Recursive variant types — self-reference and mutual recursion."""

    def test_direct_self_reference(self):
        """A type can reference itself in variant fields."""
        check(
            "module M\n"
            "  type Expr is\n"
            "      Literal(value Integer)\n"
            "      Add(left Expr, right Expr)\n"
            "      Negate(inner Expr)\n"
        )

    def test_unit_base_case(self):
        """A recursive type with a unit base case is valid."""
        check("module M\n  type Tree is\n      Leaf\n      Branch(left Tree, right Tree)\n")

    def test_no_base_case_error(self):
        """E423: every variant references the type — no base case."""
        check_fails(
            "module M\n  type Bad is\n      A(x Bad)\n      B(y Bad)\n",
            "E423",
        )

    def test_option_self_reference(self):
        """Option<Self> is indirect — struct layout unchanged."""
        check(
            "module M\n"
            "  type Node is\n"
            "      Leaf(value Integer)\n"
            "      Branch(left Node, right Node, parent Option<Node>)\n"
        )

    def test_list_self_reference(self):
        """List<Self> is indirect — already boxed."""
        check(
            "module M\n"
            "  type Folder is\n"
            "      File(name String)\n"
            "      Dir(name String, children List<Folder>)\n"
        )

    def test_constructor_signatures_correct(self):
        """Recursive type constructors have correct parameter types."""
        from tests.helpers import parse_check

        _, symbols = parse_check(
            "module M\n"
            "  type Expr is\n"
            "      Literal(value Integer)\n"
            "      Add(left Expr, right Expr)\n"
        )
        lit_sig = symbols.resolve_function(None, "Literal", 1)
        add_sig = symbols.resolve_function(None, "Add", 2)
        assert lit_sig is not None
        assert add_sig is not None
        assert isinstance(lit_sig.return_type, AlgebraicType)
        assert lit_sig.return_type.name == "Expr"
        assert isinstance(add_sig.return_type, AlgebraicType)
        assert add_sig.return_type.name == "Expr"


class TestLambdaCapture:
    """Lambda closure capture (replaces E364 rejection)."""

    def test_lambda_without_capture_still_works(self):
        check(
            "transforms result(xs List<Value>) List<Value>\nfrom map(xs, |x| x)\n",
        )

    def test_sequential_lambda_with_capture_ok(self):
        check(
            "transforms result(xs List<Value>, factor Integer) List<Value>\n"
            "from map(xs, |x| x * factor)\n",
        )
