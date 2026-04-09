"""Compact binary serialization for Prove AST modules.

Serializes/deserializes Module AST to tagged-tuple binary format with
string interning.  Used by the package manager to store pre-checked AST
in .prvpkg (SQLite) files.

Format:
  - Each node starts with a uint8 tag identifying the concrete type.
  - Strings are interned: stored once in a StringIntern table, referenced by uint32 ID.
  - Lists: uint32 count followed by elements.
  - None/absent: TAG_NONE (0xFF).
  - Bools: uint8 (0/1).
  - Integers encoded as interned strings (since Prove integers are arbitrary-precision).
"""

from __future__ import annotations

import struct
from dataclasses import fields as dc_fields
from typing import Any, get_origin

from prove.ast_nodes import (
    AlgebraicTypeDef,
    Assignment,
    AsyncCallExpr,
    BinaryDef,
    BinaryExpr,
    BinaryLookupExpr,
    BindingPattern,
    BooleanLit,
    CallExpr,
    CharLit,
    CommentDecl,
    CommentStmt,
    ComptimeExpr,
    ConstantDef,
    DecimalLit,
    ExplainBlock,
    ExplainEntry,
    ExprStmt,
    FailPropExpr,
    FieldAssignment,
    FieldDef,
    FieldExpr,
    FloatLit,
    ForeignBlock,
    ForeignFunction,
    FunctionDef,
    GenericType,
    IdentifierExpr,
    ImportDecl,
    ImportItem,
    IndexExpr,
    IntegerLit,
    InvariantNetwork,
    LambdaExpr,
    ListLiteral,
    LiteralPattern,
    LookupAccessExpr,
    LookupEntry,
    LookupExpr,
    LookupPattern,
    LookupTypeDef,
    MainDef,
    MatchArm,
    MatchExpr,
    ModifiedType,
    Module,
    ModuleDecl,
    NearMiss,
    Param,
    PathLit,
    PipeExpr,
    RawStringLit,
    RecordTypeDef,
    RefinementTypeDef,
    RegexLit,
    SimpleType,
    StoreLookupExpr,
    StringInterp,
    StringLit,
    TailContinue,
    TailLoop,
    TodoStmt,
    TripleStringLit,
    TypeDef,
    TypeIdentifierExpr,
    TypeModifier,
    UnaryExpr,
    ValidExpr,
    VarDecl,
    Variant,
    VariantPattern,
    WhileLoop,
    WildcardPattern,
    WithConstraint,
)
from prove.source import Span

# ── String interning ─────────────────────────────────────────────

_DUMMY_SPAN = Span("<package>", 0, 0, 0, 0)


class StringIntern:
    """Bidirectional string ↔ uint32 ID table."""

    def __init__(self) -> None:
        self._to_id: dict[str, int] = {}
        self._to_str: list[str] = []

    def intern(self, s: str) -> int:
        """Return the ID for *s*, adding it if new."""
        idx = self._to_id.get(s)
        if idx is not None:
            return idx
        idx = len(self._to_str)
        self._to_id[s] = idx
        self._to_str.append(s)
        return idx

    def get_str(self, idx: int) -> str:
        return self._to_str[idx]

    def size(self) -> int:
        return len(self._to_str)

    def all_strings(self) -> list[str]:
        return list(self._to_str)

    @classmethod
    def from_list(cls, strings: list[str]) -> StringIntern:
        si = cls()
        for s in strings:
            si.intern(s)
        return si


# ── Tag map ──────────────────────────────────────────────────────

TAG_NONE: int = 0xFF

