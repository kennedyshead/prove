"""Tests for imports, namespacing, and stdlib in the Prove semantic analyzer."""

from __future__ import annotations

from prove.types import (
    FLOAT,
    INTEGER,
    STRING,
    AlgebraicType,
    FunctionType,
    PrimitiveType,
    RecordType,
    VariantInfo,
    is_json_serializable,
    types_compatible,
)
from tests.helpers import check, check_fails, check_info, check_warns


class TestStdlibLoading:
    """Test that stdlib imports resolve to real signatures."""

    def test_io_import_resolves(self):
        """Importing from Io should resolve function types."""
        st = check(
            'module Main\n  Io outputs console\n\nmain()\n    from\n        console("hello")\n'
        )
        # console should resolve without error
        sig = st.resolve_function_any("console")
        assert sig is not None


class TestNamespacedCalls:
    """Test Module.function() syntax."""

    def test_namespaced_call_resolves(self):
        """System.console() should resolve when imported."""
        check(
            "module Main\n"
            "  System outputs console\n"
            "\n"
            "main()\n"
            "    from\n"
            '        System.console("hello")\n'
        )

    def test_namespaced_call_unimported_module_errors(self):
        """Module.function() should error if module is not imported."""
        check_fails(
            "module Main\n"
            '  narrative: """test"""\n'
            "\n"
            "transforms run() Integer\n"
            "    from\n"
            "        Table.new()\n",
            "E313",
        )

    def test_namespaced_call_unimported_function_errors(self):
        """Module.function() should error if function is not imported."""
        check_fails(
            "module Main\n"
            "  System outputs console\n"
            "\n"
            "outputs run() Unit\n"
            "    from\n"
            '        System.file("test.txt")\n',
            "E312",
        )


class TestUnusedImport:
    """Test W302 unused import warning."""

    def test_unused_import_info(self):
        """W302: imported name never used (info — formatter removes)."""
        check_info(
            "module Main\n"
            "  Text transforms trim\n"
            "\n"
            "transforms greet(name String) String\n"
            "    from\n"
            "        name\n",
            "I302",
        )

    def test_used_import_no_warning(self):
        """Used import should not trigger W302."""
        check(
            "module Main\n"
            "  Text transforms trim\n"
            "\n"
            "transforms clean(s String) String\n"
            "    from\n"
            "        Text.trim(s)\n",
        )


class TestImportVerbWarning:
    """Test W312: import verb mismatch warning."""

    def test_w312_fires_for_wrong_verb(self):
        """Parse has creates/reads json but no 'transforms json'."""
        check_warns(
            "module Main\n  Parse transforms json\nmain() Unit\n    from\n        0\n",
            "W312",
        )

    def test_no_w312_for_correct_verb(self):
        """'creates json' matches, no warning expected."""
        st = check("module Main\n  Parse creates json\nmain() Unit\n    from\n        0\n")
        # No error or warning about verb mismatch
        assert st is not None


