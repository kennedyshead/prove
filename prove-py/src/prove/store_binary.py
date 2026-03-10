"""PDAT binary format reader/writer for Prove lookup tables.

Implements the binary serialization format documented in prove_store.c,
enabling offline compilation and inspection of :[Lookup] type definitions.

Format (all little-endian):
  [4] magic 0x50444154 ("PDAT")
  [4] format version (1)
  [8] data version (int64)
  [8] column_count
  Per column: [4] name_len + [N] name bytes
  [8] variant_count
  Per variant: [4] name_len + [N] name bytes + per column: [4] val_len + [N] val bytes
"""

from __future__ import annotations

import struct
from pathlib import Path

from prove.ast_nodes import LookupTypeDef, ModuleDecl, TypeDef
from prove.errors import CompileError
from prove.lexer import Lexer
from prove.parser import Parser

PDAT_MAGIC = 0x50444154
PDAT_VERSION = 1


def write_pdat(
    path: str | Path,
    name: str,
    columns: list[str],
    variants: list[tuple[str, list[str]]],
    version: int = 0,
) -> None:
    """Write a PDAT binary file.

    Args:
        path: Output file path.
        name: Table name (unused in format but reserved for metadata).
        columns: Column type names (e.g. ["String", "Integer"]).
        variants: List of (variant_name, [col_values...]) tuples.
        version: Data version number.
    """
    with open(path, "wb") as f:
        f.write(struct.pack("<I", PDAT_MAGIC))
        f.write(struct.pack("<I", PDAT_VERSION))
        f.write(struct.pack("<q", version))
        f.write(struct.pack("<q", len(columns)))
        for col in columns:
            col_bytes = col.encode("utf-8")
            f.write(struct.pack("<I", len(col_bytes)))
            f.write(col_bytes)
        f.write(struct.pack("<q", len(variants)))
        for variant_name, values in variants:
            vn_bytes = variant_name.encode("utf-8")
            f.write(struct.pack("<I", len(vn_bytes)))
            f.write(vn_bytes)
            for val in values:
                val_bytes = val.encode("utf-8")
                f.write(struct.pack("<I", len(val_bytes)))
                f.write(val_bytes)


def read_pdat(path: str | Path) -> dict:
    """Read a PDAT binary file.

    Returns:
        Dict with keys: name (str, from filename), version (int),
        columns (list[str]), variants (list[tuple[str, list[str]]]).
    """
    with open(path, "rb") as f:
        data = f.read()

    off = 0

    def u32() -> int:
        nonlocal off
        (v,) = struct.unpack_from("<I", data, off)
        off += 4
        return v

    def i64() -> int:
        nonlocal off
        (v,) = struct.unpack_from("<q", data, off)
        off += 8
        return v

    def read_str() -> str:
        length = u32()
        nonlocal off
        s = data[off : off + length].decode("utf-8")
        off += length
        return s

    magic = u32()
    if magic != PDAT_MAGIC:
        msg = f"Not a PDAT file (magic: 0x{magic:08X})"
        raise ValueError(msg)

    fmt_version = u32()
    if fmt_version != PDAT_VERSION:
        msg = f"Unsupported PDAT version: {fmt_version}"
        raise ValueError(msg)

    data_version = i64()
    column_count = i64()
    columns = [read_str() for _ in range(column_count)]

    variant_count = i64()
    variants: list[tuple[str, list[str]]] = []
    for _ in range(variant_count):
        vname = read_str()
        values = [read_str() for _ in range(column_count)]
        variants.append((vname, values))

    name = Path(path).stem
    return {
        "name": name,
        "version": data_version,
        "columns": columns,
        "variants": variants,
    }


def _type_name(te: object) -> str:
    """Extract the simple name from a TypeExpr."""
    from prove.ast_nodes import GenericType, ModifiedType, SimpleType

    if isinstance(te, SimpleType):
        return te.name
    if isinstance(te, GenericType):
        return te.name
    if isinstance(te, ModifiedType):
        return _type_name(te.base)
    return str(te)


def prv_to_pdat(prv_path: str | Path, output_path: str | Path | None = None) -> Path:
    """Parse a .prv file and write each :[Lookup] type as a PDAT binary.

    Args:
        prv_path: Path to the .prv source file.
        output_path: Output .dat path. If None, derived from type name.

    Returns:
        Path to the written .dat file.

    Raises:
        CompileError: If parsing fails.
        ValueError: If no binary lookup type is found.
    """
    prv_path = Path(prv_path)
    source = prv_path.read_text()
    tokens = Lexer(source, str(prv_path)).lex()
    module = Parser(tokens, str(prv_path)).parse()

    for decl in module.declarations:
        if not isinstance(decl, ModuleDecl):
            continue
        for td in decl.types:
            if not isinstance(td, TypeDef):
                continue
            if not isinstance(td.body, LookupTypeDef):
                continue
            if not td.body.is_binary:
                continue

            columns = [_type_name(vt) for vt in td.body.value_types]
            variants: list[tuple[str, list[str]]] = []
            for entry in td.body.entries:
                if entry.values:
                    variants.append((entry.variant, list(entry.values)))
                else:
                    variants.append((entry.variant, [entry.value]))

            out = Path(output_path) if output_path else prv_path.parent / f"{td.name}.dat"
            write_pdat(out, td.name, columns, variants)
            return out

    msg = f"No binary :[Lookup] type found in {prv_path}"
    raise ValueError(msg)


def pdat_to_prv(bin_path: str | Path, output: str | Path | None = None) -> str:
    """Read a PDAT binary and generate .prv source text.

    Args:
        bin_path: Path to the .dat binary file.
        output: If provided, write source to this file path.

    Returns:
        The generated .prv source text.
    """
    info = read_pdat(bin_path)
    name = info["name"]
    # Capitalize the table name for the type name
    type_name = name[0].upper() + name[1:] if name else "Table"
    columns = info["columns"]
    variants = info["variants"]

    col_types = " ".join(columns)
    lines = [
        f"module {type_name}",
        "",
        f"  type {type_name}:[Lookup] is {col_types} where",
    ]
    for variant_name, values in variants:
        formatted_vals = []
        for val in values:
            # Try to detect if value is numeric
            try:
                int(val)
                formatted_vals.append(val)
            except ValueError:
                try:
                    float(val)
                    formatted_vals.append(val)
                except ValueError:
                    formatted_vals.append(f'"{val}"')
        lines.append(f"    {variant_name} | {' | '.join(formatted_vals)}")

    source = "\n".join(lines) + "\n"

    if output:
        Path(output).write_text(source)

    return source
