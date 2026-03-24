"""Compile a Prove project via the Python bootstrap compiler.

This script is embedded as a comptime string in build.prv and executed via
PyRun_SimpleString.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import cast
import warnings

warnings.filterwarnings(
    "ignore", message="nltk.app.wordfreq not loaded", category=UserWarning
)
# pylint: disable=invalid-name

path: str = cast(str, globals().get("path", "."))
debug: bool = cast(bool, globals().get("debug", False))
no_mutate: bool = cast(bool, globals().get("no_mutate", False))

if __name__ == "__main__":
    from prove._build_runner import mutate
    from prove.builder import build_project
    from prove.config import load_config
    from prove.errors import DiagnosticRenderer

    project_dir: Path = Path(path)
    config = load_config(project_dir / "prove.toml")

    # Override with CLI-injected values
    config.build.debug = debug
    config.build.mutate = not no_mutate

    result = build_project(project_dir, config, debug=debug)
    renderer = DiagnosticRenderer(color=True)

    for diag in result.diagnostics:
        _ = sys.stderr.write(renderer.render(diag) + "\n")

    if not result.ok:
        if result.c_error:
            _ = sys.stderr.write(f"error: {result.c_error}\n")
        raise SystemExit(1)
    if config.build.mutate:
        mutate(project_dir)
    raise SystemExit(0)
