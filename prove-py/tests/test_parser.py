"""Tests for the Prove parser."""

from __future__ import annotations

from prove.ast_nodes import (
    AlgebraicTypeDef,
    Assignment,
    BinaryDef,
    BinaryExpr,
    BooleanLit,
    CallExpr,
    ComptimeExpr,
    ConstantDef,
    DecimalLit,
    ExprStmt,
    FailPropExpr,
    FieldExpr,
    FunctionDef,
    GenericType,
    IdentifierExpr,
    ImportItem,
    IndexExpr,
    IntegerLit,
    InvariantNetwork,
    LambdaExpr,
    ListLiteral,
    LiteralPattern,
    LookupAccessExpr,
    LookupTypeDef,
    MainDef,
    MatchExpr,
    ModifiedType,
    ModuleDecl,
    PipeExpr,
    RawStringLit,
    RecordTypeDef,
    RefinementTypeDef,
    RegexLit,
    SimpleType,
    StringInterp,
    StringLit,
    TypeDef,
    TypeIdentifierExpr,
    UnaryExpr,
    VarDecl,
    Variant,
)
from prove.lexer import Lexer
from prove.parser import Parser


def parse(source: str):
    """Helper: lex and parse source, return the Module."""
    tokens = Lexer(source, "test.prv").lex()
    return Parser(tokens, "test.prv").parse()


def parse_decl(source: str):
    """Helper: parse and return the first declaration."""
    mod = parse(source)
    assert len(mod.declarations) >= 1
    return mod.declarations[0]


def parse_module_type(source: str):
    """Helper: wrap source in a module, parse, return first type from ModuleDecl."""
    wrapped = f"module M\n{source}"
    mod = parse(wrapped)
    decl = mod.declarations[0]
    assert isinstance(decl, ModuleDecl)
    assert len(decl.types) >= 1
    return decl.types[0]


def parse_module_constant(source: str):
    """Helper: wrap source in a module, parse, return first constant from ModuleDecl."""
    wrapped = f"module M\n{source}"
    mod = parse(wrapped)
    decl = mod.declarations[0]
    assert isinstance(decl, ModuleDecl)
    assert len(decl.constants) >= 1
    return decl.constants[0]


def parse_module_invariant(source: str):
    """Helper: wrap source in a module, parse, return first invariant from ModuleDecl."""
    wrapped = f"module M\n{source}"
    mod = parse(wrapped)
    decl = mod.declarations[0]
    assert isinstance(decl, ModuleDecl)
    assert len(decl.invariants) >= 1
    return decl.invariants[0]


class TestParserTypes:
    def test_simple_type(self):
        decl = parse_module_type("  type Port is Integer where 1..65535\n")
        assert isinstance(decl, TypeDef)
        assert decl.name == "Port"
        assert isinstance(decl.body, RefinementTypeDef)
        assert isinstance(decl.body.base_type, SimpleType)
        assert decl.body.base_type.name == "Integer"

    def test_generic_type(self):
        decl = parse_module_type(
            "  type Result<Value, Error> is Ok(value Value) | Err(error Error)\n"
        )  # noqa: E501
        assert isinstance(decl, TypeDef)
        assert decl.name == "Result"
        assert decl.type_params == ["Value", "Error"]
        assert isinstance(decl.body, AlgebraicTypeDef)

    def test_modified_type(self):
        decl = parse_module_type("  type Port is Integer:[16 Unsigned] where 1..65535\n")
        assert isinstance(decl, TypeDef)
        assert isinstance(decl.body, RefinementTypeDef)
        assert isinstance(decl.body.base_type, ModifiedType)
        assert decl.body.base_type.name == "Integer"

    def test_refinement_type(self):
        # Shorthand `>= 0` means the constraint is an operator expression
        decl = parse_module_type("  type Quantity is Integer where >= 0\n")
        assert isinstance(decl, TypeDef)
        assert isinstance(decl.body, RefinementTypeDef)

    def test_algebraic_inline(self):
        decl = parse_module_type(
            "  type OrderStatus is Pending | Confirmed | Shipped | Cancelled\n"
        )
        assert isinstance(decl, TypeDef)
        assert isinstance(decl.body, AlgebraicTypeDef)
        assert len(decl.body.variants) == 4

    def test_algebraic_multiline(self):
        source = "  type Shape is\n    Circle(radius Decimal)\n    | Rect(w Decimal, h Decimal)\n"
        decl = parse_module_type(source)
        assert isinstance(decl, TypeDef)
        assert isinstance(decl.body, AlgebraicTypeDef)
        assert len(decl.body.variants) >= 2

    def test_record_type(self):
        source = "  type Product is\n    sku String\n    name String\n    price Decimal\n"
        decl = parse_module_type(source)
        assert isinstance(decl, TypeDef)
        assert isinstance(decl.body, RecordTypeDef)
        assert len(decl.body.fields) == 3

    def test_binary_type(self):
        decl = parse_module_type("  type Table<Value> is binary\n")
        assert isinstance(decl, TypeDef)
        assert decl.name == "Table"
        assert decl.type_params == ["Value"]
        assert isinstance(decl.body, BinaryDef)

    def test_binary_type_no_params(self):
        decl = parse_module_type("  type StringBuilder is binary\n")
        assert isinstance(decl, TypeDef)
        assert decl.name == "StringBuilder"
        assert isinstance(decl.body, BinaryDef)

    def test_unit_variants(self):
        decl = parse_module_type("  type Color is Red | Green | Blue\n")
        assert isinstance(decl.body, AlgebraicTypeDef)
        for v in decl.body.variants:
            assert isinstance(v, Variant)
            assert len(v.fields) == 0


