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
    ImportItem,
    IndexExpr,
    IntegerLit,
    InvariantNetwork,
    LambdaExpr,
    ListLiteral,
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
        decl = parse_module_type("  type Result<T, E> is Ok(value T) | Err(error E)\n")
        assert isinstance(decl, TypeDef)
        assert decl.name == "Result"
        assert decl.type_params == ["T", "E"]
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
        decl = parse_module_type("  type Table<V> is binary\n")
        assert isinstance(decl, TypeDef)
        assert decl.name == "Table"
        assert decl.type_params == ["V"]
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
        source = 'validates email(address String)\n    from\n        address\n'
        decl = parse_decl(source)
        assert isinstance(decl, FunctionDef)
        assert decl.verb == "validates"

    def test_inputs(self):
        source = 'inputs load_config(path String) Config!\n    from\n        path\n'
        decl = parse_decl(source)
        assert isinstance(decl, FunctionDef)
        assert decl.verb == "inputs"
        assert decl.can_fail is True

    def test_outputs(self):
        source = 'outputs add_product(db Database, product Product)!\n    from\n        db\n'
        decl = parse_decl(source)
        assert isinstance(decl, FunctionDef)
        assert decl.verb == "outputs"
        assert decl.can_fail is True

    def test_reads(self):
        source = 'reads get(key String, table Table) String\n    from\n        key\n'
        decl = parse_decl(source)
        assert isinstance(decl, FunctionDef)
        assert decl.verb == "reads"
        assert decl.name == "get"

    def test_creates(self):
        source = 'creates new() Table\n    from\n        0\n'
        decl = parse_decl(source)
        assert isinstance(decl, FunctionDef)
        assert decl.verb == "creates"
        assert decl.name == "new"

    def test_matches(self):
        source = (
            'matches add(key String, value String, table Table)'
            ' Table\n    from\n        table\n'
        )
        decl = parse_decl(source)
        assert isinstance(decl, FunctionDef)
        assert decl.verb == "matches"
        assert decl.name == "add"

    def test_main(self):
        source = 'main() Result<Unit, Error>!\n    from\n        x\n'
        decl = parse_decl(source)
        assert isinstance(decl, MainDef)
        assert decl.can_fail is True
        assert isinstance(decl.return_type, GenericType)

    def test_ensures(self):
        source = 'transforms f(x Integer) Integer\n    ensures result >= 0\n    from\n        x\n'
        decl = parse_decl(source)
        assert isinstance(decl, FunctionDef)
        assert len(decl.ensures) == 1

    def test_requires(self):
        source = 'transforms f(x Integer) Integer\n    requires x > 0\n    from\n        x\n'
        decl = parse_decl(source)
        assert isinstance(decl, FunctionDef)
        assert len(decl.requires) == 1

    def test_proof_block(self):
        source = (
            'transforms f(x Integer) Integer\n'
            '    ensures result >= 0\n'
            '    proof\n'
            '        non_negative: x is always positive\n'
            '    from\n'
            '        x\n'
        )
        decl = parse_decl(source)
        assert isinstance(decl, FunctionDef)
        assert decl.proof is not None
        assert len(decl.proof.obligations) == 1
        assert decl.proof.obligations[0].name == "non_negative"
        assert decl.proof.obligations[0].condition is None

    def test_proof_with_when_condition(self):
        source = (
            'transforms abs(n Integer) Integer\n'
            '    ensures result >= 0\n'
            '    proof\n'
            '        positive: identity when n >= 0\n'
            '        negative: deducted when n < 0\n'
            '    from\n'
            '        n\n'
            '        0 - n\n'
        )
        decl = parse_decl(source)
        assert isinstance(decl, FunctionDef)
        assert decl.proof is not None
        assert len(decl.proof.obligations) == 2
        obl0 = decl.proof.obligations[0]
        assert obl0.name == "positive"
        assert obl0.text == "identity"
        assert isinstance(obl0.condition, BinaryExpr)
        assert obl0.condition.op == ">="
        obl1 = decl.proof.obligations[1]
        assert obl1.name == "negative"
        assert obl1.text == "deducted"
        assert isinstance(obl1.condition, BinaryExpr)
        assert obl1.condition.op == "<"

    def test_proof_mixed_obligations(self):
        source = (
            'transforms clamp_pos(n Integer) Integer\n'
            '    ensures result >= 0\n'
            '    proof\n'
            '        bounded: every path keeps result non-negative\n'
            '        positive: identity when n >= 0\n'
            '    from\n'
            '        n\n'
            '        0\n'
        )
        decl = parse_decl(source)
        assert isinstance(decl, FunctionDef)
        assert decl.proof is not None
        assert len(decl.proof.obligations) == 2
        assert decl.proof.obligations[0].condition is None
        assert decl.proof.obligations[1].condition is not None

    def test_doc_comment(self):
        source = '/// Does something\ntransforms f(x Integer) Integer\n    from\n        x\n'
        decl = parse_decl(source)
        assert isinstance(decl, FunctionDef)
        assert decl.doc_comment == "Does something"


