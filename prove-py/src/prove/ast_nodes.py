"""AST node definitions for the Prove language."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Union

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
    modifiers: list[TypeModifier] = field(default_factory=list)


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
    kind: str = "integer"  # "integer", "decimal", "string", "boolean", "path"


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
class FloatLit:
    value: str
    span: Span


@dataclass(frozen=True)
class StringLit:
    value: str
    span: Span


# noqa: E501
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
class RawStringLit:
    value: str
    span: Span


@dataclass(frozen=True)
class PathLit:
    value: str
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
class AsyncCallExpr:
    """Async call: expr& — desugars to passing caller's coro context."""

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


@dataclass(frozen=True)
class LookupExpr:
    """Compile-time lookup: $"main" or $Main (legacy, kept for compat)."""

    operand: Expr  # the literal or variant being looked up
    resolved_value: object | None  # filled in by checker: Expr or None
    span: Span


@dataclass(frozen=True)
class LookupAccessExpr:
    """Compile-time lookup: TokenKind:"main" or TokenKind:Main."""

    type_name: str  # "TokenKind"
    operand: Expr  # the literal or variant being looked up
    span: Span


@dataclass(frozen=True)
class BinaryLookupExpr:
    """Runtime binary lookup: TypeName:variable."""

    type_name: str  # "TokenKind"
    operand: Expr  # the variable being used as key
    column_type: str  # resolved return column type name
    key_type: str  # resolved key type name ("variant", "String", etc.)
    span: Span


@dataclass(frozen=True)
class StoreLookupExpr:
    """Runtime store-backed lookup: variable:"key"."""

    table_var: str  # "colors"
    operand: Expr  # StringLit("red"), IntegerLit, IdentifierExpr
    span: Span