class TestParserFunctions:
    def test_transforms(self):
        source = "transforms area(s Shape) Decimal\n    from\n        s\n"
        decl = parse_decl(source)
        assert isinstance(decl, FunctionDef)
        assert decl.verb == "transforms"
        assert decl.name == "area"
        assert len(decl.params) == 1

    def test_validates(self):
        source = "validates email(address String)\n    from\n        address\n"
        decl = parse_decl(source)
        assert isinstance(decl, FunctionDef)
        assert decl.verb == "validates"

    def test_inputs(self):
        source = "inputs load_config(path String) Config!\n    from\n        path\n"
        decl = parse_decl(source)
        assert isinstance(decl, FunctionDef)
        assert decl.verb == "inputs"
        assert decl.can_fail is True

    def test_outputs(self):
        source = "outputs add_product(db Store, product Product)!\n    from\n        db\n"
        decl = parse_decl(source)
        assert isinstance(decl, FunctionDef)
        assert decl.verb == "outputs"
        assert decl.can_fail is True

    def test_derives(self):
        source = "derives get(key String, table Table) String\n    from\n        key\n"
        decl = parse_decl(source)
        assert isinstance(decl, FunctionDef)
        assert decl.verb == "derives"
        assert decl.name == "get"

    def test_reads_alias(self):
        """reads keyword parses as derives (backward compat)."""
        source = "reads get(key String, table Table) String\n    from\n        key\n"
        decl = parse_decl(source)
        assert isinstance(decl, FunctionDef)
        assert decl.verb == "derives"
        assert decl.name == "get"

    def test_dispatches(self):
        source = "dispatches handle(cmd String) Integer\n    from\n        0\n"
        decl = parse_decl(source)
        assert isinstance(decl, FunctionDef)
        assert decl.verb == "dispatches"
        assert decl.name == "handle"

    def test_creates(self):
        source = "creates new() Table\n    from\n        0\n"
        decl = parse_decl(source)
        assert isinstance(decl, FunctionDef)
        assert decl.verb == "creates"
        assert decl.name == "new"

    def test_matches(self):
        source = (
            "matches add(key String, value String, table Table) Table\n    from\n        table\n"
        )
        decl = parse_decl(source)
        assert isinstance(decl, FunctionDef)
        assert decl.verb == "matches"
        assert decl.name == "add"

    def test_main(self):
        source = "main() Result<Unit, Error>!\n    from\n        x\n"
        decl = parse_decl(source)
        assert isinstance(decl, MainDef)
        assert decl.can_fail is True
        assert isinstance(decl.return_type, GenericType)

    def test_ensures(self):
        source = "transforms f(x Integer) Integer\n    ensures result >= 0\n    from\n        x\n"
        decl = parse_decl(source)
        assert isinstance(decl, FunctionDef)
        assert len(decl.ensures) == 1

    def test_requires(self):
        source = "transforms f(x Integer) Integer\n    requires x > 0\n    from\n        x\n"
        decl = parse_decl(source)
        assert isinstance(decl, FunctionDef)
        assert len(decl.requires) == 1

    def test_explain_named_entry(self):
        source = (
            "transforms f(x Integer) Integer\n"
            "    ensures result >= 0\n"
            "    explain\n"
            "        non_negative: x is always positive\n"
            "    from\n"
            "        x\n"
        )
        decl = parse_decl(source)
        assert isinstance(decl, FunctionDef)
        assert decl.explain is not None
        assert len(decl.explain.entries) == 1
        assert decl.explain.entries[0].name == "non_negative"
        assert decl.explain.entries[0].condition is None

    def test_explain_with_when_condition(self):
        source = (
            "transforms abs(n Integer) Integer\n"
            "    ensures result >= 0\n"
            "    explain\n"
            "        positive: identity when n >= 0\n"
            "        negative: deducted when n < 0\n"
            "    from\n"
            "        n\n"
            "        0 - n\n"
        )
        decl = parse_decl(source)
        assert isinstance(decl, FunctionDef)
        assert decl.explain is not None
        assert len(decl.explain.entries) == 2
        e0 = decl.explain.entries[0]
        assert e0.name == "positive"
        assert e0.text == "identity"
        assert isinstance(e0.condition, BinaryExpr)
        assert e0.condition.op == ">="
        e1 = decl.explain.entries[1]
        assert e1.name == "negative"
        assert e1.text == "deducted"
        assert isinstance(e1.condition, BinaryExpr)
        assert e1.condition.op == "<"

    def test_explain_mixed_entries(self):
        source = (
            "transforms clamp_pos(n Integer) Integer\n"
            "    ensures result >= 0\n"
            "    explain\n"
            "        bounded: every path keeps result non-negative\n"
            "        positive: identity when n >= 0\n"
            "    from\n"
            "        n\n"
            "        0\n"
        )
        decl = parse_decl(source)
        assert isinstance(decl, FunctionDef)
        assert decl.explain is not None
        assert len(decl.explain.entries) == 2
        assert decl.explain.entries[0].condition is None
        assert decl.explain.entries[1].condition is not None

    def test_doc_comment(self):
        source = "/// Does something\ntransforms f(x Integer) Integer\n    from\n        x\n"
        decl = parse_decl(source)
        assert isinstance(decl, FunctionDef)
        assert decl.doc_comment == "Does something"


