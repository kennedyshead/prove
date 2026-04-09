"""Tests for AST serialization roundtrip."""

from typing import get_args

from prove.ast_nodes import (
    AlgebraicTypeDef,
    BinaryExpr,
    BooleanLit,
    ConstantDef,
    ExprStmt,
    FieldDef,
    FunctionDef,
    IdentifierExpr,
    ImportDecl,
    ImportItem,
    IntegerLit,
    LookupEntry,
    LookupTypeDef,
    MatchArm,
    MatchExpr,
    Module,
    ModuleDecl,
    Param,
    RecordTypeDef,
    SimpleType,
    StringLit,
    TypeDef,
    Variant,
    VariantPattern,
    WildcardPattern,
)
from prove.ast_serial import (
    _TAG_MAP,
    StringIntern,
    deserialize_module,
    serialize_module,
)
from prove.source import Span

_S = Span("test.prv", 1, 1, 1, 10)


def _simple_module() -> Module:
    """A minimal module with one function."""
    return Module(
        declarations=[
            ModuleDecl(
                name="Test",
                narrative=None,
                domain=None,
                temporal=None,
                imports=[
                    ImportDecl(
                        module="Math",
                        items=[ImportItem(verb=None, name="sqrt", span=_S)],
                        span=_S,
                    )
                ],
                types=[],
                constants=[],
                invariants=[],
                foreign_blocks=[],
                body=[
                    FunctionDef(
                        verb="creates",
                        name="double",
                        params=[
                            Param(
                                name="x",
                                type_expr=SimpleType("Integer", _S),
                                constraint=None,
                                span=_S,
                            )
                        ],
                        return_type=SimpleType("Integer", _S),
                        can_fail=False,
                        ensures=[],
                        requires=[],
                        explain=None,
                        terminates=None,
                        trusted=None,
                        binary=False,
                        why_not=[],
                        chosen=None,
                        near_misses=[],
                        know=[],
                        assume=[],
                        believe=[],
                        with_constraints=[],
                        intent=None,
                        satisfies=[],
                        event_type=None,
                        state_init=None,
                        state_type=None,
                        body=[
                            ExprStmt(
                                expr=BinaryExpr(
                                    left=IdentifierExpr("x", _S),
                                    op="*",
                                    right=IntegerLit("2", _S),
                                    span=_S,
                                ),
                                span=_S,
                            )
                        ],
                        doc_comment="Doubles a number.",
                        span=_S,
                    ),
                ],
                span=_S,
            )
        ],
        span=_S,
    )


def _complex_module() -> Module:
    """Module with types, match, contracts."""
    return Module(
        declarations=[
            ModuleDecl(
                name="Complex",
                narrative="A complex module.",
                domain="Testing",
                temporal=None,
                imports=[],
                types=[
                    TypeDef(
                        name="Color",
                        type_params=[],
                        modifiers=[],
                        body=AlgebraicTypeDef(
                            variants=[
                                Variant("Red", [], _S),
                                Variant("Green", [], _S),
                                Variant("Blue", [], _S),
                            ],
                            span=_S,
                        ),
                        span=_S,
                        doc_comment="A color type.",
                    ),
                    TypeDef(
                        name="Point",
                        type_params=[],
                        modifiers=[],
                        body=RecordTypeDef(
                            fields=[
                                FieldDef("x", SimpleType("Integer", _S), None, _S),
                                FieldDef("y", SimpleType("Integer", _S), None, _S),
                            ],
                            span=_S,
                        ),
                        span=_S,
                    ),
                ],
                constants=[
                    ConstantDef(
                        name="MAX",
                        type_expr=SimpleType("Integer", _S),
                        value=IntegerLit("100", _S),
                        span=_S,
                    )
                ],
                invariants=[],
                foreign_blocks=[],
                body=[
                    FunctionDef(
                        verb="creates",
                        name="color_name",
                        params=[Param("c", SimpleType("Color", _S), None, _S)],
                        return_type=SimpleType("String", _S),
                        can_fail=False,
                        ensures=[],
                        requires=[
                            BinaryExpr(
                                IdentifierExpr("c", _S), "!=", IdentifierExpr("Blue", _S), _S
                            )
                        ],
                        explain=None,
                        terminates=None,
                        trusted=None,
                        binary=False,
                        why_not=[],
                        chosen=None,
                        near_misses=[],
                        know=[],
                        assume=[],
                        believe=[],
                        with_constraints=[],
                        intent=None,
                        satisfies=[],
                        event_type=None,
                        state_init=None,
                        state_type=None,
                        body=[
                            ExprStmt(
                                expr=MatchExpr(
                                    subject=IdentifierExpr("c", _S),
                                    arms=[
                                        MatchArm(
                                            VariantPattern("Red", [], _S),
                                            [ExprStmt(StringLit("red", _S), _S)],
                                            _S,
                                        ),
                                        MatchArm(
                                            VariantPattern("Green", [], _S),
                                            [ExprStmt(StringLit("green", _S), _S)],
                                            _S,
                                        ),
                                        MatchArm(
                                            WildcardPattern(_S),
                                            [ExprStmt(StringLit("other", _S), _S)],
                                            _S,
                                        ),
                                    ],
                                    span=_S,
                                ),
                                span=_S,
                            )
                        ],
                        doc_comment=None,
                        span=_S,
                    ),
                ],
                span=_S,
            )
        ],
        span=_S,
    )