# Concrete AST node types → tag IDs (must be stable across versions)
_CONCRETE_TYPES: list[type] = [
    # Type expressions (1-3)
    SimpleType,  # 1
    GenericType,  # 2
    TypeModifier,  # 3
    ModifiedType,  # 4
    # Patterns (5-9)
    VariantPattern,  # 5
    WildcardPattern,  # 6
    LiteralPattern,  # 7
    BindingPattern,  # 8
    LookupPattern,  # 9
    # Literals (10-19)
    IntegerLit,  # 10
    DecimalLit,  # 11
    FloatLit,  # 12
    StringLit,  # 13
    BooleanLit,  # 14
    CharLit,  # 15
    RegexLit,  # 16
    RawStringLit,  # 17
    PathLit,  # 18
    TripleStringLit,  # 19
    # Complex exprs (20-39)
    StringInterp,  # 20
    ListLiteral,  # 21
    IdentifierExpr,  # 22
    TypeIdentifierExpr,  # 23
    BinaryExpr,  # 24
    UnaryExpr,  # 25
    CallExpr,  # 26
    FieldExpr,  # 27
    PipeExpr,  # 28
    FailPropExpr,  # 29
    AsyncCallExpr,  # 30
    LambdaExpr,  # 31
    ValidExpr,  # 32
    MatchArm,  # 33
    MatchExpr,  # 34
    ComptimeExpr,  # 35
    IndexExpr,  # 36
    LookupExpr,  # 37
    LookupAccessExpr,  # 38
    BinaryLookupExpr,  # 39
    StoreLookupExpr,  # 40
    # Statements (41-49)
    VarDecl,  # 41
    Assignment,  # 42
    FieldAssignment,  # 43
    ExprStmt,  # 44
    TailLoop,  # 45
    TailContinue,  # 46
    WhileLoop,  # 47
    CommentStmt,  # 48
    TodoStmt,  # 49
    # Function parts (50-54)
    Param,  # 50
    ExplainEntry,  # 51
    ExplainBlock,  # 52
    NearMiss,  # 53
    ImportItem,  # 54
    # Type defs (55-61)
    FieldDef,  # 55
    Variant,  # 56
    RefinementTypeDef,  # 57
    AlgebraicTypeDef,  # 58
    RecordTypeDef,  # 59
    BinaryDef,  # 60
    LookupTypeDef,  # 61
    # Top-level (62-72)
    WithConstraint,  # 62
    FunctionDef,  # 63
    MainDef,  # 64
    TypeDef,  # 65
    ConstantDef,  # 66
    ImportDecl,  # 67
    ForeignFunction,  # 68
    ForeignBlock,  # 69
    LookupEntry,  # 70
    ModuleDecl,  # 71
    InvariantNetwork,  # 72
    CommentDecl,  # 73
    Module,  # 74
]

_TAG_MAP: dict[type, int] = {cls: i + 1 for i, cls in enumerate(_CONCRETE_TYPES)}
_TAG_TO_TYPE: dict[int, type] = {i + 1: cls for i, cls in enumerate(_CONCRETE_TYPES)}

# Fields to skip during serialization
_SKIP_FIELDS = frozenset({"span", "parse_diagnostics"})


# ── Serializer ───────────────────────────────────────────────────


class _Serializer:
    """Walks a Module AST and produces compact binary bytes."""

    def __init__(self) -> None:
        self.strings = StringIntern()
        self._buf = bytearray()

    def _write_u8(self, v: int) -> None:
        self._buf.append(v & 0xFF)

    def _write_u32(self, v: int) -> None:
        self._buf.extend(struct.pack("<I", v))

    def _write_i64(self, v: int) -> None:
        self._buf.extend(struct.pack("<q", v))

    def _write_str(self, s: str) -> None:
        self._write_u32(self.strings.intern(s))

    def _write_bool(self, v: bool) -> None:
        self._write_u8(1 if v else 0)

    def _write_none(self) -> None:
        self._write_u8(TAG_NONE)

    def serialize(self, node: object) -> None:
        if node is None:
            self._write_none()
            return

        if isinstance(node, bool):
            self._write_u8(0xFE)  # bool marker
            self._write_bool(node)
            return

        if isinstance(node, str):
            self._write_u8(0xFD)  # string marker
            self._write_str(node)
            return

        if isinstance(node, int):
            self._write_u8(0xFC)  # int marker
            self._write_i64(node)
            return

        if isinstance(node, (list, tuple)):
            self._write_u8(0xFB)  # list marker
            self._write_u32(len(node))
            for item in node:
                self.serialize(item)
            return

        if isinstance(node, frozenset):
            self._write_u8(0xFB)  # treat as list
            items = sorted(node)
            self._write_u32(len(items))
            for item in items:
                self.serialize(item)
            return

        tag = _TAG_MAP.get(type(node))
        if tag is None:
            raise ValueError(f"unknown AST node type: {type(node).__name__}")

        self._write_u8(tag)
        for f in dc_fields(node):
            if f.name in _SKIP_FIELDS:
                continue
            val = getattr(node, f.name)
            self.serialize(val)

    def get_bytes(self) -> bytes:
        return bytes(self._buf)


