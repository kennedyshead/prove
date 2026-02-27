"""Tests for c_types — Prove Type -> C type mapping."""

from prove.c_types import mangle_name, mangle_type_name, map_type
from prove.types import (
    BOOLEAN,
    DECIMAL,
    FLOAT,
    INTEGER,
    STRING,
    UNIT,
    AlgebraicType,
    GenericInstance,
    ListType,
    PrimitiveType,
    RecordType,
    VariantInfo,
)


class TestMapType:
    def test_integer_default(self):
        ct = map_type(INTEGER)
        assert ct.decl == "int64_t"
        assert ct.is_pointer is False

    def test_integer_32_unsigned(self):
        ty = PrimitiveType("Integer", ("32", "Unsigned"))
        ct = map_type(ty)
        assert ct.decl == "uint32_t"

    def test_integer_16(self):
        ty = PrimitiveType("Integer", ("16",))
        ct = map_type(ty)
        assert ct.decl == "int16_t"

    def test_decimal(self):
        ct = map_type(DECIMAL)
        assert ct.decl == "double"

    def test_float_32(self):
        ty = PrimitiveType("Float", ("32",))
        ct = map_type(ty)
        assert ct.decl == "float"

    def test_boolean(self):
        ct = map_type(BOOLEAN)
        assert ct.decl == "bool"
        assert ct.is_pointer is False

    def test_character(self):
        ct = map_type(PrimitiveType("Character"))
        assert ct.decl == "char"

    def test_byte(self):
        ct = map_type(PrimitiveType("Byte"))
        assert ct.decl == "uint8_t"

    def test_string(self):
        ct = map_type(STRING)
        assert ct.decl == "Prove_String*"
        assert ct.is_pointer is True
        assert ct.header == "prove_string.h"

    def test_unit(self):
        ct = map_type(UNIT)
        assert ct.decl == "void"

    def test_record_type(self):
        ty = RecordType("Point", {"x": INTEGER, "y": INTEGER})
        ct = map_type(ty)
        assert ct.decl == "Prove_Point"
        assert ct.is_pointer is False

    def test_algebraic_type(self):
        ty = AlgebraicType("Shape", [
            VariantInfo("Circle", {"radius": FLOAT}),
            VariantInfo("Square", {"side": FLOAT}),
        ])
        ct = map_type(ty)
        assert ct.decl == "Prove_Shape"

    def test_list_type(self):
        ct = map_type(ListType(INTEGER))
        assert ct.decl == "Prove_List*"
        assert ct.is_pointer is True
        assert ct.header == "prove_list.h"

    def test_result_generic(self):
        ty = GenericInstance("Result", [INTEGER, PrimitiveType("Error")])
        ct = map_type(ty)
        assert ct.decl == "Prove_Result"
        assert ct.header == "prove_result.h"

    def test_option_generic(self):
        ty = GenericInstance("Option", [INTEGER])
        ct = map_type(ty)
        assert "Prove_Option" in ct.decl
        assert ct.header == "prove_option.h"


class TestMangling:
    def test_mangle_name_with_verb(self):
        result = mangle_name("transforms", "add", [INTEGER, INTEGER])
        assert result == "transforms_add_Integer_Integer"

    def test_mangle_name_no_verb(self):
        result = mangle_name(None, "println", [STRING])
        assert result == "println_String"

    def test_mangle_name_no_params(self):
        result = mangle_name("inputs", "main")
        assert result == "inputs_main"

    def test_mangle_type_name(self):
        assert mangle_type_name("Point") == "Prove_Point"
        assert mangle_type_name("Shape") == "Prove_Shape"
