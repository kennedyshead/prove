"""Tests for the foreign block (C FFI) feature."""

from prove.ast_nodes import ForeignBlock, ModuleDecl
from prove.c_emitter import CEmitter
from prove.checker import Checker
from prove.lexer import Lexer
from prove.parser import Parser


def _parse(source: str):
    """Parse a Prove source string into a Module AST."""
    tokens = Lexer(source, "<test>").lex()
    return Parser(tokens, "<test>").parse()


def _check(source: str):
    """Parse and check a Prove source string."""
    module = _parse(source)
    checker = Checker()
    symbols = checker.check(module)
    return module, symbols, checker


def _emit(source: str) -> str:
    """Parse, check, and emit C for a Prove source string."""
    module, symbols, checker = _check(source)
    assert not checker.has_errors(), [d.message for d in checker.diagnostics]
    emitter = CEmitter(module, symbols)
    return emitter.emit()


# ── Parser tests ──────────────────────────────────────────────────


class TestForeignParser:
    def test_foreign_block_parses(self):
        source = (
            'module Math\n'
            '  foreign "libm"\n'
            '    sqrt(x Float) Float\n'
            '    pow(base Float, exp Float) Float\n'
        )
        module = _parse(source)
        mod_decl = module.declarations[0]
        assert isinstance(mod_decl, ModuleDecl)
        assert len(mod_decl.foreign_blocks) == 1
        fb = mod_decl.foreign_blocks[0]
        assert isinstance(fb, ForeignBlock)
        assert fb.library == "libm"
        assert len(fb.functions) == 2
        assert fb.functions[0].name == "sqrt"
        assert len(fb.functions[0].params) == 1
        assert fb.functions[1].name == "pow"
        assert len(fb.functions[1].params) == 2

    def test_multiple_foreign_blocks(self):
        source = (
            'module Sys\n'
            '  foreign "libm"\n'
            '    sqrt(x Float) Float\n'
            '  foreign "libpthread"\n'
            '    pthread_self() Integer\n'
        )
        module = _parse(source)
        mod_decl = module.declarations[0]
        assert isinstance(mod_decl, ModuleDecl)
        assert len(mod_decl.foreign_blocks) == 2
        assert mod_decl.foreign_blocks[0].library == "libm"
        assert mod_decl.foreign_blocks[1].library == "libpthread"

    def test_empty_foreign_block(self):
        source = (
            'module Empty\n'
            '  foreign "libtest"\n'
            '\n'
        )
        module = _parse(source)
        mod_decl = module.declarations[0]
        assert isinstance(mod_decl, ModuleDecl)
        assert len(mod_decl.foreign_blocks) == 1
        assert mod_decl.foreign_blocks[0].functions == []

    def test_foreign_with_no_return_type(self):
        source = (
            'module Sys\n'
            '  foreign "libc"\n'
            '    abort()\n'
        )
        module = _parse(source)
        fb = module.declarations[0].foreign_blocks[0]
        assert fb.functions[0].name == "abort"
        assert fb.functions[0].return_type is None


# ── Checker tests ─────────────────────────────────────────────────


class TestForeignChecker:
    def test_foreign_functions_registered(self):
        source = (
            'module Math\n'
            '  foreign "libm"\n'
            '    sqrt(x Float) Float\n'
        )
        _module, symbols, checker = _check(source)
        assert not checker.has_errors()
        sig = symbols.resolve_function(None, "sqrt", 1)
        assert sig is not None
        assert sig.name == "sqrt"

    def test_foreign_callable_from_function(self):
        source = (
            'module Math\n'
            '  foreign "libm"\n'
            '    sqrt(x Float) Float\n'
            '\n'
            'transforms root(x Float) Float\n'
            '    from\n'
            '        sqrt(x)\n'
        )
        _module, _symbols, checker = _check(source)
        assert not checker.has_errors()


# ── Emitter tests ─────────────────────────────────────────────────


class TestForeignEmitter:
    def test_direct_call_no_mangling(self):
        source = (
            'module Math\n'
            '  foreign "libm"\n'
            '    sqrt(x Float) Float\n'
            '\n'
            'transforms root(x Float) Float\n'
            '    from\n'
            '        sqrt(x)\n'
        )
        c_code = _emit(source)
        # sqrt should appear as a direct C call, not prv_sqrt or prv_None_sqrt
        assert "sqrt(x)" in c_code
        assert "prv_" not in c_code or "prv_transforms_root" in c_code

    def test_math_header_included(self):
        source = (
            'module Math\n'
            '  foreign "libm"\n'
            '    sqrt(x Float) Float\n'
        )
        c_code = _emit(source)
        assert "#include <math.h>" in c_code

    def test_multiple_libs_headers(self):
        source = (
            'module Sys\n'
            '  foreign "libm"\n'
            '    sqrt(x Float) Float\n'
            '  foreign "libpthread"\n'
            '    pthread_self() Integer\n'
        )
        c_code = _emit(source)
        assert "#include <math.h>" in c_code
        assert "#include <pthread.h>" in c_code


# ── Config tests ──────────────────────────────────────────────────


class TestForeignConfig:
    def test_c_flags_in_config(self, tmp_path):
        from prove.config import load_config

        toml_content = (
            '[package]\n'
            'name = "test"\n'
            '[build]\n'
            'c_flags = ["-I/usr/local/include"]\n'
            'link_flags = ["-L/usr/local/lib"]\n'
        )
        config_path = tmp_path / "prove.toml"
        config_path.write_text(toml_content)
        config = load_config(config_path)
        assert config.build.c_flags == ["-I/usr/local/include"]
        assert config.build.link_flags == ["-L/usr/local/lib"]

    def test_default_empty_flags(self, tmp_path):
        from prove.config import load_config

        toml_content = (
            '[package]\n'
            'name = "test"\n'
        )
        config_path = tmp_path / "prove.toml"
        config_path.write_text(toml_content)
        config = load_config(config_path)
        assert config.build.c_flags == []
        assert config.build.link_flags == []
