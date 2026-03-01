"""Tests for ASM code generation infrastructure."""

from prove.asm_codegen import AsmCodegen
from prove.asm_types import FieldLayout, map_type_asm, struct_layout
from prove.types import (
    BOOLEAN,
    DECIMAL,
    INTEGER,
    STRING,
    UNIT,
    ListType,
    PrimitiveType,
    RecordType,
)


class TestAsmTypeMapping:
    def test_integer(self):
        t = map_type_asm(INTEGER)
        assert t.size == 8
        assert t.alignment == 8
        assert not t.is_pointer

    def test_boolean(self):
        t = map_type_asm(BOOLEAN)
        assert t.size == 1
        assert not t.is_pointer

    def test_string_is_pointer(self):
        t = map_type_asm(STRING)
        assert t.is_pointer
        assert t.size == 8

    def test_decimal(self):
        t = map_type_asm(DECIMAL)
        assert t.size == 8
        assert not t.is_pointer

    def test_unit(self):
        t = map_type_asm(UNIT)
        assert t.size == 0

    def test_list_is_pointer(self):
        t = map_type_asm(ListType(INTEGER))
        assert t.is_pointer
        assert t.size == 8

    def test_integer_16(self):
        ty = PrimitiveType("Integer", ("16",))
        t = map_type_asm(ty)
        assert t.size == 2

    def test_integer_32(self):
        ty = PrimitiveType("Integer", ("32",))
        t = map_type_asm(ty)
        assert t.size == 4


class TestStructLayout:
    def test_simple_record(self):
        rt = RecordType("Point", {"x": INTEGER, "y": INTEGER}, ())
        fields = struct_layout(rt)
        assert len(fields) == 2
        assert fields[0] == FieldLayout("x", 0, 8, 8)
        assert fields[1] == FieldLayout("y", 8, 8, 8)

    def test_mixed_types(self):
        rt = RecordType(
            "Mixed",
            {"flag": BOOLEAN, "count": INTEGER},
            (),
        )
        fields = struct_layout(rt)
        assert fields[0].name == "flag"
        assert fields[0].offset == 0
        assert fields[0].size == 1
        # count should be aligned to 8
        assert fields[1].name == "count"
        assert fields[1].offset == 8
        assert fields[1].size == 8

    def test_total_size(self):
        rt = RecordType("Point", {"x": INTEGER, "y": INTEGER}, ())
        info = map_type_asm(rt)
        assert info.size == 16
        assert info.alignment == 8


class TestAsmCodegenBase:
    """Test the abstract base class helpers."""

    def test_new_label(self):
        # Create a minimal concrete subclass for testing
        class DummyCodegen(AsmCodegen):
            def emit_prologue(self, name, stack_size): ...
            def emit_epilogue(self): ...
            def emit_load_imm(self, value): ...
            def emit_load_local(self, offset): ...
            def emit_store_local(self, offset): ...
            def emit_call(self, name, arg_count): ...
            def emit_ret(self): ...
            def emit_push_result(self): ...
            def emit_pop_arg(self, arg_index): ...
            def emit_branch(self, label): ...
            def emit_branch_if_zero(self, label): ...
            def emit_compare(self, op): ...
            def emit_arith(self, op): ...
            def emit_negate(self): ...
            def emit_not(self): ...
            def emit_load_string(self, label): ...
            def emit_global(self, name): ...
            def emit_text_section(self): ...

        cg = DummyCodegen()
        l1 = cg.new_label()
        l2 = cg.new_label()
        assert l1 != l2
        assert l1.startswith(".L")

    def test_string_data(self):
        class DummyCodegen(AsmCodegen):
            def emit_prologue(self, name, stack_size): ...
            def emit_epilogue(self): ...
            def emit_load_imm(self, value): ...
            def emit_load_local(self, offset): ...
            def emit_store_local(self, offset): ...
            def emit_call(self, name, arg_count): ...
            def emit_ret(self): ...
            def emit_push_result(self): ...
            def emit_pop_arg(self, arg_index): ...
            def emit_branch(self, label): ...
            def emit_branch_if_zero(self, label): ...
            def emit_compare(self, op): ...
            def emit_arith(self, op): ...
            def emit_negate(self): ...
            def emit_not(self): ...
            def emit_load_string(self, label): ...
            def emit_global(self, name): ...
            def emit_text_section(self): ...

        cg = DummyCodegen()
        cg.add_string_data(".str1", "hello")
        cg.emit_data_section()
        out = cg.output()
        assert ".rodata" in out
        assert '.asciz "hello"' in out