class TestParserExpressions:
    def test_integer_literal(self):
        source = "transforms f() Integer\n    from\n        42\n"
        decl = parse_decl(source)
        assert isinstance(decl.body[0], ExprStmt)
        assert isinstance(decl.body[0].expr, IntegerLit)
        assert decl.body[0].expr.value == "42"

    def test_decimal_literal(self):
        source = "transforms f() Decimal\n    from\n        3.14\n"
        decl = parse_decl(source)
        assert isinstance(decl.body[0].expr, DecimalLit)

    def test_string_literal(self):
        source = 'transforms f() String\n    from\n        "hello"\n'
        decl = parse_decl(source)
        assert isinstance(decl.body[0].expr, StringLit)
        assert decl.body[0].expr.value == "hello"

    def test_boolean_literal(self):
        source = "transforms f() Boolean\n    from\n        true\n"
        decl = parse_decl(source)
        assert isinstance(decl.body[0].expr, BooleanLit)
        assert decl.body[0].expr.value is True

    def test_binary_ops(self):
        source = "transforms f() Integer\n    from\n        1 + 2\n"
        decl = parse_decl(source)
        expr = decl.body[0].expr
        assert isinstance(expr, BinaryExpr)
        assert expr.op == "+"

    def test_precedence(self):
        source = "transforms f() Integer\n    from\n        1 + 2 * 3\n"
        decl = parse_decl(source)
        expr = decl.body[0].expr
        # Should be 1 + (2 * 3)
        assert isinstance(expr, BinaryExpr)
        assert expr.op == "+"
        assert isinstance(expr.right, BinaryExpr)
        assert expr.right.op == "*"

    def test_pipe(self):
        source = "transforms f() Integer\n    from\n        x |> g\n"
        decl = parse_decl(source)
        expr = decl.body[0].expr
        assert isinstance(expr, PipeExpr)

    def test_field_access(self):
        source = "transforms f() Integer\n    from\n        x.y\n"
        decl = parse_decl(source)
        expr = decl.body[0].expr
        assert isinstance(expr, FieldExpr)
        assert expr.field == "y"

    def test_call(self):
        source = "transforms f() Integer\n    from\n        g(1, 2)\n"
        decl = parse_decl(source)
        expr = decl.body[0].expr
        assert isinstance(expr, CallExpr)
        assert len(expr.args) == 2

    def test_namespaced_call(self):
        source = "transforms f() Integer\n    from\n        Table.new()\n"
        decl = parse_decl(source)
        expr = decl.body[0].expr
        assert isinstance(expr, CallExpr)
        assert isinstance(expr.func, FieldExpr)
        assert isinstance(expr.func.obj, TypeIdentifierExpr)
        assert expr.func.obj.name == "Table"
        assert expr.func.field == "new"

    def test_fail_propagation(self):
        source = "inputs f() Integer!\n    from\n        g()!\n"
        decl = parse_decl(source)
        expr = decl.body[0].expr
        assert isinstance(expr, FailPropExpr)

    def test_unary_minus(self):
        source = "transforms f() Integer\n    from\n        -x\n"
        decl = parse_decl(source)
        expr = decl.body[0].expr
        assert isinstance(expr, UnaryExpr)
        assert expr.op == "-"

    def test_unary_not(self):
        source = "transforms f() Boolean\n    from\n        !x\n"
        decl = parse_decl(source)
        expr = decl.body[0].expr
        assert isinstance(expr, UnaryExpr)
        assert expr.op == "!"

    def test_lambda(self):
        source = "transforms f() Integer\n    from\n        map(xs, |x| x + 1)\n"
        decl = parse_decl(source)
        call = decl.body[0].expr
        assert isinstance(call, CallExpr)
        assert isinstance(call.args[1], LambdaExpr)
        assert call.args[1].params == ["x"]

    def test_match_expr(self):
        source = (
            "transforms f() Integer\n    from\n"
            "        match x\n            A => 1\n"
            "            B => 2\n"
        )
        decl = parse_decl(source)
        expr = decl.body[0].expr
        assert isinstance(expr, MatchExpr)
        assert len(expr.arms) == 2

    def test_list_literal(self):
        source = "transforms f() List<Integer>\n    from\n        [1, 2, 3]\n"
        decl = parse_decl(source)
        expr = decl.body[0].expr
        assert isinstance(expr, ListLiteral)
        assert len(expr.elements) == 3

    def test_string_interpolation(self):
        source = 'transforms f() String\n    from\n        f"hello {name}"\n'
        decl = parse_decl(source)
        expr = decl.body[0].expr
        assert isinstance(expr, StringInterp)

    def test_plain_string_no_interp(self):
        source = 'transforms f() String\n    from\n        "hello {x}"\n'
        decl = parse_decl(source)
        expr = decl.body[0].expr
        assert isinstance(expr, StringLit)
        assert expr.value == "hello {x}"

    def test_range(self):
        source = "transforms f() Integer\n    from\n        1..10\n"
        decl = parse_decl(source)
        expr = decl.body[0].expr
        assert isinstance(expr, BinaryExpr)
        assert expr.op == ".."

    def test_index(self):
        source = "transforms f() Integer\n    from\n        xs[0]\n"
        decl = parse_decl(source)
        expr = decl.body[0].expr
        assert isinstance(expr, IndexExpr)

    def test_regex_literal(self):
        source = "validates f(s String)\n    from\n        check(s, /^[A-Z]+$/)\n"
        decl = parse_decl(source)
        call = decl.body[0].expr
        assert isinstance(call, CallExpr)
        assert isinstance(call.args[1], RegexLit)

    def test_raw_string_literal(self):
        source = 'validates f(s String)\n    from\n        check(s, r"^[A-Z]+$")\n'
        decl = parse_decl(source)
        call = decl.body[0].expr
        assert isinstance(call, CallExpr)
        assert isinstance(call.args[1], RawStringLit)

    def test_verb_keyword_in_expr_gives_clear_error(self):
        import pytest

        from prove.errors import CompileError

        source = 'validates f(s String)\n    from\n        matches(s, "pattern")\n'
        with pytest.raises(CompileError, match="verb keyword"):
            parse_decl(source)


