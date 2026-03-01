"""Assembler and linker invocation for the ASM backend."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


class CompileAsmError(Exception):
    """Error during assembly or linking."""

    def __init__(self, message: str, stderr: str | None = None) -> None:
        super().__init__(message)
        self.stderr = stderr


def find_assembler() -> str | None:
    """Find an assembler (GAS via gcc/as)."""
    for name in ("gcc", "cc", "as"):
        if shutil.which(name):
            return name
    return None


def find_linker() -> str | None:
    """Find a linker."""
    for name in ("gcc", "cc", "ld"):
        if shutil.which(name):
            return name
    return None


def assemble(
    asm_file: Path,
    output: Path,
    assembler: str = "gcc",
) -> None:
    """Assemble a .s file to a .o object file."""
    cmd = [assembler, "-c", str(asm_file), "-o", str(output)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise CompileAsmError(
            f"assembly failed: {asm_file}",
            stderr=result.stderr,
        )


def link(
    object_files: list[Path],
    output: Path,
    linker: str = "gcc",
    extra_flags: list[str] | None = None,
) -> None:
    """Link object files into a binary."""
    cmd = [linker]
    cmd.extend(str(f) for f in object_files)
    cmd.extend(["-o", str(output)])
    if extra_flags:
        cmd.extend(extra_flags)
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise CompileAsmError(
            f"linking failed: {output}",
            stderr=result.stderr,
        )
