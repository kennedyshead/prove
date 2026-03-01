"""Tests for the x86-64 code generation backend."""

from prove.asm_x86_64 import X86_64Codegen


class TestX86Prologue:
    def test_prologue_emits_frame(self):
        cg = X86_64Codegen()
        cg.emit_prologue("my_func", 32)
        out = cg.output()
        assert "my_func:" in out
        assert "pushq %rbp" in out
        assert "movq %rsp, %rbp" in out
        assert "subq $32, %rsp" in out

    def test_prologue_aligns_16(self):
        cg = X86_64Codegen()
        cg.emit_prologue("f", 10)
        out = cg.output()
        assert "subq $16, %rsp" in out

    def test_epilogue(self):
        cg = X86_64Codegen()
        cg.emit_epilogue()
        out = cg.output()
        assert "movq %rbp, %rsp" in out
        assert "popq %rbp" in out
        assert "ret" in out


class TestX86LoadStore:
    def test_load_imm_small(self):
        cg = X86_64Codegen()
        cg.emit_load_imm(42)
        out = cg.output()
        assert "movq $42, %rax" in out

    def test_load_imm_large(self):
        cg = X86_64Codegen()
        cg.emit_load_imm(2**40)
        out = cg.output()
        assert "movabsq" in out

    def test_load_local(self):
        cg = X86_64Codegen()
        cg.emit_load_local(-8)
        out = cg.output()
        assert "movq -8(%rbp), %rax" in out

    def test_store_local(self):
        cg = X86_64Codegen()
        cg.emit_store_local(-16)
        out = cg.output()
        assert "movq %rax, -16(%rbp)" in out


class TestX86Arithmetic:
    def test_add(self):
        cg = X86_64Codegen()
        cg.emit_arith("+")
        out = cg.output()
        assert "addq" in out

    def test_sub(self):
        cg = X86_64Codegen()
        cg.emit_arith("-")
        out = cg.output()
        assert "subq" in out

    def test_mul(self):
        cg = X86_64Codegen()
        cg.emit_arith("*")
        out = cg.output()
        assert "imulq" in out

    def test_div(self):
        cg = X86_64Codegen()
        cg.emit_arith("/")
        out = cg.output()
        assert "idivq" in out
        assert "cqto" in out

    def test_mod(self):
        cg = X86_64Codegen()
        cg.emit_arith("%")
        out = cg.output()
        assert "idivq" in out
        assert "movq %rdx, %rax" in out

    def test_negate(self):
        cg = X86_64Codegen()
        cg.emit_negate()
        out = cg.output()
        assert "negq %rax" in out


class TestX86Compare:
    def test_equal(self):
        cg = X86_64Codegen()
        cg.emit_compare("==")
        out = cg.output()
        assert "cmpq" in out
        assert "sete" in out
        assert "movzbq" in out

    def test_less_than(self):
        cg = X86_64Codegen()
        cg.emit_compare("<")
        out = cg.output()
        assert "setl" in out

    def test_greater_equal(self):
        cg = X86_64Codegen()
        cg.emit_compare(">=")
        out = cg.output()
        assert "setge" in out


class TestX86Control:
    def test_branch(self):
        cg = X86_64Codegen()
        cg.emit_branch(".L1")
        out = cg.output()
        assert "jmp .L1" in out

    def test_branch_if_zero(self):
        cg = X86_64Codegen()
        cg.emit_branch_if_zero(".L2")
        out = cg.output()
        assert "testq %rax, %rax" in out
        assert "jz .L2" in out

    def test_call(self):
        cg = X86_64Codegen()
        cg.emit_call("prove_println", 1)
        out = cg.output()
        assert "call prove_println" in out

    def test_not(self):
        cg = X86_64Codegen()
        cg.emit_not()
        out = cg.output()
        assert "sete" in out


class TestX86String:
    def test_load_string(self):
        cg = X86_64Codegen()
        cg.emit_load_string(".str1")
        out = cg.output()
        assert "leaq .str1(%rip), %rdi" in out

    def test_global(self):
        cg = X86_64Codegen()
        cg.emit_global("main")
        out = cg.output()
        assert ".globl main" in out


class TestX86FullFunction:
    def test_simple_function(self):
        """Generate a complete simple function and verify structure."""
        cg = X86_64Codegen()
        cg.emit_text_section()
        cg.emit_global("my_func")
        cg.emit_prologue("my_func", 16)
        cg.emit_load_imm(42)
        cg.emit_epilogue()
        out = cg.output()
        assert ".text" in out
        assert ".globl my_func" in out
        assert "my_func:" in out
        assert "pushq %rbp" in out
        assert "$42" in out
        assert "ret" in out
