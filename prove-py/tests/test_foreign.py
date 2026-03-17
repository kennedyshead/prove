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


# ── Formatter tests ───────────────────────────────────────────────


class TestForeignFormatter:
    def test_foreign_block_roundtrip(self):
        from prove.formatter import ProveFormatter

        source = (
            'module Math\n'
            '\n'
            '  foreign "libm"\n'
            '    sqrt(x Float) Float\n'
            '    pow(base Float, exp Float) Float\n'
        )
        module = _parse(source)
        formatter = ProveFormatter()
        result = formatter.format(module)
        assert result.rstrip("\n") == source.rstrip("\n")

    def test_multiple_foreign_blocks_roundtrip(self):
        from prove.formatter import ProveFormatter

        source = (
            'module Sys\n'
            '\n'
            '  foreign "libm"\n'
            '    sqrt(x Float) Float\n'
            '\n'
            '  foreign "libpthread"\n'
            '    pthread_self() Integer\n'
        )
        module = _parse(source)
        formatter = ProveFormatter()
        result = formatter.format(module)
        assert result.rstrip("\n") == source.rstrip("\n")

    def test_foreign_with_function_roundtrip(self):
        from prove.formatter import ProveFormatter

        source = (
            'module Math\n'
            '  foreign "libm"\n'
            '    sqrt(x Float) Float\n'
            '\n'
            'transforms root(x Float) Float\n'
            'from\n'
            '    sqrt(x)\n'
        )
        module, symbols, checker = _check(source)
        assert not checker.has_errors()
        formatter = ProveFormatter(symbols=symbols)
        result = formatter.format(module)
        assert 'foreign "libm"' in result
        assert "sqrt(x Float) Float" in result


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


# ── Header emission tests ────────────────────────────────────────


class TestForeignHeaders:
    def test_python3_header_included(self):
        source = (
            'module PyBind\n'
            '  foreign "libpython3"\n'
            '    pyinit() Integer\n'
        )
        c_code = _emit(source)
        assert "#include <Python.h>" in c_code

    def test_jvm_header_included(self):
        source = (
            'module JvmBind\n'
            '  foreign "libjvm"\n'
            '    createvm() Integer\n'
        )
        c_code = _emit(source)
        assert "#include <jni.h>" in c_code


# ── pkg-config resolution tests ──────────────────────────────────


class TestResolveForeignFlags:
    def test_pkg_config_success(self):
        from unittest.mock import MagicMock, patch

        from prove.builder import _resolve_foreign_flags

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "-I/usr/include/python3.12 -lpython3.12\n"

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            c_flags, l_flags = _resolve_foreign_flags("libpython3")
            mock_run.assert_called_once_with(
                ["pkg-config", "--cflags", "--libs", "python3-embed"],
                capture_output=True,
                text=True,
                timeout=5,
            )
        assert c_flags == ["-I/usr/include/python3.12"]
        assert l_flags == ["-lpython3.12"]

    def test_pkg_config_failure_falls_back(self):
        from unittest.mock import MagicMock, patch

        from prove.builder import _resolve_foreign_flags

        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""

        with patch("subprocess.run", return_value=mock_result):
            c_flags, l_flags = _resolve_foreign_flags("libpython3")
        assert c_flags == []
        assert l_flags == ["-lpython3"]

    def test_pkg_config_not_found_falls_back(self):
        from unittest.mock import patch

        from prove.builder import _resolve_foreign_flags

        with patch("subprocess.run", side_effect=FileNotFoundError):
            c_flags, l_flags = _resolve_foreign_flags("libjvm")
        assert c_flags == []
        assert l_flags == ["-ljvm"]

    def test_unknown_library_plain_link(self):
        from prove.builder import _resolve_foreign_flags

        c_flags, l_flags = _resolve_foreign_flags("libcurl")
        assert c_flags == []
        assert l_flags == ["-lcurl"]

    def test_library_without_lib_prefix(self):
        from prove.builder import _resolve_foreign_flags

        c_flags, l_flags = _resolve_foreign_flags("zlib")
        assert c_flags == []
        assert l_flags == ["-lzlib"]

    def test_env_vars_override_pkg_config(self, monkeypatch):
        from prove.builder import _resolve_foreign_flags

        monkeypatch.setenv(
            "PROVE_PYTHON_CFLAGS",
            "-I/opt/homebrew/opt/python@3.13/include/python3.13",
        )
        monkeypatch.setenv(
            "PROVE_PYTHON_LDFLAGS",
            "-L/opt/homebrew/lib -lpython3.13 -ldl",
        )
        c_flags, l_flags = _resolve_foreign_flags("libpython3")
        assert c_flags == ["-I/opt/homebrew/opt/python@3.13/include/python3.13"]
        assert l_flags == ["-L/opt/homebrew/lib", "-lpython3.13", "-ldl"]

    def test_env_vars_partial_cflags_only(self, monkeypatch):
        from prove.builder import _resolve_foreign_flags

        monkeypatch.setenv(
            "PROVE_PYTHON_CFLAGS",
            "-I/usr/include/python3.12",
        )
        monkeypatch.delenv("PROVE_PYTHON_LDFLAGS", raising=False)
        c_flags, l_flags = _resolve_foreign_flags("libpython3")
        assert c_flags == ["-I/usr/include/python3.12"]
        assert l_flags == []

    def test_env_vars_jvm(self, monkeypatch):
        from prove.builder import _resolve_foreign_flags

        monkeypatch.setenv("PROVE_JVM_CFLAGS", "-I/usr/lib/jvm/include")
        monkeypatch.setenv("PROVE_JVM_LDFLAGS", "-L/usr/lib/jvm/lib -ljvm")
        c_flags, l_flags = _resolve_foreign_flags("libjvm")
        assert c_flags == ["-I/usr/lib/jvm/include"]
        assert l_flags == ["-L/usr/lib/jvm/lib", "-ljvm"]

    def test_empty_env_vars_fall_through(self, monkeypatch):
        """Empty env vars should not short-circuit — fall through to pkg-config."""
        from unittest.mock import MagicMock, patch

        from prove.builder import _resolve_foreign_flags

        monkeypatch.setenv("PROVE_PYTHON_CFLAGS", "")
        monkeypatch.setenv("PROVE_PYTHON_LDFLAGS", "")

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "-I/usr/include/python3.12 -lpython3.12\n"

        with patch("subprocess.run", return_value=mock_result):
            c_flags, l_flags = _resolve_foreign_flags("libpython3")
        assert c_flags == ["-I/usr/include/python3.12"]
        assert l_flags == ["-lpython3.12"]