class TestParserExpressions:
    def test_integer_literal(self):
        source = 'transforms f() Integer\n    from\n        42\n'
        decl = parse_decl(source)
        assert isinstance(decl.body[0], ExprStmt)
        assert isinstance(decl.body[0].expr, IntegerLit)
        assert decl.body[0].expr.value == "42"

    def test_decimal_literal(self):
        source = 'transforms f() Decimal\n    from\n        3.14\n'
        decl = parse_decl(source)
        assert isinstance(decl.body[0].expr, DecimalLit)

    def test_string_literal(self):
        source = 'transforms f() String\n    from\n        "hello"\n'
        decl = parse_decl(source)
        assert isinstance(decl.body[0].expr, StringLit)
        assert decl.body[0].expr.value == "hello"

    def test_boolean_literal(self):
        source = 'transforms f() Boolean\n    from\n        true\n'
        decl = parse_decl(source)
        assert isinstance(decl.body[0].expr, BooleanLit)
        assert decl.body[0].expr.value is True

    def test_binary_ops(self):
        source = 'transforms f() Integer\n    from\n        1 + 2\n'
        decl = parse_decl(source)
        expr = decl.body[0].expr
        assert isinstance(expr, BinaryExpr)
        assert expr.op == "+"

    def test_precedence(self):
        source = 'transforms f() Integer\n    from\n        1 + 2 * 3\n'
        decl = parse_decl(source)
        expr = decl.body[0].expr
        # Should be 1 + (2 * 3)
        assert isinstance(expr, BinaryExpr)
        assert expr.op == "+"
        assert isinstance(expr.right, BinaryExpr)
        assert expr.right.op == "*"

    def test_pipe(self):
        source = 'transforms f() Integer\n    from\n        x |> g\n'
        decl = parse_decl(source)
        expr = decl.body[0].expr
        assert isinstance(expr, PipeExpr)

    def test_field_access(self):
        source = 'transforms f() Integer\n    from\n        x.y\n'
        decl = parse_decl(source)
        expr = decl.body[0].expr
        assert isinstance(expr, FieldExpr)
        assert expr.field == "y"

    def test_call(self):
        source = 'transforms f() Integer\n    from\n        g(1, 2)\n'
        decl = parse_decl(source)
        expr = decl.body[0].expr
        assert isinstance(expr, CallExpr)
        assert len(expr.args) == 2

    def test_namespaced_call(self):
        source = 'transforms f() Integer\n    from\n        Table.new()\n'
        decl = parse_decl(source)
        expr = decl.body[0].expr
        assert isinstance(expr, CallExpr)
        assert isinstance(expr.func, FieldExpr)
        assert isinstance(expr.func.obj, TypeIdentifierExpr)
        assert expr.func.obj.name == "Table"
        assert expr.func.field == "new"

    def test_fail_propagation(self):
        source = 'inputs f() Integer!\n    from\n        g()!\n'
        decl = parse_decl(source)
        expr = decl.body[0].expr
        assert isinstance(expr, FailPropExpr)

    def test_unary_minus(self):
        source = 'transforms f() Integer\n    from\n        -x\n'
        decl = parse_decl(source)
        expr = decl.body[0].expr
        assert isinstance(expr, UnaryExpr)
        assert expr.op == "-"

    def test_unary_not(self):
        source = 'transforms f() Boolean\n    from\n        !x\n'
        decl = parse_decl(source)
        expr = decl.body[0].expr
        assert isinstance(expr, UnaryExpr)
        assert expr.op == "!"

    def test_lambda(self):
        source = 'transforms f() Integer\n    from\n        map(xs, |x| x + 1)\n'
        decl = parse_decl(source)
        call = decl.body[0].expr
        assert isinstance(call, CallExpr)
        assert isinstance(call.args[1], LambdaExpr)
        assert call.args[1].params == ["x"]

    def test_match_expr(self):
        source = (
            'transforms f() Integer\n    from\n'
            '        match x\n            A => 1\n'
            '            B => 2\n'
        )
        decl = parse_decl(source)
        expr = decl.body[0].expr
        assert isinstance(expr, MatchExpr)
        assert len(expr.arms) == 2

    def test_list_literal(self):
        source = 'transforms f() List<Integer>\n    from\n        [1, 2, 3]\n'
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
        source = 'transforms f() Integer\n    from\n        1..10\n'
        decl = parse_decl(source)
        expr = decl.body[0].expr
        assert isinstance(expr, BinaryExpr)
        assert expr.op == ".."

    def test_index(self):
        source = 'transforms f() Integer\n    from\n        xs[0]\n'
        decl = parse_decl(source)
        expr = decl.body[0].expr
        assert isinstance(expr, IndexExpr)

    def test_regex_literal(self):
        source = 'validates f(s String)\n    from\n        check(s, /^[A-Z]+$/)\n'
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


