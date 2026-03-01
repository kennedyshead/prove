"""Copy bundled C runtime files to a build directory."""

from __future__ import annotations

import importlib.resources
import shutil
from pathlib import Path

_RUNTIME_FILES = [
    "prove_runtime.h",
    "prove_runtime.c",
    "prove_arena.h",
    "prove_arena.c",
    "prove_hash.h",
    "prove_hash.c",
    "prove_intern.h",
    "prove_intern.c",
    "prove_string.h",
    "prove_string.c",
    "prove_list.h",
    "prove_list.c",
    "prove_hof.h",
    "prove_hof.c",
    "prove_option.h",
    "prove_result.h",
    "prove_character.h",
    "prove_character.c",
    "prove_text.h",
    "prove_text.c",
    "prove_table.h",
    "prove_table.c",
]


def copy_runtime(build_dir: Path) -> list[Path]:
    """Copy bundled runtime files to *build_dir*/runtime/.

    Returns the list of .c files (needed for compilation).
    """
    dest = build_dir / "runtime"
    dest.mkdir(parents=True, exist_ok=True)

    c_files: list[Path] = []

    pkg = importlib.resources.files("prove.runtime")
    for name in _RUNTIME_FILES:
        src = pkg.joinpath(name)
        dst = dest / name
        with importlib.resources.as_file(src) as src_path:
            shutil.copy2(src_path, dst)
        if name.endswith(".c"):
            c_files.append(dst)

    return c_files