class TestCreatesValue:
    """Test creates value(Value) — explicit verb-gated Record→Value conversion."""

    def test_creates_value_accepts_record(self):
        """creates value(user) should type-check for serializable records."""
        check(
            "module Main\n"
            "  Parse types Value\n"
            "  Parse creates value\n"
            "  type User is\n"
            "    id Integer\n"
            "    name String\n"
            "\n"
            "creates wrap(u User) Value\n"
            "    from\n"
            "        value(u)\n"
        )

    def test_creates_value_pipe_to_json(self):
        """user |> value |> json |> string pattern should type-check."""
        check(
            "module Main\n"
            "  Parse types Value\n"
            "  Parse creates value json\n"
            "  Types creates string\n"
            "  type User is\n"
            "    id Integer\n"
            "    name String\n"
            "\n"
            "reads render(u User) String\n"
            "    from\n"
            "        u |> value |> json |> string\n"
        )

    def test_creates_value_rejects_non_serializable(self):
        """Algebraic types are not serializable — should error."""
        check_fails(
            "module Main\n"
            "  Parse types Value\n"
            "  Parse creates value\n"
            "  type Color is\n"
            "    Red\n"
            "    | Green\n"
            "\n"
            "creates wrap(c Color) Value\n"
            "    from\n"
            "        value(c)\n",
            "E320",
        )

    def test_validates_value_accepts_record(self):
        """validates value(user) should type-check for serializable records."""
        check(
            "module Main\n"
            "  Parse validates value\n"
            "  type User is\n"
            "    id Integer\n"
            "    name String\n"
            "\n"
            "validates ok(u User) Boolean\n"
            "    from\n"
            "        value(u)\n"
        )

    def test_validates_value_rejects_non_serializable(self):
        """Algebraic types are not serializable — should error."""
        check_fails(
            "module Main\n"
            "  Parse validates value\n"
            "  type Color is\n"
            "    Red\n"
            "    | Green\n"
            "\n"
            "validates ok(c Color) Boolean\n"
            "    from\n"
            "        value(c)\n",
            "E320",
        )


class TestRecordValueSerializable:
    """Test is_json_serializable() — used by creates value(Value) gate."""

    def test_record_with_primitives_serializable(self):
        user = RecordType("User", {"id": INTEGER, "name": STRING})
        assert is_json_serializable(user) is True

    def test_record_implicitly_compatible_with_value(self):
        """Record with serializable fields IS compatible with Value."""
        user = RecordType("User", {"id": INTEGER, "name": STRING})
        value = PrimitiveType("Value")
        assert types_compatible(value, user) is True

    def test_algebraic_not_serializable(self):
        color = AlgebraicType(
            "Color",
            [
                VariantInfo("Red"),
                VariantInfo("Green"),
                VariantInfo("Blue"),
            ],
        )
        assert is_json_serializable(color) is False

    def test_record_with_function_field_not_serializable(self):
        bad = RecordType(
            "Bad",
            {
                "fn": FunctionType([INTEGER], STRING),
            },
        )
        assert is_json_serializable(bad) is False

    def test_nested_record_serializable(self):
        inner = RecordType("Address", {"city": STRING})
        outer = RecordType("Person", {"name": STRING, "addr": inner})
        assert is_json_serializable(outer) is True

    def test_record_with_float_serializable(self):
        point = RecordType("Point", {"x": FLOAT, "y": FLOAT})
        assert is_json_serializable(point) is True

    def test_is_json_serializable_primitives(self):
        assert is_json_serializable(STRING) is True
        assert is_json_serializable(INTEGER) is True
        assert is_json_serializable(FLOAT) is True
        assert is_json_serializable(PrimitiveType("Boolean")) is True
        assert is_json_serializable(PrimitiveType("Value")) is True

    def test_is_json_serializable_rejects_function(self):
        assert is_json_serializable(FunctionType([INTEGER], STRING)) is False

    def test_is_json_serializable_rejects_algebraic(self):
        color = AlgebraicType("Color", [VariantInfo("Red")])
        assert is_json_serializable(color) is False


class TestConstantImport:
    """Test importing constants from stdlib."""

    def test_import_nonexistent_constant_errors(self):
        """import Log NONEXISTENT should produce E315."""
        check_fails(
            "module Main\n  Log NONEXISTENT\n\nmain()\n    from\n        0\n",
            "E315",
        )


class TestSelfImport:
    """Test E318 self-import detection."""

    def test_self_import_errors(self):
        """E318: module importing from itself should error."""
        check_fails(
            "module Foo\n  Foo outputs bar\n\noutputs bar() Unit\n    from\n        0\n",
            "E318",
        )

    def test_self_import_case_insensitive(self):
        """E318: self-import detection is case-insensitive."""
        check_fails(
            "module MyMod\n"
            "  Mymod outputs something\n"
            "\n"
            "outputs something() Unit\n"
            "    from\n"
            "        0\n",
            "E318",
        )
