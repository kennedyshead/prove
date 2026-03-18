"""Tests for store_binary PDAT reader/writer."""

from __future__ import annotations

import struct

import pytest

from prove.store_binary import (
    PDAT_MAGIC,
    PDAT_VERSION,
    pdat_to_prv,
    prv_to_pdat,
    read_pdat,
    write_pdat,
)


class TestWriteReadRoundtrip:
    """Test write_pdat / read_pdat roundtrip."""

    def test_simple_roundtrip(self, tmp_path):
        """Write and read back a two-column table."""
        path = tmp_path / "test.dat"
        columns = ["String", "Integer"]
        variants = [
            ("First", ["hello", "1"]),
            ("Second", ["world", "2"]),
        ]
        write_pdat(path, "Test", columns, variants, version=42)

        result = read_pdat(path)
        assert result["name"] == "test"
        assert result["version"] == 42
        assert result["columns"] == ["String", "Integer"]
        assert result["variants"] == [
            ("First", ["hello", "1"]),
            ("Second", ["world", "2"]),
        ]

    def test_single_column(self, tmp_path):
        """Roundtrip with a single column."""
        path = tmp_path / "single.dat"
        columns = ["String"]
        variants = [("Alpha", ["a"]), ("Beta", ["b"])]
        write_pdat(path, "Single", columns, variants)

        result = read_pdat(path)
        assert result["columns"] == ["String"]
        assert result["variants"] == [("Alpha", ["a"]), ("Beta", ["b"])]
        assert result["version"] == 0

    def test_three_columns(self, tmp_path):
        """Roundtrip with three columns."""
        path = tmp_path / "triple.dat"
        columns = ["String", "Integer", "Decimal"]
        variants = [
            ("X", ["foo", "10", "1.5"]),
            ("Y", ["bar", "20", "2.5"]),
        ]
        write_pdat(path, "Triple", columns, variants, version=7)

        result = read_pdat(path)
        assert result["columns"] == columns
        assert result["variants"] == variants
        assert result["version"] == 7

    def test_empty_variants(self, tmp_path):
        """Roundtrip with no variants."""
        path = tmp_path / "empty.dat"
        write_pdat(path, "Empty", ["String"], [])

        result = read_pdat(path)
        assert result["variants"] == []

    def test_unicode_values(self, tmp_path):
        """Roundtrip with unicode strings."""
        path = tmp_path / "unicode.dat"
        variants = [("Greet", ["\u00e5\u00e4\u00f6"])]
        write_pdat(path, "Unicode", ["String"], variants)

        result = read_pdat(path)
        assert result["variants"] == [("Greet", ["\u00e5\u00e4\u00f6"])]


class TestReadPdatErrors:
    """Test read_pdat error handling."""

    def test_bad_magic(self, tmp_path):
        """Reject files with wrong magic number."""
        path = tmp_path / "bad.dat"
        path.write_bytes(struct.pack("<I", 0xDEADBEEF))
        with pytest.raises(ValueError, match="Not a PDAT file"):
            read_pdat(path)

    def test_bad_version(self, tmp_path):
        """Reject files with unsupported version."""
        path = tmp_path / "badver.dat"
        path.write_bytes(struct.pack("<II", PDAT_MAGIC, 99))
        with pytest.raises(ValueError, match="Unsupported PDAT version"):
            read_pdat(path)


class TestPdatFormat:
    """Test the binary format matches prove_store.c expectations."""

    def test_magic_bytes(self, tmp_path):
        """Verify magic is 0x50444154 little-endian."""
        path = tmp_path / "magic.dat"
        write_pdat(path, "T", ["String"], [("A", ["x"])])
        data = path.read_bytes()
        (magic,) = struct.unpack_from("<I", data, 0)
        assert magic == PDAT_MAGIC

    def test_format_version(self, tmp_path):
        """Verify format version is 1."""
        path = tmp_path / "ver.dat"
        write_pdat(path, "T", ["String"], [("A", ["x"])])
        data = path.read_bytes()
        (ver,) = struct.unpack_from("<I", data, 4)
        assert ver == PDAT_VERSION