class TestParserStatements:
    def test_var_decl_with_type(self):
        source = "transforms f() Integer\n    from\n        x as Integer = 42\n        x\n"
        decl = parse_decl(source)
        stmt = decl.body[0]
        assert isinstance(stmt, VarDecl)
        assert stmt.name == "x"
        assert isinstance(stmt.type_expr, SimpleType)

    def test_assignment(self):
        source = "transforms f() Integer\n    from\n        x = 42\n        x\n"
        decl = parse_decl(source)
        stmt = decl.body[0]
        assert isinstance(stmt, Assignment)
        assert stmt.target == "x"

    def test_expression_statement(self):
        source = "transforms f() Integer\n    from\n        g()\n"
        decl = parse_decl(source)
        stmt = decl.body[0]
        assert isinstance(stmt, ExprStmt)


class TestParserImplicitMatch:
    def test_inputs_implicit_match(self):
        source = (
            "inputs request(route Route) Response!\n"
            "    from\n"
            '        Get("/health") => ok("healthy")\n'
            "        _ => not_found()\n"
        )
        decl = parse_decl(source)
        assert isinstance(decl, FunctionDef)
        # Body should contain a MatchExpr with subject=None
        match_found = False
        for item in decl.body:
            if isinstance(item, MatchExpr):
                assert item.subject is None
                assert len(item.arms) == 2
                match_found = True
        assert match_found

    def test_mixed_stmts_and_arms(self):
        source = (
            "inputs request(route Route, db Store) Response!\n"
            "    from\n"
            "        user as User = authenticate()!\n"
            '        Get("/health") => ok("healthy")\n'
            "        _ => not_found()\n"
        )
        decl = parse_decl(source)
        # First should be VarDecl, then MatchExpr
        assert isinstance(decl.body[0], VarDecl)
        assert isinstance(decl.body[1], MatchExpr)


