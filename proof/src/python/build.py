"""Compile a Prove project via the Python bootstrap compiler.

This script is embedded as a comptime string in build.prv and executed via
PyRun_SimpleString.
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

# pylint: disable=invalid-name

path: str = cast(str, globals().get("path", "."))
debug: bool = cast(bool, globals().get("debug", False))
no_mutate: bool = cast(bool, globals().get("no_mutate", False))

if __name__ == "__main__":
    from prove._build_runner import mutate
    from prove.builder import build_project
    from prove.config import load_config

    project_dir: Path = Path(path)
    config = load_config(project_dir / "prove.toml")

    # Override with CLI-injected values
    config.build.debug = debug
    config.build.mutate = not no_mutate

    result = build_project(project_dir, config, debug=debug)

    for diag in result.diagnostics:
        print(f"{diag}\n")

    if not result.ok:
        if result.c_error:
            print(f"error: {result.c_error}\n")
        raise SystemExit(1)
    if config.build.mutate:
        mutate(project_dir)
    raise SystemExit(0)