class TestPrvToPdat:
    """Test prv_to_pdat conversion."""

    def test_binary_lookup(self, tmp_path):
        """Convert a .prv with binary lookup to PDAT."""
        prv = tmp_path / "test.prv"
        prv.write_text(
            "module M\n"
            "\n"
            "  type Color:[Lookup] is String Integer where\n"
            '    Red | "red" | 1\n'
            '    Green | "green" | 2\n'
            '    Blue | "blue" | 3\n'
            "\n"
            "main()\n"
            "    from\n"
            "        0\n"
        )
        out = prv_to_pdat(prv)
        assert out.name == "Color.dat"
        assert out.exists()

        result = read_pdat(out)
        assert result["columns"] == ["String", "Integer"]
        assert len(result["variants"]) == 3
        assert result["variants"][0] == ("Red", ["red", "1"])
        assert result["variants"][1] == ("Green", ["green", "2"])
        assert result["variants"][2] == ("Blue", ["blue", "3"])

    def test_custom_output_path(self, tmp_path):
        """prv_to_pdat respects custom output path."""
        prv = tmp_path / "test.prv"
        prv.write_text(
            "module M\n"
            "\n"
            "  type T:[Lookup] is String Integer where\n"
            '    A | "a" | 1\n'
            "\n"
            "main()\n"
            "    from\n"
            "        0\n"
        )
        custom = tmp_path / "custom.dat"
        out = prv_to_pdat(prv, custom)
        assert out == custom
        assert custom.exists()

    def test_no_binary_lookup_raises(self, tmp_path):
        """prv_to_pdat raises if no binary lookup found."""
        prv = tmp_path / "nolookup.prv"
        prv.write_text(
            "module M\n"
            "\n"
            "  type Color:[Lookup] is String where\n"
            '    Red | "red"\n'
            '    Blue | "blue"\n'
            "\n"
            "main()\n"
            "    from\n"
            "        0\n"
        )
        with pytest.raises(ValueError, match="No binary"):
            prv_to_pdat(prv)


class TestPdatToPrv:
    """Test pdat_to_prv conversion."""

    def test_generates_prv_source(self, tmp_path):
        """Generate .prv source from a PDAT binary."""
        path = tmp_path / "Color.dat"
        write_pdat(
            path,
            "Color",
            ["String", "Integer"],
            [
                ("Red", ["red", "1"]),
                ("Blue", ["blue", "2"]),
            ],
        )

        source = pdat_to_prv(path)
        assert "module Color" in source
        assert "  type Color:[Lookup] is String Integer where" in source
        assert '    Red | "red" | 1' in source
        assert '    Blue | "blue" | 2' in source

    def test_writes_to_output_file(self, tmp_path):
        """pdat_to_prv writes to file when output is given."""
        dat = tmp_path / "T.dat"
        write_pdat(dat, "T", ["String"], [("A", ["hello"])])

        out = tmp_path / "out.prv"
        pdat_to_prv(dat, out)
        assert out.exists()
        content = out.read_text()
        assert "module T" in content
        assert "  type T:[Lookup] is String where" in content

    def test_roundtrip_prv_to_pdat_to_prv(self, tmp_path):
        """Full roundtrip: .prv -> PDAT -> .prv preserves data."""
        prv = tmp_path / "test.prv"
        prv.write_text(
            "module M\n"
            "\n"
            "  type Status:[Lookup] is String Integer where\n"
            '    Active | "active" | 1\n'
            '    Inactive | "inactive" | 0\n'
            "\n"
            "main()\n"
            "    from\n"
            "        0\n"
        )

        dat = prv_to_pdat(prv)
        source = pdat_to_prv(dat)

        assert "module Status" in source
        assert "  type Status:[Lookup] is String Integer where" in source
        assert '    Active | "active" | 1' in source
        assert '    Inactive | "inactive" | 0' in source
