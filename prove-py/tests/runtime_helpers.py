"""Shared helpers for C runtime tests."""

from __future__ import annotations

import subprocess
from pathlib import Path

from prove.c_compiler import find_c_compiler


def compile_and_run(
    runtime_dir: Path,
    tmp_path: Path,
    c_code: str,
    *,
    name: str = "test",
    extra_flags: list[str] | None = None,
    args: list[str] | None = None,
) -> subprocess.CompletedProcess:
    """Compile a C test program against the runtime and run it."""
    src = tmp_path / f"{name}.c"
    src.write_text(c_code)
    binary = tmp_path / name
    cc = find_c_compiler()
    assert cc is not None

    runtime_c = sorted(runtime_dir.glob("*.c"))
    cmd = [
        cc, "-O0", "-Wall", "-Wextra", "-Wno-unused-parameter",
        "-I", str(runtime_dir),
        str(src), *[str(f) for f in runtime_c],
        "-o", str(binary),
        "-lm",
    ]
    if extra_flags:
        cmd.extend(extra_flags)
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, f"Compile failed:\n{result.stderr}"

    run_cmd = [str(binary)] + (args or [])
    return subprocess.run(run_cmd, capture_output=True, text=True, timeout=10)