class TestParserMultiPatternMatch:
    """Multi-pattern match arms desugar into one arm per pattern."""

    def test_multi_pattern_produces_duplicate_arms(self):
        from prove.parse import parse as cst_parse

        source = (
            "matches route(path String) String\n"
            "    from\n"
            '        "foo"\n'
            '        "bar" => "matched"\n'
            '        _ => "other"\n'
        )
        mod = cst_parse(source, "test.prv")
        decl = mod.declarations[0]
        assert isinstance(decl, FunctionDef)
        match_expr = decl.body[0]
        assert isinstance(match_expr, MatchExpr)
        # "foo" and "bar" should each be their own arm, plus the wildcard
        assert len(match_expr.arms) == 3
        assert isinstance(match_expr.arms[0].pattern, LiteralPattern)
        assert match_expr.arms[0].pattern.value == "foo"
        assert isinstance(match_expr.arms[1].pattern, LiteralPattern)
        assert match_expr.arms[1].pattern.value == "bar"
        # Both share the same body
        assert len(match_expr.arms[0].body) == len(match_expr.arms[1].body)

    def test_three_patterns_same_arm(self):
        from prove.parse import parse as cst_parse

        source = (
            "matches kind(tag String) String\n"
            "    from\n"
            '        "a"\n'
            '        "b"\n'
            '        "c" => "letter"\n'
            '        _ => "other"\n'
        )
        mod = cst_parse(source, "test.prv")
        decl = mod.declarations[0]
        match_expr = decl.body[0]
        assert isinstance(match_expr, MatchExpr)
        assert len(match_expr.arms) == 4


class TestParserConstants:
    def test_simple_constant(self):
        source = "  MAX_SIZE as Integer = 100\n"
        decl = parse_module_constant(source)
        assert isinstance(decl, ConstantDef)
        assert decl.name == "MAX_SIZE"
        assert isinstance(decl.type_expr, SimpleType)

    def test_comptime_constant(self):
        source = (
            "  MAX_CONNECTIONS as Integer = comptime\n"
            '    match target\n        "embedded" => 16\n'
            "        _ => 1024\n"
        )
        decl = parse_module_constant(source)
        assert isinstance(decl, ConstantDef)
        assert isinstance(decl.value, ComptimeExpr)


