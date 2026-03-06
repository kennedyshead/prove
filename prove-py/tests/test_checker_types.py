"""Tests for the Prove type system — resolution, checking, compatibility."""

from __future__ import annotations

from prove.types import (
    INTEGER,
    STRING,
    AlgebraicType,
    GenericInstance,
    PrimitiveType,
    RecordType,
    RefinementType,
    types_compatible,
)
from tests.helpers import check, check_fails


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
            "module M\n"
            "  type Foo is\n"
            "    x Integer\n"
            "  type Foo is\n"
            "    y String\n",
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
            "module M\n"
            '  type Sku is String where matched(r"^[A-Z]+")\n',
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


class TestModifiedTypeCompat:
    """PrimitiveType with modifiers should be compatible with underlying named types."""

    def test_mutable_primitive_compat_with_record(self):
        rec = RecordType("User", {"name": STRING})
        prim = PrimitiveType("User", ("Mutable",))
        assert types_compatible(rec, prim)

    def test_record_compat_with_mutable_primitive(self):
        rec = RecordType("User", {"name": STRING})
        prim = PrimitiveType("User", ("Mutable",))
        assert types_compatible(prim, rec)

    def test_mutable_primitive_compat_with_algebraic(self):
        alg = AlgebraicType("Shape", [])
        prim = PrimitiveType("Shape", ("Mutable",))
        assert types_compatible(alg, prim)

    def test_name_mismatch_still_fails(self):
        rec = RecordType("User", {"name": STRING})
        prim = PrimitiveType("Admin", ("Mutable",))
        assert not types_compatible(rec, prim)

    def test_no_modifiers_still_incompatible(self):
        rec = RecordType("User", {"name": STRING})
        prim = PrimitiveType("User")
        assert not types_compatible(rec, prim)


# ── Fix: Option<Refinement(T)> compatibility ─────────────────────────


class TestOptionRefinementCompat:
    """Test that T → Option<Refinement(T)> is allowed."""

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
