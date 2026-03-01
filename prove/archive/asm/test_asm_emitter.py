"""Tests for asm_emitter — x86-64 assembly generation from Prove AST."""

from prove.asm_emitter import AsmEmitter
from prove.checker import Checker
from prove.lexer import Lexer
from prove.parser import Parser


def _emit_asm(source: str) -> str:
    """Parse, check, and emit x86-64 ASM for a Prove source string."""
    tokens = Lexer(source, "<test>").lex()
    module = Parser(tokens, "<test>").parse()
    checker = Checker()
    symbols = checker.check(module)
    assert not checker.has_errors(), [d.message for d in checker.diagnostics]
    emitter = AsmEmitter(module, symbols)
    return emitter.emit()


class TestAsmHelloWorld:
    def test_hello_main(self):
        source = (
            "main() Result<Unit, Error>!\n"
            "    from\n"
            '        println("Hello from Prove!")\n'
        )
        asm = _emit_asm(source)
        assert ".text" in asm
        assert ".globl main" in asm
        assert "main:" in asm
        assert "prove_println" in asm
        assert "Hello from Prove!" in asm
        assert "ret" in asm

    def test_data_section_has_string(self):
        source = (
            "main() Result<Unit, Error>!\n"
            "    from\n"
            '        println("test string")\n'
        )
        asm = _emit_asm(source)
        assert ".rodata" in asm
        assert "test string" in asm


class TestAsmVarDecl:
    def test_integer_var(self):
        source = (
            "transforms compute() Integer\n"
            "    from\n"
            "        x as Integer = 42\n"
            "        x\n"
        )
        asm = _emit_asm(source)
        assert "$42" in asm
        assert "movq" in asm

    def test_string_var(self):
        source = (
            "outputs greet()\n"
            "    from\n"
            '        name as String = "world"\n'
            "        println(name)\n"
        )
        asm = _emit_asm(source)
        assert "prove_string_from_cstr" in asm
        assert "world" in asm


class TestAsmFunction:
    def test_simple_function(self):
        source = (
            "transforms add(a Integer, b Integer) Integer\n"
            "    from\n"
            "        a + b\n"
            "\n"
            "main()\n"
            "    from\n"
            "        println(to_string(add(1, 2)))\n"
        )
        asm = _emit_asm(source)
        # Function should be declared global and have a label
        assert "transforms_add_Integer_Integer" in asm
        # Should have prologue/epilogue
        assert "pushq %rbp" in asm
        # Should store args to locals
        assert "%rdi" in asm

    def test_function_with_return(self):
        source = (
            "transforms identity(x Integer) Integer\n"
            "    from\n"
            "        x\n"
            "\n"
            "main()\n"
            "    from\n"
            "        println(to_string(identity(5)))\n"
        )
        asm = _emit_asm(source)
        assert "transforms_identity_Integer" in asm
        assert "ret" in asm


class TestAsmBinaryExpr:
    def test_addition(self):
        source = (
            "transforms add(a Integer, b Integer) Integer\n"
            "    from\n"
            "        a + b\n"
            "\n"
            "main()\n"
            "    from\n"
            "        println(to_string(add(1, 2)))\n"
        )
        asm = _emit_asm(source)
        assert "addq" in asm

    def test_subtraction(self):
        source = (
            "transforms sub(a Integer, b Integer) Integer\n"
            "    from\n"
            "        a - b\n"
            "\n"
            "main()\n"
            "    from\n"
            "        println(to_string(sub(5, 3)))\n"
        )
        asm = _emit_asm(source)
        assert "subq" in asm

    def test_multiplication(self):
        source = (
            "transforms mul(a Integer, b Integer) Integer\n"
            "    from\n"
            "        a * b\n"
            "\n"
            "main()\n"
            "    from\n"
            "        println(to_string(mul(3, 4)))\n"
        )
        asm = _emit_asm(source)
        assert "imulq" in asm

    def test_comparison(self):
        source = (
            "transforms is_positive(n Integer) Boolean\n"
            "    from\n"
            "        n > 0\n"
            "\n"
            "main()\n"
            "    from\n"
            "        println(to_string(is_positive(5)))\n"
        )
        asm = _emit_asm(source)
        assert "cmpq" in asm
        assert "setg" in asm


class TestAsmUnaryExpr:
    def test_negate(self):
        source = (
            "transforms neg(n Integer) Integer\n"
            "    from\n"
            "        -n\n"
            "\n"
            "main()\n"
            "    from\n"
            "        println(to_string(neg(5)))\n"
        )
        asm = _emit_asm(source)
        assert "negq" in asm

    def test_not(self):
        source = (
            "transforms invert(b Boolean) Boolean\n"
            "    from\n"
            "        !b\n"
            "\n"
            "main()\n"
            "    from\n"
            "        println(to_string(invert(true)))\n"
        )
        asm = _emit_asm(source)
        assert "sete" in asm


