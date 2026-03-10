"""Comprehensive tests for formatter auto-fixes.

Each auto-fixable diagnostic is tested for correct formatter behavior:
- I300: unused variable → prefix with _
- I301: unreachable match arm → remove arm
- I302: unused import → remove item or entire line
- I303: unused type → remove definition
- I314: unknown module → remove import line
- I360: validates Boolean → strip return type
"""

from __future__ import annotations

from tests.helpers import check_and_format


# ── I301: unreachable match arm — formatter removes ─────────────────


class TestFixI301:
    """Formatter removes match arms after wildcard."""

    def test_removes_arm_after_wildcard(self):
        source = (
            "module M\n"
            "  type Color is Red | Green\n"
            "\n"
            "  matches name(c Color) String\n"
            "  from\n"
            "      match c\n"
            '          _ => "any"\n'
            '          Red => "red"\n'
        )
        result = check_and_format(source)
        assert '_ => "any"' in result
        assert "Red =>" not in result

    def test_preserves_arms_before_wildcard(self):
        source = (
            "module M\n"
            "  type Color is Red | Green\n"
            "\n"
            "  matches name(c Color) String\n"
            "  from\n"
            "      match c\n"
            '          Red => "red"\n'
            '          _ => "other"\n'
        )
        result = check_and_format(source)
        assert 'Red =>' in result
        assert '_ => "other"' in result

    def test_removes_multiple_unreachable_arms(self):
        source = (
            "module M\n"
            "  type Color is Red | Green | Blue\n"
            "\n"
            "  matches name(c Color) String\n"
            "  from\n"
            "      match c\n"
            '          _ => "any"\n'
            '          Red => "red"\n'
            '          Green => "green"\n'
        )
        result = check_and_format(source)
        assert '_ => "any"' in result
        assert "Red =>" not in result
        assert "Green =>" not in result


# ── I302: unused import — formatter removes ─────────────────────────


class TestFixI302:
    """Formatter removes unused import items."""

    def test_removes_single_unused_item(self):
        source = (
            "module Main\n"
            "  Text transforms trim upper\n"
            "\n"
            "transforms clean(s String) String\n"
            "from\n"
            "    Text.trim(s)\n"
        )
        result = check_and_format(source)
        assert "trim" in result
        assert "upper" not in result

    def test_removes_entire_line_when_all_unused(self):
        source = (
            "module Main\n"
            "  Text transforms trim\n"
            "\n"
            "transforms greet(name String) String\n"
            "from\n"
            "    name\n"
        )
        result = check_and_format(source)
        assert "Text" not in result

    def test_removes_multiple_unused_items_same_verb(self):
        source = (
            "module Main\n"
            "  Text transforms trim upper replace\n"
            "\n"
            "transforms greet(name String) String\n"
            "from\n"
            "    name\n"
        )
        result = check_and_format(source)
        assert "Text" not in result
        assert "trim" not in result
        assert "upper" not in result
        assert "replace" not in result

    def test_removes_some_keeps_others(self):
        source = (
            "module Main\n"
            "  Text transforms trim upper replace\n"
            "\n"
            "transforms shout(s String) String\n"
            "from\n"
            "    Text.upper(s)\n"
        )
        result = check_and_format(source)
        assert "upper" in result
        assert "trim" not in result
        assert "replace" not in result

    def test_removes_from_multi_verb_groups(self):
        source = (
            "module Main\n"
            "  System outputs console, inputs file\n"
            "\n"
            "transforms greet(name String) String\n"
            "from\n"
            "    name\n"
        )
        result = check_and_format(source)
        assert "System" not in result
        assert "console" not in result
        assert "file" not in result

    def test_keeps_used_imports(self):
        source = (
            "module Main\n"
            "  Text transforms trim\n"
            "\n"
            "transforms clean(s String) String\n"
            "from\n"
            "    Text.trim(s)\n"
        )
        result = check_and_format(source)
        assert "Text transforms trim" in result


# ── I303: unused type — formatter removes ───────────────────────────


class TestFixI303:
    """Formatter removes unused type definitions."""

    def test_removes_unused_type(self):
        source = (
            "module M\n"
            "  type Unused is\n"
            "    x Integer\n"
            "\n"
            "transforms one() Integer\n"
            "from\n"
            "    1\n"
        )
        result = check_and_format(source)
        assert "Unused" not in result
        assert "transforms one() Integer" in result

    def test_keeps_used_type(self):
        source = (
            "module M\n"
            "  type Point is\n"
            "    x Integer\n"
            "    y Integer\n"
            "\n"
            "transforms origin() Point\n"
            "from\n"
            "    Point(0, 0)\n"
        )
        result = check_and_format(source)
        assert "type Point is" in result

    def test_removes_unused_keeps_used(self):
        source = (
            "module M\n"
            "  type Unused is\n"
            "    x Integer\n"
            "\n"
            "  type Used is\n"
            "    y Integer\n"
            "\n"
            "transforms f() Used\n"
            "from\n"
            "    Used(0)\n"
        )
        result = check_and_format(source)
        assert "Unused" not in result
        assert "type Used is" in result


# ── I314: unknown module — formatter removes ────────────────────────


