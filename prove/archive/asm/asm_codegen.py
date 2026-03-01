"""Abstract base for assembly code generation backends."""

from __future__ import annotations

from abc import ABC, abstractmethod


class AsmCodegen(ABC):
    """Abstract base class for architecture-specific ASM backends.

    Subclasses implement platform-specific instruction emission
    (register allocation, calling convention, instruction encoding).
    """

    def __init__(self) -> None:
        self._lines: list[str] = []
        self._label_counter = 0
        self._data_entries: list[str] = []

    # ── Output ────────────────────────────────────────────────

    def output(self) -> str:
        """Return the assembled source."""
        return "\n".join(self._lines) + "\n"

    def _emit(self, line: str) -> None:
        """Emit an instruction (indented)."""
        self._lines.append(f"    {line}")

    def _label(self, name: str) -> None:
        """Emit a label."""
        self._lines.append(f"{name}:")

    def _directive(self, text: str) -> None:
        """Emit an assembler directive (indented)."""
        self._lines.append(f"    {text}")

    def _raw(self, text: str) -> None:
        """Emit raw text (no indent)."""
        self._lines.append(text)

    def _comment(self, text: str) -> None:
        """Emit a comment."""
        self._lines.append(f"    # {text}")

    def new_label(self, prefix: str = ".L") -> str:
        """Generate a unique label name."""
        self._label_counter += 1
        return f"{prefix}{self._label_counter}"

    # ── Data section ──────────────────────────────────────────

    def add_string_data(self, label: str, value: str) -> None:
        """Register a string constant for the data section."""
        escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
        self._data_entries.append(f'{label}:\n    .asciz "{escaped}"')

    def emit_data_section(self) -> None:
        """Emit the .data / .rodata section with all registered data."""
        if not self._data_entries:
            return
        self._raw("")
        self._directive(".section .rodata")
        for entry in self._data_entries:
            self._raw(entry)

    # ── Abstract methods ─────────────────────────────────────

    @abstractmethod
    def emit_prologue(self, name: str, stack_size: int) -> None:
        """Emit function prologue (push frame, allocate locals)."""
        ...

    @abstractmethod
    def emit_epilogue(self) -> None:
        """Emit function epilogue (restore frame, ret)."""
        ...

    @abstractmethod
    def emit_load_imm(self, value: int) -> None:
        """Load an immediate integer into the result register."""
        ...

    @abstractmethod
    def emit_load_local(self, offset: int) -> None:
        """Load a local variable from stack into the result register."""
        ...

    @abstractmethod
    def emit_store_local(self, offset: int) -> None:
        """Store the result register into a local variable on stack."""
        ...

    @abstractmethod
    def emit_call(self, name: str, arg_count: int) -> None:
        """Emit a function call. Args assumed to be in ABI registers."""
        ...

    @abstractmethod
    def emit_ret(self) -> None:
        """Emit a return instruction."""
        ...

    @abstractmethod
    def emit_push_result(self) -> None:
        """Push the result register onto the stack."""
        ...

    @abstractmethod
    def emit_pop_arg(self, arg_index: int) -> None:
        """Pop a value from stack into an argument register."""
        ...

    @abstractmethod
    def emit_branch(self, label: str) -> None:
        """Emit an unconditional branch."""
        ...

    @abstractmethod
    def emit_branch_if_zero(self, label: str) -> None:
        """Branch to label if result register is zero (false)."""
        ...

    @abstractmethod
    def emit_compare(self, op: str) -> None:
        """Compare top-of-stack with result register using op.

        Leaves boolean result (0/1) in result register.
        """
        ...

    @abstractmethod
    def emit_arith(self, op: str) -> None:
        """Perform arithmetic: pop left from stack, right in result register.

        Result goes into result register.
        """
        ...

    @abstractmethod
    def emit_negate(self) -> None:
        """Negate the result register."""
        ...

    @abstractmethod
    def emit_not(self) -> None:
        """Logical NOT of the result register."""
        ...

    @abstractmethod
    def emit_load_string(self, label: str) -> None:
        """Load the address of a string constant into the result register."""
        ...

    @abstractmethod
    def emit_global(self, name: str) -> None:
        """Declare a symbol as global."""
        ...

    @abstractmethod
    def emit_text_section(self) -> None:
        """Emit the .text section directive."""
        ...