class TestAsmCallExpr:
    def test_builtin_call(self):
        source = (
            "main()\n"
            "    from\n"
            '        println("hello")\n'
        )
        asm = _emit_asm(source)
        assert "call prove_println" in asm

    def test_user_function_call(self):
        source = (
            "transforms double(x Integer) Integer\n"
            "    from\n"
            "        x * 2\n"
            "\n"
            "main()\n"
            "    from\n"
            "        println(to_string(double(5)))\n"
        )
        asm = _emit_asm(source)
        assert "call transforms_double_Integer" in asm


class TestAsmPipeExpr:
    def test_pipe_to_builtin(self):
        source = (
            "outputs show()\n"
            "    from\n"
            '        "hello" |> println\n'
        )
        asm = _emit_asm(source)
        assert "prove_println" in asm

    def test_pipe_to_function(self):
        source = (
            "transforms double(x Integer) Integer\n"
            "    from\n"
            "        x * 2\n"
            "\n"
            "transforms compute() Integer\n"
            "    from\n"
            "        5 |> double\n"
            "\n"
            "main()\n"
            "    from\n"
            "        println(to_string(compute()))\n"
        )
        asm = _emit_asm(source)
        assert "$5" in asm


class TestAsmStringInterp:
    def test_string_interpolation(self):
        source = (
            "transforms describe(x Integer) String\n"
            "    from\n"
            '        f"value is {x}"\n'
            "\n"
            "main()\n"
            "    from\n"
            "        println(describe(42))\n"
        )
        asm = _emit_asm(source)
        assert "prove_string_concat" in asm
        assert "prove_string_from_int" in asm
        assert "value is " in asm


class TestAsmProofBranching:
    def test_two_branch_proof(self):
        source = (
            "transforms abs(n Integer) Integer\n"
            "    ensures result >= 0\n"
            "    proof\n"
            "        positive: identity when n >= 0\n"
            "        negative: deducted when n < 0\n"
            "    from\n"
            "        n\n"
            "        0 - n\n"
        )
        asm = _emit_asm(source)
        # Should have conditional branches
        assert "cmpq" in asm
        assert "jz" in asm
        assert "ret" in asm

    def test_no_condition_fallback(self):
        """Proof without when conditions falls through to regular body."""
        source = (
            "transforms identity(x Integer) Integer\n"
            "    ensures result == x\n"
            "    proof\n"
            "        trivial: x is returned unchanged\n"
            "    from\n"
            "        x\n"
        )
        asm = _emit_asm(source)
        # Should NOT have conditional jump instructions from proof
        assert "transforms_identity_Integer" in asm
        assert "ret" in asm


class TestAsmBooleanLit:
    def test_true(self):
        source = (
            "transforms yes() Boolean\n"
            "    from\n"
            "        true\n"
        )
        asm = _emit_asm(source)
        assert "$1" in asm

    def test_false(self):
        source = (
            "transforms no() Boolean\n"
            "    from\n"
            "        false\n"
        )
        asm = _emit_asm(source)
        assert "$0" in asm


class TestAsmMatchExpr:
    def test_boolean_match(self):
        """Match on boolean produces conditional branches."""
        source = (
            "transforms abs_val(n Integer) Integer\n"
            "    from\n"
            "        match n >= 0\n"
            "            true => n\n"
            "            false => 0 - n\n"
        )
        asm = _emit_asm(source)
        # Should have comparison and conditional jumps
        assert "cmpq" in asm
        assert "jz" in asm
        assert "jmp" in asm
        # Should have subtraction for the false branch
        assert "subq" in asm

    def test_wildcard_match(self):
        """Match with wildcard arm."""
        source = (
            "transforms classify(n Integer) Integer\n"
            "    from\n"
            "        match n\n"
            "            0 => 0\n"
            "            _ => 1\n"
        )
        asm = _emit_asm(source)
        assert "jmp" in asm
        assert "cmpq" in asm


class TestAsmListLiteral:
    def test_list_literal(self):
        source = (
            "transforms nums() List<Integer>\n"
            "    from\n"
            "        [10, 20, 30]\n"
        )
        asm = _emit_asm(source)
        assert "prove_list_new" in asm
        assert "prove_list_push" in asm
        assert "$10" in asm

    def test_list_index(self):
        source = (
            "transforms first() Integer\n"
            "    from\n"
            "        xs as List<Integer> = [1, 2, 3]\n"
            "        xs[0]\n"
        )
        asm = _emit_asm(source)
        assert "prove_list_get" in asm


class TestAsmFailProp:
    def test_fail_prop(self):
        source = (
            "inputs risky() Result<Integer, Error>!\n"
            "    from\n"
            "        42\n"
            "\n"
            "inputs caller() Result<Integer, Error>!\n"
            "    from\n"
            "        risky()!\n"
        )
        asm = _emit_asm(source)
        assert "prove_result_is_err" in asm
        assert "prove_result_unwrap_int" in asm


class TestAsmModuleDecl:
    def test_function_in_module(self):
        source = (
            "module Math\n"
            "    transforms add(a Integer, b Integer) Integer\n"
            "        from\n"
            "            a + b\n"
            "\n"
            "    main()\n"
            "        from\n"
            "            println(to_string(add(1, 2)))\n"
        )
        asm = _emit_asm(source)
        assert "main:" in asm
        assert "addq" in asm
