"""Invoke a C compiler to produce a native binary."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


class CompileCError(Exception):
    """Raised when the C compiler fails."""

    def __init__(self, message: str, stderr: str = "") -> None:
        self.stderr = stderr
        super().__init__(message)


def _compiler_family(cc: str) -> str:
    """Return 'gcc', 'clang', or 'msvc'."""
    try:
        result = subprocess.run(
            [cc, "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        output = result.stdout.lower()
        if "clang" in output:
            return "clang"
        if "gcc" in output or "gnu" in output:
            return "gcc"
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    if cc in ("cl", "cl.exe"):
        return "msvc"
    return "gcc"  # default assumption


def find_c_compiler() -> str | None:
    """Search PATH for a C compiler (gcc, cc, clang)."""
    for name in ("gcc", "cc", "clang"):
        if shutil.which(name):
            return name
    return None


def find_ccache() -> str | None:
    """Return the path to ccache if installed, else None."""
    return shutil.which("ccache")


def compile_c(
    c_files: list[Path],
    output: Path,
    *,
    compiler: str | None = None,
    optimize: bool = False,
    debug: bool = False,
    extra_flags: list[str] | None = None,
    include_dirs: list[Path] | None = None,
    pgo_phase: str | None = None,
    pgo_dir: Path | None = None,
    strip: bool = False,
    tune_host: bool = False,
    gc_sections: bool = False,
    use_ccache: bool = False,
) -> Path:
    """Compile a list of .c files into a native binary.

    pgo_phase: None (normal), "generate" (instrument), or "use" (optimize).
    pgo_dir: directory for profile data (required when pgo_phase is set).
    strip: pass -s to strip symbols (ignored in debug builds).
    tune_host: pass -march=native for host-specific tuning.
    gc_sections: enable linker dead-code elimination (ignored in debug builds).
    use_ccache: prepend ccache to the compiler command.

    Returns the output path on success; raises CompileCError on failure.
    """
    cc = compiler or find_c_compiler()
    if cc is None:
        raise CompileCError("no C compiler found (install gcc or clang)")

    cmd: list[str] = ["ccache", cc] if use_ccache else [cc]

    # Optimization
    if optimize:
        cmd.extend(["-O2", "-flto"])
    else:
        cmd.append("-O0")

    # Host-specific tuning
    if tune_host:
        cmd.append("-march=native")

    # PGO flags
    if pgo_phase and pgo_dir:
        if pgo_phase == "generate":
            cmd.append(f"-fprofile-generate={pgo_dir}")
        elif pgo_phase == "use":
            cmd.append(f"-fprofile-use={pgo_dir}")
            family = _compiler_family(cc)
            if family == "gcc":
                cmd.append("-Wno-missing-profile")

    # Debug symbols
    if debug:
        cmd.append("-g")
        cmd.append("-rdynamic")  # Export symbols for backtrace

    # Strip symbols (release only)
    if strip and not debug:
        cmd.append("-s")

    # Dead code elimination at link time (release only)
    if gc_sections and not debug:
        cmd.extend(["-ffunction-sections", "-fdata-sections"])
        if sys.platform == "darwin":
            cmd.append("-Wl,-dead_strip")
        else:
            cmd.append("-Wl,--gc-sections")

    # Warnings
    cmd.extend(["-Wall", "-Wextra", "-Wno-unused-parameter"])

    # Safety: runtime casts between void*, Prove_Header*, and concrete types
    cmd.append("-fno-strict-aliasing")

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