class TestParserStatements:
    def test_var_decl_with_type(self):
        source = 'transforms f() Integer\n    from\n        x as Integer = 42\n        x\n'
        decl = parse_decl(source)
        stmt = decl.body[0]
        assert isinstance(stmt, VarDecl)
        assert stmt.name == "x"
        assert isinstance(stmt.type_expr, SimpleType)

    def test_assignment(self):
        source = 'transforms f() Integer\n    from\n        x = 42\n        x\n'
        decl = parse_decl(source)
        stmt = decl.body[0]
        assert isinstance(stmt, Assignment)
        assert stmt.target == "x"

    def test_expression_statement(self):
        source = 'transforms f() Integer\n    from\n        g()\n'
        decl = parse_decl(source)
        stmt = decl.body[0]
        assert isinstance(stmt, ExprStmt)


class TestParserImplicitMatch:
    def test_inputs_implicit_match(self):
        source = (
            'inputs request(route Route) Response!\n'
            '    from\n'
            '        Get("/health") => ok("healthy")\n'
            '        _ => not_found()\n'
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
            'inputs request(route Route, db Database) Response!\n'
            '    from\n'
            '        user as User = authenticate()!\n'
            '        Get("/health") => ok("healthy")\n'
            '        _ => not_found()\n'
        )
        decl = parse_decl(source)
        # First should be VarDecl, then MatchExpr
        assert isinstance(decl.body[0], VarDecl)
        assert isinstance(decl.body[1], MatchExpr)


class TestParserConstants:
    def test_simple_constant(self):
        source = '  MAX_SIZE as Integer = 100\n'
        decl = parse_module_constant(source)
        assert isinstance(decl, ConstantDef)
        assert decl.name == "MAX_SIZE"
        assert isinstance(decl.type_expr, SimpleType)

    def test_comptime_constant(self):
        source = (
            '  MAX_CONNECTIONS as Integer = comptime\n'
            '    match target\n        "embedded" => 16\n'
            '        _ => 1024\n'
        )
        decl = parse_module_constant(source)
        assert isinstance(decl, ConstantDef)
        assert isinstance(decl.value, ComptimeExpr)


