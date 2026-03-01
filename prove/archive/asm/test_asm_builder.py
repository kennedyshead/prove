"""Tests for ASM build pipeline integration."""

from pathlib import Path
from unittest.mock import patch

from prove.asm_emitter import AsmEmitter
from prove.checker import Checker
from prove.lexer import Lexer
from prove.parser import Parser


def _build_asm(source: str) -> str:
    """Parse, check, and produce ASM output (unit-test level)."""
    tokens = Lexer(source, "<test>").lex()
    module = Parser(tokens, "<test>").parse()
    checker = Checker()
    symbols = checker.check(module)
    assert not checker.has_errors(), [d.message for d in checker.diagnostics]
    emitter = AsmEmitter(module, symbols)
    return emitter.emit()


class TestAsmBuildPipeline:
    def test_hello_produces_valid_asm(self):
        """The hello example should produce syntactically valid x86-64 ASM."""
        source = (
            "module Main\n"
            '    narrative: """Hello world program"""\n'
            "\n"
            "main() Result<Unit, Error>!\n"
            "    from\n"
            '        println("Hello from Prove!")\n'
        )
        asm = _build_asm(source)
        # Must have text section
        assert ".text" in asm
        # Must have main entry point
        assert ".globl main" in asm
        assert "main:" in asm
        # Must call runtime
        assert "call prove_println" in asm
        # Must have data section with string
        assert ".rodata" in asm
        assert "Hello from Prove!" in asm
        # Must have proper frame setup and teardown
        assert "pushq %rbp" in asm
        assert "movq %rsp, %rbp" in asm
        assert "ret" in asm

    def test_math_produces_function_calls(self):
        """The math example should produce proper function definitions."""
        source = (
            "transforms add(a Integer, b Integer) Integer\n"
            "    from\n"
            "        a + b\n"
            "\n"
            "main()\n"
            "    from\n"
            "        println(to_string(add(1, 2)))\n"
        )
        asm = _build_asm(source)
        assert "transforms_add_Integer_Integer:" in asm
        assert "main:" in asm
        assert "addq" in asm
        assert "call transforms_add_Integer_Integer" in asm


class TestBuildResultAsmField:
    def test_build_result_has_asm_error_field(self):
        """BuildResult should support asm_error field."""
        from prove.builder import BuildResult

        result = BuildResult(ok=False, asm_error="test error")
        assert result.asm_error == "test error"

    def test_build_result_asm_error_default_none(self):
        from prove.builder import BuildResult

        result = BuildResult(ok=True)
        assert result.asm_error is None


class TestBuildProjectAsm:
    def test_build_asm_flag(self, tmp_path: Path):
        """build_project with asm=True should produce ASM pipeline output."""
        from prove.builder import build_project
        from prove.config import PackageConfig, ProveConfig

        # Set up a minimal project
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        prv_file = src_dir / "main.prv"
        prv_file.write_text(
            "module Main\n"
            '    narrative: """test"""\n'
            "\n"
            "main() Result<Unit, Error>!\n"
            "    from\n"
            '        println("Hello from Prove!")\n'
        )
        toml_file = tmp_path / "prove.toml"
        toml_file.write_text(
            '[package]\nname = "test_asm"\nversion = "0.0.1"\n'
        )

        config = ProveConfig(package=PackageConfig(name="test_asm"))

        # Mock assembler/linker so we don't need actual tools
        with patch("prove.asm_assembler.find_assembler") as mock_asm, \
             patch("prove.asm_assembler.assemble"), \
             patch("prove.asm_assembler.link"), \
             patch("prove.asm_runtime.compile_runtime_objects") as mock_runtime:
            mock_asm.return_value = "gcc"
            mock_runtime.return_value = []
            build_project(tmp_path, config, asm=True)

        # Should have generated an .s file
        gen_dir = tmp_path / "build" / "gen"
        asm_files = list(gen_dir.glob("*.s"))
        assert len(asm_files) == 1
        asm_content = asm_files[0].read_text()
        assert ".text" in asm_content
        assert "main:" in asm_content