def test_string_intern_roundtrip():
    si = StringIntern()
    a = si.intern("hello")
    b = si.intern("world")
    c = si.intern("hello")
    assert a == c  # same string -> same ID
    assert a != b
    assert si.get_str(a) == "hello"
    assert si.get_str(b) == "world"
    assert si.size() == 2

    # Reconstruct from list
    si2 = StringIntern.from_list(si.all_strings())
    assert si2.get_str(a) == "hello"
    assert si2.get_str(b) == "world"


def test_simple_module_roundtrip():
    module = _simple_module()
    data, strings = serialize_module(module)
    restored = deserialize_module(data, strings)

    assert isinstance(restored, Module)
    assert len(restored.declarations) == 1
    decl = restored.declarations[0]
    assert isinstance(decl, ModuleDecl)
    assert decl.name == "Test"
    assert len(decl.imports) == 1
    assert decl.imports[0].module == "Math"
    assert len(decl.body) == 1
    func = decl.body[0]
    assert isinstance(func, FunctionDef)
    assert func.verb == "creates"
    assert func.name == "double"
    assert func.doc_comment == "Doubles a number."
    assert len(func.params) == 1
    assert func.params[0].name == "x"
    # Spans should be dummy
    assert func.span.file == "<package>"


def test_complex_module_roundtrip():
    module = _complex_module()
    data, strings = serialize_module(module)
    restored = deserialize_module(data, strings)

    assert isinstance(restored, Module)
    decl = restored.declarations[0]
    assert isinstance(decl, ModuleDecl)
    assert decl.name == "Complex"
    assert decl.narrative == "A complex module."
    assert decl.domain == "Testing"

    # Types
    assert len(decl.types) == 2
    color_def = decl.types[0]
    assert color_def.name == "Color"
    assert isinstance(color_def.body, AlgebraicTypeDef)
    assert len(color_def.body.variants) == 3
    assert color_def.body.variants[0].name == "Red"

    point_def = decl.types[1]
    assert point_def.name == "Point"
    assert isinstance(point_def.body, RecordTypeDef)
    assert len(point_def.body.fields) == 2

    # Constants
    assert len(decl.constants) == 1
    assert decl.constants[0].name == "MAX"

    # Function with match + requires
    func = decl.body[0]
    assert isinstance(func, FunctionDef)
    assert len(func.requires) == 1
    body_stmt = func.body[0]
    assert isinstance(body_stmt, ExprStmt)
    match = body_stmt.expr
    assert isinstance(match, MatchExpr)
    assert len(match.arms) == 3


