#!/usr/bin/env python3
"""Export syntax highlighting definitions to companion lexer projects.

Reads canonical keyword/type lists from the Prove compiler and writes
them into tree-sitter-prove, pygments-prove, and chroma-lexer-prove
using sentinel comments (PROVE-EXPORT-BEGIN/END markers).

Usage:
    python scripts/export-lexers.py [--build] [--target treesitter|pygments|chroma]

Run from the workspace root. Expects companion projects as siblings
of prove-py/:

    workspace/
      prove-py/
      tree-sitter-prove/
      pygments-prove/
      chroma-lexer-prove/
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Ensure prove-py is importable
WORKSPACE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WORKSPACE / "prove-py" / "src"))

from prove.export import (  # noqa: E402
    build_chroma,
    build_pygments,
    build_treesitter,
    generate_chroma,
    generate_pygments,
    generate_treesitter,
    read_canonical_lists,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export syntax highlighting definitions to lexer projects.",
    )
    parser.add_argument(
        "--build", action="store_true",
        help="Run build steps after generating (tree-sitter generate, pip install, go build).",
    )
    parser.add_argument(
        "--target", choices=["treesitter", "pygments", "chroma"],
        help="Only export to a specific target (default: all).",
    )
    args = parser.parse_args()

    lists = read_canonical_lists()
    targets = [args.target] if args.target else ["treesitter", "pygments", "chroma"]

    for target in targets:
        if target == "treesitter":
            print("export: tree-sitter-prove")
            ok = generate_treesitter(lists, WORKSPACE)
            if ok and args.build:
                build_treesitter(WORKSPACE)

        elif target == "pygments":
            print("export: pygments-prove")
            ok = generate_pygments(lists, WORKSPACE)
            if ok and args.build:
                build_pygments(WORKSPACE)

        elif target == "chroma":
            print("export: chroma-lexer-prove")
            ok = generate_chroma(lists, WORKSPACE)
            if ok and args.build:
                build_chroma(WORKSPACE)


if __name__ == "__main__":
    main()
