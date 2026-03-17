"""Tests for row polymorphism (Struct type + with constraints)."""

from __future__ import annotations

from prove.ast_nodes import FunctionDef, SimpleType, WithConstraint
from prove.lexer import Lexer
from prove.parser import Parser
from prove.types import (
    INTEGER,
    STRING,
    STRUCT,
    RecordType,
    StructType,
    type_name,
    types_compatible,
)
from tests.helpers import check, check_fails


def parse(source: str):
    tokens = Lexer(source, "test.prv").lex()
    return Parser(tokens, "test.prv").parse()


def parse_decl(source: str):
    mod = parse(source)
    assert len(mod.declarations) >= 1
    return mod.declarations[0]


# ── Type system tests ────────────────────────────────────────────


class TestStructType:
    """Test StructType in the type system."""

    def test_bare_struct_accepts_any_record(self):
        user = RecordType("User", {"name": STRING, "age": INTEGER})
        assert types_compatible(STRUCT, user)

    def test_constrained_struct_accepts_matching_record(self):
        st = StructType({"name": STRING})
        user = RecordType("User", {"name": STRING, "age": INTEGER})
        assert types_compatible(st, user)

    def test_constrained_struct_rejects_missing_field(self):
        st = StructType({"name": STRING, "email": STRING})
        user = RecordType("User", {"name": STRING, "age": INTEGER})
        assert not types_compatible(st, user)

    def test_constrained_struct_rejects_wrong_type(self):
        st = StructType({"name": INTEGER})
        user = RecordType("User", {"name": STRING})
        assert not types_compatible(st, user)

    def test_struct_rejects_non_records(self):
        assert not types_compatible(STRUCT, STRING)
        assert not types_compatible(STRUCT, INTEGER)

    def test_struct_vs_struct(self):
        a = StructType({"name": STRING})
        b = StructType({"name": STRING, "age": INTEGER})
        # b has all fields of a
        assert types_compatible(a, b)
        # a doesn't have all fields of b
        assert not types_compatible(b, a)

    def test_type_name_bare(self):
        assert type_name(STRUCT) == "Struct"

    def test_type_name_constrained(self):
        st = StructType({"name": STRING})
        assert "Struct" in type_name(st)
        assert "name" in type_name(st)


# ── Parser tests ─────────────────────────────────────────────────


class TestParserWith:
    """Test parsing of with constraints."""

    def test_parse_with_clause(self):
        fd = parse_decl(
            "transforms greeting(entity Struct) String\n"
            "  with entity.name String\n"
            "  from\n"
            "    entity.name\n"
        )
        assert isinstance(fd, FunctionDef)
        assert len(fd.with_constraints) == 1
        wc = fd.with_constraints[0]
        assert wc.param_name == "entity"
        assert wc.field_name == "name"
        assert isinstance(wc.field_type, SimpleType)
        assert wc.field_type.name == "String"

    def test_parse_multiple_with_clauses(self):
        fd = parse_decl(
            "transforms display(obj Struct) String\n"
            "  with obj.name String\n"
            "  with obj.age Integer\n"
            "  from\n"
            "    obj.name\n"
        )
        assert isinstance(fd, FunctionDef)
        assert len(fd.with_constraints) == 2
        assert fd.with_constraints[0].field_name == "name"
        assert fd.with_constraints[1].field_name == "age"

    def test_parse_with_and_ensures(self):
        fd = parse_decl(
            "transforms greeting(entity Struct) String\n"
            "  with entity.name String\n"
            "  ensures result != \"\"\n"
            "  from\n"
            "    entity.name\n"
        )
        assert isinstance(fd, FunctionDef)
        assert len(fd.with_constraints) == 1
        assert len(fd.ensures) == 1

    def test_no_with_constraints_default(self):
        fd = parse_decl(
            "transforms identity(x Integer) Integer\n"
            "  from\n"
            "    x\n"
        )
        assert isinstance(fd, FunctionDef)
        assert fd.with_constraints == []


# ── Checker tests ────────────────────────────────────────────────


class TestCheckerStruct:
    """Test type checking of Struct parameters and with constraints."""

    def test_struct_with_field_access(self):
        """Struct param with `with` allows field access."""
        check(
            "transforms greeting(entity Struct) String\n"
            "  with entity.name String\n"
            "  from\n"
            "    entity.name\n"
        )

    def test_e430_unknown_param(self):
        """E430: with references unknown parameter."""
        check_fails(
            "transforms greeting(entity Struct) String\n"
            "  with other.name String\n"
            "  from\n"
            "    \"hello\"\n",
            "E430",
        )

    def test_e431_non_struct_param(self):
        """E431: with on non-Struct parameter."""
        check_fails(
            "transforms greeting(name String) String\n"
            "  with name.length Integer\n"
            "  from\n"
            "    name\n",
            "E431",
        )

    def test_e432_duplicate_field(self):
        """E432: duplicate with for same field."""
        check_fails(
            "transforms greeting(entity Struct) String\n"
            "  with entity.name String\n"
            "  with entity.name Integer\n"
            "  from\n"
            "    entity.name\n",
            "E432",
        )

    def test_e433_undeclared_field_access(self):
        """E433: field access on Struct not declared via with."""
        check_fails(
            "transforms greeting(entity Struct) String\n"
            "  with entity.name String\n"
            "  from\n"
            "    entity.age\n",
            "E433",
        )


# ── Formatter tests ──────────────────────────────────────────────


class TestFormatterWith:
    """Test formatting of with constraints."""

    def test_roundtrip_with_clause(self):
        from prove.formatter import ProveFormatter

        source = (
            "transforms greeting(entity Struct) String\n"
            "  with entity.name String\n"
            "  from\n"
            "    entity.name\n"
        )
        tokens = Lexer(source, "test.prv").lex()
        mod = Parser(tokens, "test.prv").parse()
        formatted = ProveFormatter().format(mod)
        assert "with entity.name String" in formatted