class TestParserModules:
    def test_module_decl(self):
        source = "module Auth\n  temporal: authenticate -> authorize -> access\n"
        decl = parse_decl(source)
        assert isinstance(decl, ModuleDecl)
        assert decl.name == "Auth"
        assert decl.temporal == ["authenticate", "authorize", "access"]

    def test_module_with_narrative(self):
        source = 'module UserService\n  narrative: """Users are managed here."""\n'
        decl = parse_decl(source)
        assert isinstance(decl, ModuleDecl)
        assert decl.narrative is not None

    def test_import(self):
        source = "module Foo\n  String contains length\n"
        decl = parse_decl(source)
        assert isinstance(decl, ModuleDecl)
        assert len(decl.imports) == 1
        imp = decl.imports[0]
        assert imp.module == "String"
        assert len(imp.items) == 2
        assert imp.items[0].verb is None
        assert imp.items[0].name == "contains"
        assert imp.items[1].name == "length"

    def test_import_types_verb(self):
        source = "module Foo\n  System types ExitCode, inputs console\n"
        decl = parse_decl(source)
        assert isinstance(decl, ModuleDecl)
        assert len(decl.imports) == 1
        imp = decl.imports[0]
        assert imp.module == "System"
        assert len(imp.items) == 2
        assert imp.items[0].verb == "types"
        assert imp.items[0].name == "ExitCode"
        assert imp.items[1].verb == "inputs"
        assert imp.items[1].name == "console"

    def test_import_with_verb(self):
        source = "module Foo\n  Auth validates login, transforms login\n"
        decl = parse_decl(source)
        assert isinstance(decl, ModuleDecl)
        assert len(decl.imports) == 1
        imp = decl.imports[0]
        assert imp.items[0].verb == "validates"
        assert imp.items[0].name == "login"
        assert imp.items[1].verb == "transforms"
        assert imp.items[1].name == "login"

    def test_import_verb_group(self):
        source = "module Foo\n  System outputs console file, inputs console file\n"
        decl = parse_decl(source)
        assert isinstance(decl, ModuleDecl)
        assert len(decl.imports) == 1
        imp = decl.imports[0]
        assert imp.module == "System"
        assert len(imp.items) == 4
        assert imp.items[0] == ImportItem("outputs", "console", imp.items[0].span)
        assert imp.items[1] == ImportItem("outputs", "file", imp.items[1].span)
        assert imp.items[2] == ImportItem("inputs", "console", imp.items[2].span)
        assert imp.items[3] == ImportItem("inputs", "file", imp.items[3].span)

    def test_import_constant_identifiers(self):
        source = "module Foo\n  Log RED GREEN RESET\n"
        decl = parse_decl(source)
        assert isinstance(decl, ModuleDecl)
        assert len(decl.imports) == 1
        imp = decl.imports[0]
        assert imp.module == "Log"
        assert len(imp.items) == 3
        assert imp.items[0].name == "RED"
        assert imp.items[1].name == "GREEN"
        assert imp.items[2].name == "RESET"

    def test_doc_comment_before_constant(self):
        source = "module Foo\n  /// My constant.\n  MY_CONST as Integer = 42\n"
        decl = parse_decl(source)
        assert isinstance(decl, ModuleDecl)
        assert len(decl.constants) == 1
        assert decl.constants[0].name == "MY_CONST"
        assert decl.constants[0].doc_comment == "My constant."

    def test_invariant_network(self):
        source = "  invariant_network Accounting\n    total >= 0\n"
        decl = parse_module_invariant(source)
        assert isinstance(decl, InvariantNetwork)
        assert decl.name == "Accounting"
        assert len(decl.constraints) >= 1

    def test_invariant_network_string_name(self):
        source = '  invariant_network "valid_state"\n    total >= 0\n'
        decl = parse_module_invariant(source)
        assert isinstance(decl, InvariantNetwork)
        assert decl.name == "valid_state"

    def test_invariant_network_colon_syntax(self):
        source = '  invariant_network: "valid_state"\n'
        decl = parse_module_invariant(source)
        assert isinstance(decl, InvariantNetwork)
        assert decl.name == "valid_state"

    def test_module_with_domain(self):
        source = "module PaymentService\n  domain: Finance\n"
        decl = parse_decl(source)
        assert isinstance(decl, ModuleDecl)
        assert decl.domain == "Finance"

    def test_module_with_domain_string(self):
        source = 'module PaymentService\n  domain: "finance"\n'
        decl = parse_decl(source)
        assert isinstance(decl, ModuleDecl)
        assert decl.domain == "finance"

    def test_module_with_all_features(self):
        source = (
            "module Main\n"
            '  narrative: """Test"""\n'
            "  domain: Finance\n"
            "  temporal: authenticate -> authorize -> access\n"
        )
        decl = parse_decl(source)
        assert isinstance(decl, ModuleDecl)
        assert decl.narrative == "Test"
        assert decl.domain == "Finance"
        assert decl.temporal == ["authenticate", "authorize", "access"]

    def test_temporal_string_syntax(self):
        source = 'module Auth\n  temporal: "authenticate -> authorize -> access"\n'
        decl = parse_decl(source)
        assert isinstance(decl, ModuleDecl)
        assert decl.temporal == ["authenticate", "authorize", "access"]


class TestParserAIResistance:
    def test_why_not_chosen(self):
        source = (
            "transforms evict(cache Cache) Option<Product>\n"
            '    why_not: "FIFO bad"\n'
            '    chosen: "LFU because reasons"\n'
            "    from\n"
            "        cache\n"
        )
        decl = parse_decl(source)
        assert isinstance(decl, FunctionDef)
        assert len(decl.why_not) == 1
        assert decl.chosen is not None

    def test_near_miss(self):
        source = (
            "validates wholesale(quantity Integer)\n"
            "    near_miss: 10 => false\n"
            "    near_miss: 11 => true\n"
            "    from\n"
            "        quantity\n"
        )
        decl = parse_decl(source)
        assert isinstance(decl, FunctionDef)
        assert len(decl.near_misses) == 2

    def test_epistemic_annotations(self):
        source = (
            "transforms process(order Order) Receipt\n"
            "    know: len(order) > 0\n"
            "    assume: order\n"
            "    believe: order\n"
            "    from\n"
            "        order\n"
        )
        decl = parse_decl(source)
        assert len(decl.know) == 1
        assert len(decl.assume) == 1
        assert len(decl.believe) == 1


