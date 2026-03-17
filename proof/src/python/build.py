"""Compile a Prove project via the Python bootstrap compiler.

This script is embedded as a comptime string in build.prv and executed via
PyRun_SimpleString. The caller (py_set_string/py_set_bool wrappers) must
inject the following variables into __main__ before running this script:

    path      (str)       – project directory, default "."
    debug     (bool|None) – compile with debug symbols; None defers to prove.toml
    no_mutate (bool)      – skip mutation testing
"""

from __future__ import annotations

import sys

from prove._build_runner import run_build

path: str = ""
debug: bool = False
no_mutate: bool = False

if __name__ == "__main__":
    import prove.nlp as nlp_mod

    if not nlp_mod.has_nlp_backend():
        _ = sys.stderr.write(
            (
                "info: NLP not available \u2014 run `prove setup` for improved"
                " narrative analysis.\n"
            )
        )

    raise SystemExit(run_build(path, debug=debug, no_mutate=no_mutate))
