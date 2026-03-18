"""Compile a Prove project via the Python bootstrap compiler.

This script is embedded as a comptime string in build.prv and executed via
PyRun_SimpleString. The caller (py_set_string/py_set_bool wrappers) must
inject the following variables into __main__ before running this script:

  path      (str)  — project directory
  debug     (bool) — enable debug build
  no_mutate (bool) — skip mutation testing
"""

from __future__ import annotations

import sys
from pathlib import Path

# pylint: disable=invalid-name

# Injected by pybuild() via py_set_string / py_set_bool
path: str = ""
debug: bool = False
no_mutate: bool = False

if __name__ == "__main__":
    from prove._build_runner import mutate
    from prove.builder import build_project
    from prove.config import load_config
    import prove.nlp as nlp_mod

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