class TestParserIntegration:
    def test_parse_hello_main(self):
        """Parse the hello world example."""
        source = (
            "/// Hello from Prove!\n"
            "main() Result<Unit, Error>!\n"
            "    from\n"
            '        println("Hello from Prove!")\n'
        )
        mod = parse(source)
        assert len(mod.declarations) == 1
        decl = mod.declarations[0]
        assert isinstance(decl, MainDef)
        assert decl.doc_comment == "Hello from Prove!"

    def test_parse_hello_file(self):
        """Parse the actual hello example file."""
        from pathlib import Path

        hello = Path(__file__).resolve().parent.parent.parent / "examples/hello/src/main.prv"
        if not hello.exists():
            import pytest

            pytest.skip("hello example not found")
        source = hello.read_text()
        mod = parse(source)
        # Module declaration + main function
        assert len(mod.declarations) == 2
        assert isinstance(mod.declarations[0], ModuleDecl)
        assert isinstance(mod.declarations[1], MainDef)

    def test_parse_multiple_declarations(self):
        source = (
            "module M\n"
            "  type Port is Integer where 1..65535\n"
            "\n"
            "validates valid_port(p Integer)\n"
            "    from\n"
            "        p >= 1 && p <= 65535\n"
        )
        mod = parse(source)
        assert len(mod.declarations) == 2
        assert isinstance(mod.declarations[0], ModuleDecl)
        assert len(mod.declarations[0].types) == 1
        assert isinstance(mod.declarations[1], FunctionDef)


class TestParserLookup:
    """Tests for [Lookup] type modifier parsing."""

    def test_lookup_type_basic(self):
        """Parse a basic [Lookup] type definition."""
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
            "        0\n"
        )
        mod = parse(source)
        decl = mod.declarations[0]
        assert isinstance(decl, ModuleDecl)
        assert len(decl.types) == 1
        td = decl.types[0]
        assert isinstance(td, TypeDef)
        assert td.name == "TokenKind"
        assert len(td.modifiers) == 1
        assert td.modifiers[0].value == "Lookup"
        assert isinstance(td.body, LookupTypeDef)
        assert len(td.body.entries) == 3
        assert td.body.entries[0].variant == "Main"
        assert td.body.entries[0].value == "main"
        assert td.body.entries[0].value_kind == "string"

    def test_lookup_access_string(self):
        """Parse TokenKind:"main" as a LookupAccessExpr."""
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
        mod = parse(source)
        main_def = mod.declarations[1]
        assert isinstance(main_def, MainDef)
        stmt = main_def.body[0]
        assert isinstance(stmt, ExprStmt)
        assert isinstance(stmt.expr, LookupAccessExpr)
        assert stmt.expr.type_name == "TokenKind"
        assert isinstance(stmt.expr.operand, StringLit)
        assert stmt.expr.operand.value == "main"

    def test_lookup_access_variant(self):
        """Parse TokenKind:Main as a LookupAccessExpr."""
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
        mod = parse(source)
        main_def = mod.declarations[1]
        assert isinstance(main_def, MainDef)
        stmt = main_def.body[0]
        assert isinstance(stmt, ExprStmt)
        assert isinstance(stmt.expr, LookupAccessExpr)
        assert stmt.expr.type_name == "TokenKind"
        assert isinstance(stmt.expr.operand, TypeIdentifierExpr)
        assert stmt.expr.operand.name == "Main"

    def test_lookup_stacking(self):
        """Parse stacked entries: BooleanLit | "true" / | "false"."""
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
            "        0\n"
        )
        mod = parse(source)
        decl = mod.declarations[0]
        assert isinstance(decl, ModuleDecl)
        td = decl.types[0]
        assert isinstance(td.body, LookupTypeDef)
        assert len(td.body.entries) == 3
        assert td.body.entries[0].variant == "BooleanLit"
        assert td.body.entries[0].value == "true"
        assert td.body.entries[1].variant == "BooleanLit"
        assert td.body.entries[1].value == "false"
        assert td.body.entries[2].variant == "Foreign"
        assert td.body.entries[2].value == "foreign"

    def test_lookup_as_function_name(self):
        """'lookup' can be used as a function name (no longer a keyword)."""
        source = 'module M\n\nreads lookup(key String) String\n    from\n        "value"\n'
        mod = parse(source)
        func = mod.declarations[1]
        assert isinstance(func, FunctionDef)
        assert func.name == "lookup"


