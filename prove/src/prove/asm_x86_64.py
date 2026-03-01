"""x86-64 (System V AMD64 ABI) code generation backend using AT&T syntax."""

from __future__ import annotations

from prove.asm_codegen import AsmCodegen

# System V AMD64 ABI argument registers (in order)
_ARG_REGS = ["%rdi", "%rsi", "%rdx", "%rcx", "%r8", "%r9"]


class X86_64Codegen(AsmCodegen):
    """x86-64 code generator using GAS AT&T syntax."""

    def emit_text_section(self) -> None:
        self._directive(".text")

    def emit_global(self, name: str) -> None:
        self._directive(f".globl {name}")

    def emit_prologue(self, name: str, stack_size: int) -> None:
        # Align stack to 16 bytes
        aligned = (stack_size + 15) & ~15
        if aligned < 16:
            aligned = 16
        self._label(name)
        self._emit("pushq %rbp")
        self._emit("movq %rsp, %rbp")
        if aligned > 0:
            self._emit(f"subq ${aligned}, %rsp")

    def emit_epilogue(self) -> None:
        self._emit("movq %rbp, %rsp")
        self._emit("popq %rbp")
        self._emit("ret")

    def emit_load_imm(self, value: int) -> None:
        if -2147483648 <= value <= 2147483647:
            self._emit(f"movq ${value}, %rax")
        else:
            self._emit(f"movabsq ${value}, %rax")

    def emit_load_local(self, offset: int) -> None:
        self._emit(f"movq {offset}(%rbp), %rax")

    def emit_store_local(self, offset: int) -> None:
        self._emit(f"movq %rax, {offset}(%rbp)")

    def emit_load_arg(self, arg_index: int) -> None:
        """Load argument register value into %rax."""
        if arg_index < len(_ARG_REGS):
            reg = _ARG_REGS[arg_index]
            self._emit(f"movq {reg}, %rax")

    def emit_store_arg_to_local(self, arg_index: int, offset: int) -> None:
        """Store incoming argument to a local stack slot."""
        if arg_index < len(_ARG_REGS):
            reg = _ARG_REGS[arg_index]
            self._emit(f"movq {reg}, {offset}(%rbp)")

    def emit_call(self, name: str, arg_count: int) -> None:
        # Ensure 16-byte stack alignment before call
        # The call instruction pushes 8 bytes (return address).
        # We rely on prologue alignment + even number of pushes.
        self._emit(f"call {name}")

    def emit_ret(self) -> None:
        self._emit("ret")

    def emit_push_result(self) -> None:
        self._emit("pushq %rax")

    def emit_pop_arg(self, arg_index: int) -> None:
        if arg_index < len(_ARG_REGS):
            reg = _ARG_REGS[arg_index]
            self._emit(f"popq {reg}")

    def emit_branch(self, label: str) -> None:
        self._emit(f"jmp {label}")

    def emit_branch_if_zero(self, label: str) -> None:
        self._emit("testq %rax, %rax")
        self._emit(f"jz {label}")

    def emit_branch_if_nonzero(self, label: str) -> None:
        """Branch to label if %rax is nonzero (true)."""
        self._emit("testq %rax, %rax")
        self._emit(f"jnz {label}")

    def emit_compare(self, op: str) -> None:
        """Compare: pop left from stack, right in %rax.

        Result: 0 or 1 in %rax.
        """
        self._emit("movq %rax, %rcx")     # right -> rcx
        self._emit("popq %rax")            # left -> rax
        self._emit("cmpq %rcx, %rax")      # compare left with right
        # Map op to setcc instruction
        setcc = {
            "==": "sete", "!=": "setne",
            "<": "setl", ">": "setg",
            "<=": "setle", ">=": "setge",
        }.get(op, "sete")
        self._emit(f"{setcc} %al")
        self._emit("movzbq %al, %rax")

    def emit_arith(self, op: str) -> None:
        """Arithmetic: pop left from stack, right in %rax. Result in %rax."""
        if op == "+":
            self._emit("popq %rcx")
            self._emit("addq %rcx, %rax")
        elif op == "-":
            self._emit("movq %rax, %rcx")   # right
            self._emit("popq %rax")          # left
            self._emit("subq %rcx, %rax")    # left - right
        elif op == "*":
            self._emit("popq %rcx")
            self._emit("imulq %rcx, %rax")
        elif op == "/":
            self._emit("movq %rax, %rcx")   # right (divisor)
            self._emit("popq %rax")          # left (dividend)
            self._emit("cqto")               # sign-extend rax → rdx:rax
            self._emit("idivq %rcx")         # rax = quotient
        elif op == "%":
            self._emit("movq %rax, %rcx")
            self._emit("popq %rax")
            self._emit("cqto")
            self._emit("idivq %rcx")
            self._emit("movq %rdx, %rax")    # remainder in rdx
        else:
            self._comment(f"unsupported arith op: {op}")

    def emit_negate(self) -> None:
        self._emit("negq %rax")

    def emit_not(self) -> None:
        self._emit("testq %rax, %rax")
        self._emit("sete %al")
        self._emit("movzbq %al, %rax")

    def emit_load_string(self, label: str) -> None:
        self._emit(f"leaq {label}(%rip), %rdi")

    def emit_move_result_to_arg(self, arg_index: int) -> None:
        """Move %rax to argument register."""
        if arg_index < len(_ARG_REGS):
            reg = _ARG_REGS[arg_index]
            if reg != "%rax":
                self._emit(f"movq %rax, {reg}")

    def emit_load_lea(self, label: str) -> None:
        """Load effective address (RIP-relative) into %rax."""
        self._emit(f"leaq {label}(%rip), %rax")
