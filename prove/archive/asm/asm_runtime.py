"""Compile existing C runtime files to .o for linking with ASM output."""

from __future__ import annotations

import subprocess
from pathlib import Path

from prove.c_compiler import find_c_compiler
from prove.c_runtime import copy_runtime


class AsmRuntimeError(Exception):
    """Error compiling C runtime to object files."""

    def __init__(self, message: str, stderr: str | None = None) -> None:
        super().__init__(message)
        self.stderr = stderr


def compile_runtime_objects(build_dir: Path) -> list[Path]:
    """Compile C runtime sources to .o files for linking with ASM.

    Returns list of .o file paths.
    """
    # Copy runtime C sources
    runtime_c_files = copy_runtime(build_dir)
    runtime_dir = build_dir / "runtime"

    cc = find_c_compiler()
    if cc is None:
        raise AsmRuntimeError("no C compiler found (needed for runtime .o files)")

    object_files: list[Path] = []
    for c_file in runtime_c_files:
        o_file = c_file.with_suffix(".o")
        if o_file.exists() and o_file.stat().st_mtime >= c_file.stat().st_mtime:
            object_files.append(o_file)
            continue

        cmd = [
            cc, "-c", str(c_file),
            "-o", str(o_file),
            f"-I{runtime_dir}",
            "-O2",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise AsmRuntimeError(
                f"failed to compile {c_file.name}",
                stderr=result.stderr,
            )
        object_files.append(o_file)

    return object_files