class TestParserBinaryLookup:
    """Tests for binary lookup type parsing."""

    def test_binary_lookup_basic(self):
        """Parse a basic binary lookup declaration."""
        source = (
            "module M\n"
            "\n"
            "  binary TokenKind String Integer where\n"
            '      First | "first" | 1\n'
            '      Second | "second" | 2\n'
            "\n"
            "main()\n"
            "    from\n"
            "        0\n"
        )
        mod = parse(source)
        decl = mod.declarations[0]
        assert isinstance(decl, ModuleDecl)
        assert len(decl.types) == 1
        td = decl.types[0]
        assert isinstance(td, TypeDef)
        assert td.name == "TokenKind"
        assert isinstance(td.body, LookupTypeDef)
        assert td.body.is_binary is True
        assert len(td.body.value_types) == 2
        assert len(td.body.entries) == 2
        assert td.body.entries[0].variant == "First"
        assert td.body.entries[0].values == ("first", "1")
        assert td.body.entries[0].value_kinds == ("string", "integer")
        assert td.body.entries[1].variant == "Second"

    def test_binary_lookup_three_columns(self):
        """Parse a binary lookup with three columns."""
        source = (
            "module M\n"
            "\n"
            "  binary TokenKind String Integer Decimal where\n"
            '      First | "first" | 1 | 1.0\n'
            '      Second | "second" | 2 | 2.0\n'
            "\n"
            "main()\n"
            "    from\n"
            "        0\n"
        )
        mod = parse(source)
        decl = mod.declarations[0]
        assert isinstance(decl, ModuleDecl)
        td = decl.types[0]
        assert isinstance(td.body, LookupTypeDef)
        assert td.body.is_binary is True
        assert len(td.body.value_types) == 3
        assert len(td.body.entries) == 2
        assert td.body.entries[0].values == ("first", "1", "1.0")
        assert td.body.entries[0].value_kinds == ("string", "integer", "decimal")

    def test_binary_lookup_variable_access(self):
        """Parse TypeName:variable on a binary lookup type."""
        source = (
            "module M\n"
            "\n"
            "  binary TokenKind String Integer where\n"
            '      First | "first" | 1\n'
            '      Second | "second" | 2\n'
            "\n"
            "transforms lookup_word(kind TokenKind) String\n"
            "    from\n"
            "        TokenKind:kind\n"
        )
        mod = parse(source)
        func = mod.declarations[1]
        assert isinstance(func, FunctionDef)
        stmt = func.body[0]
        assert isinstance(stmt, ExprStmt)
        assert isinstance(stmt.expr, LookupAccessExpr)
        assert stmt.expr.type_name == "TokenKind"
        assert isinstance(stmt.expr.operand, IdentifierExpr)
        assert stmt.expr.operand.name == "kind"

    def test_binary_lookup_with_doc_comment(self):
        """Binary lookup with doc comment."""
        source = (
            "module M\n"
            "\n"
            "  /// Token kinds for the lexer.\n"
            "  binary TokenKind String Integer where\n"
            '      First | "first" | 1\n'
            "\n"
            "main()\n"
            "    from\n"
            "        0\n"
        )
        mod = parse(source)
        decl = mod.declarations[0]
        assert isinstance(decl, ModuleDecl)
        td = decl.types[0]
        assert isinstance(td, TypeDef)
        assert td.doc_comment is not None
        assert "Token kinds" in td.doc_comment

    def test_binary_lookup_named_columns(self):
        """Parse named columns with name:Type syntax."""
        source = (
            "module M\n"
            "\n"
            "  binary Prediction probability:Float String confidence:Float where\n"
            '      Cat | 0.9 | "cat" | 0.95\n'
            '      Dog | 0.8 | "dog" | 0.85\n'
            "\n"
            "main()\n"
            "    from\n"
            "        0\n"
        )
        mod = parse(source)
        decl = mod.declarations[0]
        assert isinstance(decl, ModuleDecl)
        td = decl.types[0]
        assert isinstance(td, TypeDef)
        assert td.name == "Prediction"
        assert isinstance(td.body, LookupTypeDef)
        assert td.body.is_binary is True
        assert len(td.body.value_types) == 3
        assert td.body.column_names == ("probability", None, "confidence")
        assert len(td.body.entries) == 2
        assert td.body.entries[0].variant == "Cat"
        assert td.body.entries[0].values == ("0.9", "cat", "0.95")

    def test_binary_lookup_all_named_columns(self):
        """Parse binary lookup where all columns are named."""
        source = (
            "module M\n"
            "\n"
            "  binary Score value:Integer label:String where\n"
            '      High | 100 | "high"\n'
            '      Low | 10 | "low"\n'
            "\n"
            "main()\n"
            "    from\n"
            "        0\n"
        )
        mod = parse(source)
        decl = mod.declarations[0]
        assert isinstance(decl, ModuleDecl)
        td = decl.types[0]
        assert isinstance(td.body, LookupTypeDef)
        assert td.body.column_names == ("value", "label")

    def test_binary_lookup_unnamed_columns_compat(self):
        """Existing unnamed columns still work — column_names are all None."""
        source = (
            "module M\n"
            "\n"
            "  binary TokenKind String Integer where\n"
            '      First | "first" | 1\n'
            "\n"
            "main()\n"
            "    from\n"
            "        0\n"
        )
        mod = parse(source)
        decl = mod.declarations[0]
        assert isinstance(decl, ModuleDecl)
        td = decl.types[0]
        assert isinstance(td.body, LookupTypeDef)
        assert td.body.column_names == (None, None)
