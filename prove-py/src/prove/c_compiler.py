"""Invoke a C compiler to produce a native binary."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


class CompileCError(Exception):
    """Raised when the C compiler fails."""

    def __init__(self, message: str, stderr: str = "") -> None:
        self.stderr = stderr
        super().__init__(message)


def find_c_compiler() -> str | None:
    """Search PATH for a C compiler (gcc, cc, clang)."""
    for name in ("gcc", "cc", "clang"):
        if shutil.which(name):
            return name
    return None


def compile_c(
    c_files: list[Path],
    output: Path,
    *,
    compiler: str | None = None,
    optimize: bool = False,
    extra_flags: list[str] | None = None,
    include_dirs: list[Path] | None = None,
) -> Path:
    """Compile a list of .c files into a native binary.

    Returns the output path on success; raises CompileCError on failure.
    """
    cc = compiler or find_c_compiler()
    if cc is None:
        raise CompileCError("no C compiler found (install gcc or clang)")

    cmd: list[str] = [cc]

    # Optimization
    cmd.append("-O2" if optimize else "-O0")

    # Warnings
    cmd.extend(["-Wall", "-Wextra", "-Wno-unused-parameter"])

    # Include dirs
    if include_dirs:
        for d in include_dirs:
            cmd.extend(["-I", str(d)])

    # Source files
    cmd.extend(str(f) for f in c_files)

    # Output
    cmd.extend(["-o", str(output)])

    # Extra flags
    if extra_flags:
        cmd.extend(extra_flags)

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except FileNotFoundError:
        raise CompileCError(f"C compiler '{cc}' not found")
    except subprocess.TimeoutExpired:
        raise CompileCError("C compilation timed out")

    if result.returncode != 0:
        raise CompileCError(
            f"C compilation failed (exit {result.returncode})",
            stderr=result.stderr,
        )

    return output
