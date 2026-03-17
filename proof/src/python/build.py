"""Compile a Prove project via the Python bootstrap compiler.

This script is embedded as a comptime string in build.prv and executed via
PyRun_SimpleString. The caller (py_set_string/py_set_bool wrappers) must
inject the following variables into __main__ before running this script:
"""

from __future__ import annotations

import sys
from pathlib import Path

# pylint: disable=invalid-name

path: str = ""

# Package
name: str = "Unknown"
version: str = "0.0.0"
authors: list[str] = []
_license: str = ""

# Build
target: str = "native"
no_mutate: bool = False
debug: bool = False
c_flags: list[str] = []
link_flags: list[str] = []
c_sources: list[str] = []
pre_build: list[list[str]] = []

# Optimize
enabled: bool = True
pgo: bool = True
strip: bool = True
tune_host: bool = True
gc_sections: bool = True

# Test
property_rounds: int = 1000

# Style
line_length: int = 90

if __name__ == "__main__":
    from prove._build_runner import mutate
    from prove.builder import build_project
    from prove.config import (
        BuildConfig,
        PackageConfig,
        ProveConfig,
        StyleConfig,
        TestConfig,
        OptimizeConfig,
    )
    import prove.nlp as nlp_mod

    config = ProveConfig(
        package=PackageConfig(
            name=name, version=version, authors=authors, license=_license
        ),
        build=BuildConfig(
            target=target,
            mutate=not no_mutate,
            debug=debug,
            c_flags=c_flags,
            link_flags=link_flags,
            c_sources=c_sources,
            pre_build=pre_build,
        ),
        optimize=OptimizeConfig(
            enabled=enabled,
            pgo=pgo,
            strip=strip,
            tune_host=tune_host,
            gc_sections=gc_sections,
        ),
        test=TestConfig(property_rounds=property_rounds),
        style=StyleConfig(line_length=line_length),
    )

    if not nlp_mod.has_nlp_backend():
        _ = sys.stderr.write(
            (
                "info: NLP not available \u2014 run `prove setup` for improved"
                " narrative analysis.\n"
            )
        )
    project_dir: Path = Path(path)
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