class TestParserModules:
    def test_module_decl(self):
        source = 'module Auth\n  temporal: authenticate -> authorize -> access\n'
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
        source = 'module Foo\n  String contains length\n'
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
        source = 'module Foo\n  InputOutput types ExitCode, inputs console\n'
        decl = parse_decl(source)
        assert isinstance(decl, ModuleDecl)
        assert len(decl.imports) == 1
        imp = decl.imports[0]
        assert imp.module == "InputOutput"
        assert len(imp.items) == 2
        assert imp.items[0].verb == "types"
        assert imp.items[0].name == "ExitCode"
        assert imp.items[1].verb == "inputs"
        assert imp.items[1].name == "console"

    def test_import_with_verb(self):
        source = 'module Foo\n  Auth validates login, transforms login\n'
        decl = parse_decl(source)
        assert isinstance(decl, ModuleDecl)
        assert len(decl.imports) == 1
        imp = decl.imports[0]
        assert imp.items[0].verb == "validates"
        assert imp.items[0].name == "login"
        assert imp.items[1].verb == "transforms"
        assert imp.items[1].name == "login"

    def test_import_verb_group(self):
        source = 'module Foo\n  InputOutput outputs console file, inputs console file\n'
        decl = parse_decl(source)
        assert isinstance(decl, ModuleDecl)
        assert len(decl.imports) == 1
        imp = decl.imports[0]
        assert imp.module == "InputOutput"
        assert len(imp.items) == 4
        assert imp.items[0] == ImportItem("outputs", "console", imp.items[0].span)
        assert imp.items[1] == ImportItem("outputs", "file", imp.items[1].span)
        assert imp.items[2] == ImportItem("inputs", "console", imp.items[2].span)
        assert imp.items[3] == ImportItem("inputs", "file", imp.items[3].span)

    def test_invariant_network(self):
        source = '  invariant_network Accounting\n    total >= 0\n'
        decl = parse_module_invariant(source)
        assert isinstance(decl, InvariantNetwork)
        assert decl.name == "Accounting"
        assert len(decl.constraints) >= 1


class TestParserAIResistance:
    def test_why_not_chosen(self):
        source = (
            'transforms evict(cache Cache) Option<Product>\n'
            '    why_not: "FIFO bad"\n'
            '    chosen: "LFU because reasons"\n'
            '    from\n'
            '        cache\n'
        )
        decl = parse_decl(source)
        assert isinstance(decl, FunctionDef)
        assert len(decl.why_not) == 1
        assert decl.chosen is not None

    def test_near_miss(self):
        source = (
            'validates wholesale(quantity Integer)\n'
            '    near_miss: 10 => false\n'
            '    near_miss: 11 => true\n'
            '    from\n'
            '        quantity\n'
        )
        decl = parse_decl(source)
        assert isinstance(decl, FunctionDef)
        assert len(decl.near_misses) == 2

    def test_epistemic_annotations(self):
        source = (
            'transforms process(order Order) Receipt\n'
            '    know: len(order) > 0\n'
            '    assume: order\n'
            '    believe: order\n'
            '    from\n'
            '        order\n'
        )
        decl = parse_decl(source)
        assert len(decl.know) == 1
        assert len(decl.assume) == 1
        assert len(decl.believe) == 1


class TestParserIntegration:
    def test_parse_hello_main(self):
        """Parse the hello world example."""
        source = (
            '/// Hello from Prove!\n'
            'main() Result<Unit, Error>!\n'
            '    from\n'
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
        hello = Path(__file__).resolve().parent.parent / "examples/hello/src/main.prv"
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
            'module M\n'
            '  type Port is Integer where 1..65535\n'
            '\n'
            'validates valid_port(p Integer)\n'
            '    from\n'
            '        p >= 1 && p <= 65535\n'
        )
        mod = parse(source)
        assert len(mod.declarations) == 2
        assert isinstance(mod.declarations[0], ModuleDecl)
        assert len(mod.declarations[0].types) == 1
        assert isinstance(mod.declarations[1], FunctionDef)
