"""Prove Type -> ASM type mapping and struct layout computation."""

from __future__ import annotations

from dataclasses import dataclass

from prove.types import (
    AlgebraicType,
    ErrorType,
    FunctionType,
    GenericInstance,
    ListType,
    PrimitiveType,
    RecordType,
    RefinementType,
    Type,
    TypeVariable,
    UnitType,
    VariantInfo,
)


@dataclass(frozen=True)
class AsmType:
    """ASM type information."""

    size: int  # size in bytes
    alignment: int  # alignment in bytes
    is_pointer: bool  # whether this is a pointer type


def map_type_asm(ty: Type) -> AsmType:
    """Map a Prove type to its ASM representation (size, alignment, pointer)."""
    if isinstance(ty, PrimitiveType):
        name = ty.name
        if name == "Integer":
            # Check modifiers for size
            for m in ty.modifiers:
                if m.isdigit():
                    bits = int(m)
                    size = bits // 8
                    return AsmType(size, size, False)
            return AsmType(8, 8, False)  # int64_t
        if name in ("Decimal", "Float"):
            for m in ty.modifiers:
                if m == "32":
                    return AsmType(4, 4, False)
            return AsmType(8, 8, False)  # double
        if name == "Boolean":
            return AsmType(1, 1, False)
        if name == "Character":
            return AsmType(1, 1, False)
        if name == "Byte":
            return AsmType(1, 1, False)
        if name == "String":
            return AsmType(8, 8, True)  # pointer
        if name == "Error":
            return AsmType(8, 8, True)
        return AsmType(8, 8, False)

    if isinstance(ty, UnitType):
        return AsmType(0, 1, False)

    if isinstance(ty, RecordType):
        return _struct_layout_info(ty)

    if isinstance(ty, AlgebraicType):
        # Tagged union: tag byte + max variant size
        max_size = 0
        for v in ty.variants:
            v_size = sum(map_type_asm(ft).size for ft in v.fields.values())
            max_size = max(max_size, v_size)
        total = 8 + max_size  # tag (padded to 8) + payload
        return AsmType(total, 8, False)

    if isinstance(ty, RefinementType):
        return map_type_asm(ty.base) if ty.base else AsmType(8, 8, False)

    if isinstance(ty, ListType):
        return AsmType(8, 8, True)  # pointer

    if isinstance(ty, GenericInstance):
        return AsmType(8, 8, False)  # opaque

    if isinstance(ty, FunctionType):
        return AsmType(8, 8, True)  # function pointer

    if isinstance(ty, TypeVariable):
        return AsmType(8, 8, True)  # generic → pointer

    if isinstance(ty, (VariantInfo, ErrorType)):
        return AsmType(8, 8, False)

    return AsmType(8, 8, False)


@dataclass(frozen=True)
class FieldLayout:
    """Layout of a single field in a struct."""

    name: str
    offset: int
    size: int
    alignment: int


def struct_layout(ty: RecordType) -> list[FieldLayout]:
    """Compute the layout of a record type's fields with proper alignment."""
    fields: list[FieldLayout] = []
    offset = 0
    for name, field_type in ty.fields.items():
        asm_ty = map_type_asm(field_type)
        # Align offset
        if asm_ty.alignment > 0:
            offset = (offset + asm_ty.alignment - 1) & ~(asm_ty.alignment - 1)
        fields.append(FieldLayout(name, offset, asm_ty.size, asm_ty.alignment))
        offset += asm_ty.size
    return fields


def _struct_layout_info(ty: RecordType) -> AsmType:
    """Compute total size and alignment for a record type."""
    fields = struct_layout(ty)
    if not fields:
        return AsmType(0, 1, False)
    total_size = fields[-1].offset + fields[-1].size
    max_align = max(f.alignment for f in fields) if fields else 1
    # Pad to alignment
    total_size = (total_size + max_align - 1) & ~(max_align - 1)
    return AsmType(total_size, max_align, False)
