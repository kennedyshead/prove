"""AST node definitions for the Prove language."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Union

from prove.source import Span

# ── Type expressions ─────────────────────────────────────────────


@dataclass(frozen=True)
class SimpleType:
    name: str
    span: Span


@dataclass(frozen=True)
class GenericType:
    name: str
    args: list[TypeExpr]
    span: Span


@dataclass(frozen=True)
class TypeModifier:
    name: str | None  # None for positional modifiers
    value: str
    span: Span


@dataclass(frozen=True)
class ModifiedType:
    name: str
    modifiers: list[TypeModifier]
    span: Span


TypeExpr = Union[SimpleType, GenericType, ModifiedType]


# ── Patterns ─────────────────────────────────────────────────────


@dataclass(frozen=True)
class VariantPattern:
    name: str
    fields: list[Pattern]
    span: Span


@dataclass(frozen=True)
class WildcardPattern:
    span: Span


@dataclass(frozen=True)
class LiteralPattern:
    value: str
    span: Span


@dataclass(frozen=True)
class BindingPattern:
    name: str
    span: Span


Pattern = Union[VariantPattern, WildcardPattern, LiteralPattern, BindingPattern]


# ── Expressions ──────────────────────────────────────────────────


@dataclass(frozen=True)
class IntegerLit:
    value: str
    span: Span


@dataclass(frozen=True)
class DecimalLit:
    value: str
    span: Span


@dataclass(frozen=True)
class StringLit:
    value: str
    span: Span


@dataclass(frozen=True)
class BooleanLit:
    value: bool
    span: Span


@dataclass(frozen=True)
class CharLit:
    value: str
    span: Span


@dataclass(frozen=True)
class RegexLit:
    pattern: str
    span: Span


@dataclass(frozen=True)
class TripleStringLit:
    value: str
    span: Span


@dataclass(frozen=True)
class StringInterp:
    parts: list[Expr]  # StringLit and other exprs alternating
    span: Span


@dataclass(frozen=True)
class ListLiteral:
    elements: list[Expr]
    span: Span


@dataclass(frozen=True)
class IdentifierExpr:
    name: str
    span: Span


@dataclass(frozen=True)
class TypeIdentifierExpr:
    name: str
    span: Span


@dataclass(frozen=True)
class BinaryExpr:
    left: Expr
    op: str
    right: Expr
    span: Span


@dataclass(frozen=True)
class UnaryExpr:
    op: str
    operand: Expr
    span: Span


@dataclass(frozen=True)
class CallExpr:
    func: Expr
    args: list[Expr]
    span: Span


@dataclass(frozen=True)
class FieldExpr:
    obj: Expr
    field: str
    span: Span


@dataclass(frozen=True)
class PipeExpr:
    left: Expr
    right: Expr
    span: Span


@dataclass(frozen=True)
class FailPropExpr:
    expr: Expr
    span: Span


@dataclass(frozen=True)
class LambdaExpr:
    params: list[str]
    body: Expr
    span: Span


@dataclass(frozen=True)
class ValidExpr:
    name: str
    args: list[Expr] | None  # None = function reference, list = call
    span: Span


@dataclass(frozen=True)
class IfExpr:
    condition: Expr
    then_body: list[Stmt]
    else_body: list[Stmt]
    span: Span


@dataclass(frozen=True)
class MatchArm:
    pattern: Pattern
    body: list[Stmt]
    span: Span


@dataclass(frozen=True)
class MatchExpr:
    subject: Expr | None  # None for implicit match
    arms: list[MatchArm]
    span: Span


@dataclass(frozen=True)
class ComptimeExpr:
    body: list[Stmt]
    span: Span


@dataclass(frozen=True)
class IndexExpr:
    obj: Expr
    index: Expr
    span: Span


Expr = Union[
    IntegerLit, DecimalLit, StringLit, BooleanLit, CharLit, RegexLit,
    TripleStringLit, StringInterp, ListLiteral,
    IdentifierExpr, TypeIdentifierExpr,
    BinaryExpr, UnaryExpr, CallExpr, FieldExpr, PipeExpr,
    FailPropExpr, LambdaExpr, ValidExpr,
    IfExpr, MatchExpr, ComptimeExpr, IndexExpr,
]


# ── Statements ───────────────────────────────────────────────────


@dataclass(frozen=True)
class VarDecl:
    name: str
    type_expr: TypeExpr | None
    value: Expr
    span: Span


@dataclass(frozen=True)
class Assignment:
    target: str
    value: Expr
    span: Span


@dataclass(frozen=True)
class ExprStmt:
    expr: Expr
    span: Span


Stmt = Union[VarDecl, Assignment, ExprStmt]


# ── Function parts ───────────────────────────────────────────────


@dataclass(frozen=True)
class Param:
    name: str
    type_expr: TypeExpr
    constraint: Expr | None  # optional `where` constraint
    span: Span


@dataclass(frozen=True)
class ProofObligation:
    name: str
    text: str
    span: Span


@dataclass(frozen=True)
class ProofBlock:
    obligations: list[ProofObligation]
    span: Span


@dataclass(frozen=True)
class NearMiss:
    input: Expr
    expected: Expr
    span: Span


@dataclass(frozen=True)
class ImportItem:
    verb: str | None
    name: str
    span: Span


# ── Type definitions ─────────────────────────────────────────────


@dataclass(frozen=True)
class FieldDef:
    name: str
    type_expr: TypeExpr
    constraint: Expr | None  # optional `where` constraint
    span: Span


@dataclass(frozen=True)
class Variant:
    name: str
    fields: list[FieldDef]
    span: Span


@dataclass(frozen=True)
class RefinementTypeDef:
    base_type: TypeExpr
    constraint: Expr
    span: Span


@dataclass(frozen=True)
class AlgebraicTypeDef:
    variants: list[Variant]
    span: Span


@dataclass(frozen=True)
class RecordTypeDef:
    fields: list[FieldDef]
    span: Span


TypeBody = Union[RefinementTypeDef, AlgebraicTypeDef, RecordTypeDef]


# ── Top-level declarations ───────────────────────────────────────


@dataclass(frozen=True)
class FunctionDef:
    verb: str
    name: str
    params: list[Param]
    return_type: TypeExpr | None
    can_fail: bool
    ensures: list[Expr]
    requires: list[Expr]
    proof: ProofBlock | None
    why_not: list[str]
    chosen: str | None
    near_misses: list[NearMiss]
    know: list[Expr]
    assume: list[Expr]
    believe: list[Expr]
    intent: str | None
    satisfies: list[str]
    body: list[Stmt | MatchExpr]
    doc_comment: str | None
    span: Span


@dataclass(frozen=True)
class MainDef:
    return_type: TypeExpr | None
    can_fail: bool
    body: list[Stmt | MatchExpr]
    doc_comment: str | None
    span: Span


@dataclass(frozen=True)
class TypeDef:
    name: str
    type_params: list[str]
    body: TypeBody
    span: Span


@dataclass(frozen=True)
class ConstantDef:
    name: str
    type_expr: TypeExpr | None
    value: Expr
    span: Span


@dataclass(frozen=True)
class ImportDecl:
    module: str
    items: list[ImportItem]
    span: Span


@dataclass(frozen=True)
class ModuleDecl:
    name: str
    narrative: str | None
    temporal: list[str] | None  # list of ordered step names
    body: list[Declaration]
    span: Span


@dataclass(frozen=True)
class InvariantNetwork:
    name: str
    constraints: list[Expr]
    span: Span


Declaration = Union[
    FunctionDef, MainDef, TypeDef, ConstantDef,
    ImportDecl, ModuleDecl, InvariantNetwork,
]


@dataclass(frozen=True)
class Module:
    declarations: list[Declaration]
    span: Span