class TestFixI314:
    """Formatter removes unknown module import lines."""

    def test_removes_unknown_module_import(self):
        source = (
            "module Main\n"
            '  narrative: """test"""\n'
            "  FakeModule transforms fake\n"
            "\n"
            "transforms f() Integer\n"
            "from\n"
            "    1\n"
        )
        result = check_and_format(source)
        assert "FakeModule" not in result
        assert "fake" not in result

    def test_keeps_known_module_import(self):
        source = (
            "module Main\n"
            '  narrative: """test"""\n'
            "  Text transforms upper\n"
            "\n"
            "transforms shout(s String) String\n"
            "from\n"
            "    Text.upper(s)\n"
        )
        result = check_and_format(source)
        assert "Text transforms upper" in result

    def test_removes_unknown_keeps_known(self):
        source = (
            "module Main\n"
            '  narrative: """test"""\n'
            "  FakeModule transforms fake\n"
            "  Text transforms upper\n"
            "\n"
            "transforms shout(s String) String\n"
            "from\n"
            "    Text.upper(s)\n"
        )
        result = check_and_format(source)
        assert "FakeModule" not in result
        assert "Text transforms upper" in result


# ── I360: validates Boolean — formatter strips ──────────────────────


class TestFixI360:
    """Formatter strips explicit Boolean return type from validates."""

    def test_strips_boolean_return(self):
        source = (
            "validates is_positive(x Integer) Boolean\n"
            "from\n"
            "    x > 0\n"
        )
        result = check_and_format(source)
        assert "validates is_positive(x Integer)\n" in result
        assert "Boolean" not in result

    def test_preserves_non_validates_return(self):
        source = (
            "transforms double(x Integer) Integer\n"
            "from\n"
            "    x * 2\n"
        )
        result = check_and_format(source)
        assert "Integer" in result


# ── Roundtrip stability ─────────────────────────────────────────────


class TestFixRoundtrip:
    """Formatting twice with auto-fixes produces identical output."""

    def test_roundtrip_i302_partial(self):
        source = (
            "module Main\n"
            "  Text transforms trim upper\n"
            "\n"
            "transforms shout(s String) String\n"
            "from\n"
            "    Text.upper(s)\n"
        )
        first = check_and_format(source)
        second = check_and_format(first)
        assert first == second

    def test_roundtrip_i314(self):
        source = (
            "module Main\n"
            '  narrative: """test"""\n'
            "  FakeModule transforms fake\n"
            "\n"
            "transforms f() Integer\n"
            "from\n"
            "    1\n"
        )
        first = check_and_format(source)
        second = check_and_format(first)
        assert first == second

    def test_roundtrip_i360(self):
        source = (
            "validates is_positive(x Integer) Boolean\n"
            "from\n"
            "    x > 0\n"
        )
        first = check_and_format(source)
        second = check_and_format(first)
        assert first == second

    def test_roundtrip_multiple_fixes(self):
        source = (
            "module M\n"
            "  FakeModule transforms fake\n"
            "  Text transforms trim upper\n"
            "\n"
            "  type Unused is\n"
            "    x Integer\n"
            "\n"
            "  type Color is Red | Green\n"
            "\n"
            "  transforms shout(s String) String\n"
            "  from\n"
            "      Text.upper(s)\n"
        )
        first = check_and_format(source)
        second = check_and_format(first)
        assert first == second


# ── Lookup table formatting ───────────────────────────────────────


class TestFormatLookup:
    """Tests for [Lookup] type and TypeName:expr formatting."""

    def test_lookup_type_roundtrip(self):
        """[Lookup] type definition should format correctly and survive a roundtrip."""
        source = (
            "module M\n"
            "\n"
            "  type TokenKind:[Lookup] is String where\n"
            '      Main | "main"\n'
            '      From | "from"\n'
            '      Type | "type"\n'
            "\n"
            "main()\n"
            "    from\n"
            '        TokenKind:"main"\n'
        )
        first = check_and_format(source)
        assert "type TokenKind:[Lookup] is String where" in first
        assert 'Main | "main"' in first
        second = check_and_format(first)
        assert first == second

    def test_lookup_access_string_roundtrip(self):
        """TokenKind:"main" should format correctly and survive roundtrip."""
        source = (
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
        first = check_and_format(source)
        assert 'TokenKind:"main"' in first
        second = check_and_format(first)
        assert first == second

    def test_lookup_access_variant_roundtrip(self):
        """TokenKind:Main should format correctly and survive roundtrip."""
        source = (
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
        first = check_and_format(source)
        assert "TokenKind:Main" in first
        second = check_and_format(first)
        assert first == second

    def test_lookup_stacking_roundtrip(self):
        """Stacked lookup entries should format with alignment."""
        source = (
            "module M\n"
            "\n"
            "  type BoolLit:[Lookup] is String where\n"
            '      BooleanLit | "true"\n'
            '                 | "false"\n'
            '      Foreign | "foreign"\n'
            "\n"
            "main()\n"
            "    from\n"
            '        BoolLit:"true"\n'
        )
        first = check_and_format(source)
        assert 'BooleanLit | "true"' in first
        assert 'Foreign | "foreign"' in first
        second = check_and_format(first)
        assert first == second