def test_lookup_type_roundtrip():
    """Lookup types with entries and tuple fields serialize correctly."""
    module = Module(
        declarations=[
            ModuleDecl(
                name="Lookup",
                narrative=None,
                domain=None,
                temporal=None,
                imports=[],
                types=[
                    TypeDef(
                        name="Status",
                        type_params=[],
                        modifiers=[],
                        body=LookupTypeDef(
                            value_type=SimpleType("String", _S),
                            entries=[
                                LookupEntry("Active", "active", "string", _S),
                                LookupEntry("Inactive", "inactive", "string", _S),
                            ],
                            span=_S,
                            value_types=(),
                            column_names=(),
                            is_binary=False,
                            csv_path=None,
                            is_store_backed=False,
                            is_pipe_entry_format=False,
                            is_dispatch=False,
                        ),
                        span=_S,
                    )
                ],
                constants=[],
                invariants=[],
                foreign_blocks=[],
                body=[],
                span=_S,
            )
        ],
        span=_S,
    )

    data, strings = serialize_module(module)
    restored = deserialize_module(data, strings)

    decl = restored.declarations[0]
    assert isinstance(decl, ModuleDecl)
    td = decl.types[0]
    assert td.name == "Status"
    assert isinstance(td.body, LookupTypeDef)
    assert len(td.body.entries) == 2
    assert td.body.entries[0].variant == "Active"
    assert td.body.entries[0].value == "active"
    # Tuple fields should be tuples, not lists
    assert isinstance(td.body.value_types, tuple)
    assert isinstance(td.body.column_names, tuple)


def test_all_node_types_have_tags():
    """Every concrete AST node type used in the union types has a tag."""
    from prove import ast_nodes

    # Collect all types from the union type aliases
    union_members = set()
    for name in ["TypeExpr", "Pattern", "Expr", "Stmt", "TypeBody", "Declaration"]:
        alias = getattr(ast_nodes, name)
        args = get_args(alias)
        if args:
            union_members.update(args)

    # Also check top-level types that aren't in unions
    for name in [
        "Module",
        "ModuleDecl",
        "FunctionDef",
        "MainDef",
        "TypeDef",
        "ConstantDef",
        "ImportDecl",
        "ForeignBlock",
        "ForeignFunction",
        "LookupEntry",
        "InvariantNetwork",
        "Param",
        "ExplainEntry",
        "ExplainBlock",
        "NearMiss",
        "ImportItem",
        "FieldDef",
        "Variant",
        "WithConstraint",
        "MatchArm",
        "TypeModifier",
        "CommentDecl",
    ]:
        cls = getattr(ast_nodes, name)
        union_members.add(cls)

    missing = [cls.__name__ for cls in union_members if cls not in _TAG_MAP]
    assert not missing, f"missing tags for: {missing}"


def test_none_and_bool_roundtrip():
    """None values and booleans in optional fields survive roundtrip."""
    module = Module(
        declarations=[
            ModuleDecl(
                name="Minimal",
                narrative=None,  # None string
                domain=None,
                temporal=None,  # None list
                imports=[],
                types=[],
                constants=[],
                invariants=[],
                foreign_blocks=[],
                body=[
                    FunctionDef(
                        verb="validates",
                        name="is_ok",
                        params=[],
                        return_type=None,
                        can_fail=True,  # bool=True
                        ensures=[],
                        requires=[],
                        explain=None,
                        terminates=None,
                        trusted=None,
                        binary=False,  # bool=False
                        why_not=[],
                        chosen=None,
                        near_misses=[],
                        know=[],
                        assume=[],
                        believe=[],
                        with_constraints=[],
                        intent=None,
                        satisfies=[],
                        event_type=None,
                        state_init=None,
                        state_type=None,
                        body=[ExprStmt(BooleanLit(True, _S), _S)],
                        doc_comment=None,
                        span=_S,
                    ),
                ],
                span=_S,
            )
        ],
        span=_S,
    )

    data, strings = serialize_module(module)
    restored = deserialize_module(data, strings)

    decl = restored.declarations[0]
    assert isinstance(decl, ModuleDecl)
    assert decl.narrative is None
    assert decl.temporal is None
    func = decl.body[0]
    assert isinstance(func, FunctionDef)
    assert func.can_fail is True
    assert func.binary is False
    assert func.return_type is None
    # BooleanLit value
    stmt = func.body[0]
    assert isinstance(stmt, ExprStmt)
    assert isinstance(stmt.expr, BooleanLit)
    assert stmt.expr.value is True
