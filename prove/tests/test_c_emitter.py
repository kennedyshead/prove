"""Tests for c_emitter — C source generation from Prove AST."""

from prove.c_emitter import CEmitter
from prove.checker import Checker
from prove.lexer import Lexer
from prove.parser import Parser


def _emit(source: str) -> str:
    """Parse, check, and emit C for a Prove source string."""
    tokens = Lexer(source, "<test>").lex()
    module = Parser(tokens, "<test>").parse()
    checker = Checker()
    symbols = checker.check(module)
    assert not checker.has_errors(), [d.message for d in checker.diagnostics]
    emitter = CEmitter(module, symbols)
    return emitter.emit()


class TestHelloWorld:
    def test_hello_world_emits(self):
        source = (
            "main() Result<Unit, Error>!\n"
            "    from\n"
            '        println("Hello from Prove!")\n'
        )
        c_code = _emit(source)
        assert "int main(" in c_code
        assert "prove_println" in c_code
        assert "Hello from Prove!" in c_code
        assert "return 0;" in c_code

    def test_includes_runtime_headers(self):
        source = (
            "main() Result<Unit, Error>!\n"
            "    from\n"
            '        println("test")\n'
        )
        c_code = _emit(source)
        assert '#include "prove_runtime.h"' in c_code
        assert '#include "prove_string.h"' in c_code


class TestVarDecl:
    def test_integer_var(self):
        source = (
            "transforms compute() Integer\n"
            "    from\n"
            "        x as Integer = 42\n"
            "        x\n"
        )
        c_code = _emit(source)
        assert "int64_t x = 42L;" in c_code

    def test_string_var(self):
        source = (
            "outputs greet()\n"
            "    from\n"
            '        name as String = "world"\n'
            "        println(name)\n"
        )
        c_code = _emit(source)
        assert "Prove_String*" in c_code
        assert 'prove_string_from_cstr("world")' in c_code


class TestBinaryExpr:
    def test_arithmetic(self):
        source = (
            "transforms compute() Integer\n"
            "    from\n"
            "        x as Integer = 1 + 2\n"
            "        x\n"
        )
        c_code = _emit(source)
        assert "(1L + 2L)" in c_code

    def test_string_concat(self):
        source = (
            "outputs greet()\n"
            "    from\n"
            '        s as String = "hello" + " world"\n'
            "        println(s)\n"
        )
        c_code = _emit(source)
        assert "prove_string_concat" in c_code


class TestFunctionDef:
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
        c_code = _emit(source)
        assert "transforms_add_Integer_Integer" in c_code
        assert "int64_t a" in c_code
        assert "int64_t b" in c_code


class TestIfExpr:
    def test_if_statement(self):
        source = (
            "main()\n"
            "    from\n"
            "        if true\n"
            '            println("yes")\n'
            "        else\n"
            '            println("no")\n'
        )
        c_code = _emit(source)
        assert "if (true)" in c_code
        assert "} else {" in c_code


class TestStringInterp:
    def test_string_interpolation(self):
        source = (
            "transforms describe(x Integer) String\n"
            "    from\n"
            '        "value is {x}"\n'
        )
        c_code = _emit(source)
        assert "prove_string_concat" in c_code
        assert "prove_string_from_int" in c_code


class TestRetainRelease:
    def test_string_var_retained(self):
        source = (
            "transforms greet(name String) String\n"
            "    from\n"
            '        msg as String = "hello"\n'
            "        msg\n"
        )
        c_code = _emit(source)
        assert "prove_retain(msg)" in c_code

    def test_pointer_released_before_return(self):
        source = (
            "outputs show()\n"
            "    from\n"
            '        s as String = "test"\n'
            "        println(s)\n"
        )
        c_code = _emit(source)
        assert "prove_release(s)" in c_code


class TestBuiltinDispatch:
    def test_to_string_integer(self):
        source = (
            "transforms show(x Integer) String\n"
            "    from\n"
            "        to_string(x)\n"
        )
        c_code = _emit(source)
        assert "prove_string_from_int" in c_code

    def test_to_string_boolean(self):
        source = (
            "transforms show(x Boolean) String\n"
            "    from\n"
            "        to_string(x)\n"
        )
        c_code = _emit(source)
        assert "prove_string_from_bool" in c_code

    def test_to_string_decimal(self):
        source = (
            "transforms show(x Decimal) String\n"
            "    from\n"
            "        to_string(x)\n"
        )
        c_code = _emit(source)
        assert "prove_string_from_double" in c_code

    def test_len_list(self):
        source = (
            "transforms count() Integer\n"
            "    from\n"
            "        len([1, 2, 3])\n"
        )
        c_code = _emit(source)
        assert "prove_list_len" in c_code

    def test_readln_emits(self):
        source = (
            "inputs get_name() String\n"
            "    from\n"
            "        readln()\n"
        )
        c_code = _emit(source)
        assert "prove_readln" in c_code

    def test_clamp_emits(self):
        source = (
            "transforms safe(x Integer) Integer\n"
            "    from\n"
            "        clamp(x, 0, 100)\n"
        )
        c_code = _emit(source)
        assert "prove_clamp" in c_code