# ── Deserializer ─────────────────────────────────────────────────


class _Deserializer:
    """Reconstructs Module AST from compact binary bytes."""

    def __init__(self, data: bytes, strings: StringIntern) -> None:
        self._data = data
        self._pos = 0
        self._strings = strings

    def _read_u8(self) -> int:
        v = self._data[self._pos]
        self._pos += 1
        return v

    def _read_u32(self) -> int:
        v = struct.unpack_from("<I", self._data, self._pos)[0]
        self._pos += 4
        return v

    def _read_i64(self) -> int:
        v = struct.unpack_from("<q", self._data, self._pos)[0]
        self._pos += 8
        return v

    def _read_str(self) -> str:
        idx = self._read_u32()
        return self._strings.get_str(idx)

    def deserialize(self) -> Any:
        tag = self._read_u8()

        if tag == TAG_NONE:
            return None

        if tag == 0xFE:  # bool
            return self._read_u8() != 0

        if tag == 0xFD:  # string
            return self._read_str()

        if tag == 0xFC:  # int
            return self._read_i64()

        if tag == 0xFB:  # list
            count = self._read_u32()
            return [self.deserialize() for _ in range(count)]

        node_type = _TAG_TO_TYPE.get(tag)
        if node_type is None:
            raise ValueError(f"unknown tag: {tag}")

        kwargs: dict[str, Any] = {}
        for f in dc_fields(node_type):
            if f.name in _SKIP_FIELDS:
                if f.name == "span":
                    kwargs["span"] = _DUMMY_SPAN
                elif f.name == "parse_diagnostics":
                    kwargs["parse_diagnostics"] = ()
                continue
            val = self.deserialize()
            # Convert lists to tuples for tuple-typed fields
            if isinstance(val, list) and _field_wants_tuple(node_type, f.name):
                val = tuple(val)
            # Convert lists to frozensets for frozenset-typed fields
            if isinstance(val, list) and _field_wants_frozenset(node_type, f.name):
                val = frozenset(val)
            kwargs[f.name] = val

        return node_type(**kwargs)


def _field_wants_tuple(cls: type, field_name: str) -> bool:
    """Check if a dataclass field is annotated as tuple."""
    for f in dc_fields(cls):
        if f.name == field_name:
            hint = f.type
            if isinstance(hint, str):
                # Evaluate string annotation in the module's namespace
                import prove.ast_nodes as _mod

                try:
                    hint = eval(hint, vars(_mod))
                except Exception:
                    return False
            origin = get_origin(hint)
            return origin is tuple
    return False


def _field_wants_frozenset(cls: type, field_name: str) -> bool:
    """Check if a dataclass field is annotated as frozenset."""
    for f in dc_fields(cls):
        if f.name == field_name:
            hint = f.type
            if isinstance(hint, str):
                import prove.ast_nodes as _mod

                try:
                    hint = eval(hint, vars(_mod))
                except Exception:
                    return False
            origin = get_origin(hint)
            return origin is frozenset
    return False


# ── Public API ───────────────────────────────────────────────────


def serialize_module(module: Module) -> tuple[bytes, StringIntern]:
    """Serialize a Module AST to compact binary + string table.

    Spans are stripped.  Returns (data_bytes, string_intern_table).
    """
    ser = _Serializer()
    ser.serialize(module)
    return ser.get_bytes(), ser.strings


def deserialize_module(data: bytes, strings: StringIntern) -> Module:
    """Reconstruct a Module from binary data + string table.

    All spans are replaced with a dummy ``Span("<package>", 0, 0, 0, 0)``.
    """
    deser = _Deserializer(data, strings)
    result = deser.deserialize()
    if not isinstance(result, Module):
        raise ValueError(f"expected Module, got {type(result).__name__}")
    return result
