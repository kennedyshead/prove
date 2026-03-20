"""Export syntax highlighting data to companion lexer projects.

This script is embedded as a comptime string in export.prv and executed via
PyRun_SimpleString.
"""

from __future__ import annotations

from typing import cast

# pylint: disable=invalid-name

fmt: str | None = cast(str, globals().get("fmt", None)) or None
build: bool = cast(bool, globals().get("build", False))
workspace_path: str | None = cast(str, globals().get("workspace_path", None)) or None

if __name__ == "__main__":
    from pathlib import Path

    from prove.export import (
        build_chroma,
        build_pygments,
        build_treesitter,
        generate_chroma,
        generate_pygments,
        generate_treesitter,
        read_canonical_lists,
    )

    if workspace_path:
        workspace = Path(workspace_path)
    else:
        import prove as _prove_pkg

        workspace = Path(_prove_pkg.__file__).resolve().parent.parent.parent.parent

    lists = read_canonical_lists()
    targets = [fmt] if fmt else ["treesitter", "pygments", "chroma"]

    for target in targets:
        if target == "treesitter":
            print("export: tree-sitter-prove")
            ok = generate_treesitter(lists, workspace)
            if ok and build:
                build_treesitter(workspace)
        elif target == "pygments":
            print("export: pygments-prove")
            ok = generate_pygments(lists, workspace)
            if ok and build:
                build_pygments(workspace)
        elif target == "chroma":
            print("export: chroma-lexer-prove")
            ok = generate_chroma(lists, workspace)
            if ok and build:
                build_chroma(workspace)
    raise SystemExit(0)