Expr = Union[
    IntegerLit,
    DecimalLit,
    StringLit,
    BooleanLit,
    CharLit,
    RegexLit,
    RawStringLit,
    PathLit,
    TripleStringLit,
    StringInterp,
    ListLiteral,
    IdentifierExpr,
    TypeIdentifierExpr,
    BinaryExpr,
    UnaryExpr,
    CallExpr,
    FieldExpr,
    PipeExpr,
    FailPropExpr,
    AsyncCallExpr,
    LambdaExpr,
    ValidExpr,
    MatchExpr,
    ComptimeExpr,
    IndexExpr,
    LookupExpr,
    LookupAccessExpr,
    BinaryLookupExpr,
    StoreLookupExpr,
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
class FieldAssignment:
    target: Expr
    field: str
    value: Expr
    span: Span


@dataclass(frozen=True)
class ExprStmt:
    expr: Expr
    span: Span


@dataclass(frozen=True)
class TailLoop:
    params: list[str]
    body: list[Any]  # list[Stmt | MatchExpr] — uses Any to avoid cycle
    span: Span


@dataclass(frozen=True)
class TailContinue:
    assignments: list[tuple[str, Expr]]
    span: Span


@dataclass(frozen=True)
class WhileLoop:
    """Finite while loop inlined from a TCO'd function call. Exits when break_cond is True."""

    break_cond: Any  # Expr
    body: list[Any]  # list[Stmt]
    span: Span


@dataclass(frozen=True)
class CommentStmt:
    text: str
    span: Span


@dataclass(frozen=True)
class TodoStmt:
    message: str | None  # optional: todo "implement credential check"
    span: Span


Stmt = Union[
    VarDecl,
    Assignment,
    FieldAssignment,
    ExprStmt,
    TailLoop,
    TailContinue,
    WhileLoop,
    CommentStmt,
    TodoStmt,
]  # noqa: E501


# ── Function parts ───────────────────────────────────────────────


@dataclass(frozen=True)
class Param:
    name: str
    type_expr: TypeExpr
    constraint: Expr | None  # optional `where` constraint
    span: Span


@dataclass(frozen=True)
class ExplainEntry:
    name: str | None  # None for prose-only entries
    text: str
    condition: Expr | None  # parsed "when <expr>", None if absent
    span: Span


@dataclass(frozen=True)
class ExplainBlock:
    entries: list[ExplainEntry]
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


@dataclass(frozen=True)
class BinaryDef:
    span: Span


@dataclass(frozen=True)
class LookupTypeDef:
    """Type body for [Lookup] types: algebraic + bidirectional mapping."""

    value_type: TypeExpr  # String, Integer, or Boolean (legacy single-column)
    entries: list[LookupEntry]  # variant | value rows
    span: Span
    value_types: tuple[TypeExpr, ...] = ()  # Multi-column types (binary)
    column_names: tuple[str | None, ...] = ()  # Parallel to value_types; None = unnamed
    is_binary: bool = False
    csv_path: str | None = None
    is_store_backed: bool = False
    is_pipe_entry_format: bool = False
    is_dispatch: bool = False


TypeBody = Union[RefinementTypeDef, AlgebraicTypeDef, RecordTypeDef, BinaryDef, LookupTypeDef]


# ── Top-level declarations ───────────────────────────────────────


@dataclass(frozen=True)
class WithConstraint:
    """Row-polymorphism field constraint: ``with param.field Type``."""

    param_name: str
    field_name: str
    field_type: TypeExpr
    span: Span


@dataclass(frozen=True)
class FunctionDef:
    verb: str
    name: str
    params: list[Param]
    return_type: TypeExpr | None
    can_fail: bool
    ensures: list[Expr]
    requires: list[Expr]
    explain: ExplainBlock | None
    terminates: Expr | None
    trusted: str | None
    binary: bool
    why_not: list[str]
    chosen: str | None
    near_misses: list[NearMiss]
    know: list[Expr]
    assume: list[Expr]
    believe: list[Expr]
    with_constraints: list[WithConstraint]
    intent: str | None
    satisfies: list[str]
    event_type: TypeExpr | None
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
    modifiers: list[TypeModifier]
    body: TypeBody
    span: Span
    doc_comment: str | None = None


@dataclass(frozen=True)
class ConstantDef:
    name: str
    type_expr: TypeExpr | None
    value: Expr
    span: Span
    doc_comment: str | None = None


@dataclass(frozen=True)
class ImportDecl:
    module: str
    items: list[ImportItem]
    span: Span
    local: bool = False  # True when prefixed with `.` to force local module resolution


@dataclass(frozen=True)
class ForeignFunction:
    name: str  # actual C function name (e.g. "sqrt")
    params: list[Param]
    return_type: TypeExpr | None
    span: Span


@dataclass(frozen=True)
class ForeignBlock:
    library: str  # e.g. "libm"
    functions: list[ForeignFunction]
    span: Span


@dataclass(frozen=True)
class LookupEntry:
    """One row in a lookup table: Variant | value."""

    variant: str  # variant name (Main)
    value: str  # literal value ("main") — first column for binary
    value_kind: str  # "string", "integer", "boolean" — first column kind
    span: Span
    values: tuple[str, ...] = ()  # Multi-column values (binary)
    value_kinds: tuple[str, ...] = ()  # Multi-column value kinds (binary)


@dataclass(frozen=True)
class ModuleDecl:
    name: str
    narrative: str | None
    domain: str | None  # domain tag (e.g. "Finance")
    temporal: list[str] | None  # list of ordered step names
    imports: list[ImportDecl]
    types: list[TypeDef]
    constants: list[ConstantDef]
    invariants: list[InvariantNetwork]
    foreign_blocks: list[ForeignBlock]
    body: list[Declaration]
    span: Span


@dataclass(frozen=True)
class InvariantNetwork:
    name: str
    constraints: list[Expr]
    span: Span


@dataclass(frozen=True)
class CommentDecl:
    text: str
    span: Span


Declaration = Union[FunctionDef, MainDef, ModuleDecl, CommentDecl]


@dataclass(frozen=True)
class Module:
    declarations: list[Declaration]
    span: Span
