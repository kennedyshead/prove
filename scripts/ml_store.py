#!/usr/bin/env python3
"""Build LSP ML store files from trained JSON models.

This script delegates to prove-py/scripts/build_stores.py for the actual work.
It should be run from the repo root after ml_train.py.

Usage:
    python scripts/ml_store.py [--top-k 5]

Pipeline:
    python scripts/ml_extract.py
    python scripts/ml_train.py
    python scripts/ml_store.py
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--top-k",
        type=int,
        default=5,
        dest="top_k",
        help="Max completions per context (default: 5)",
    )
    args = parser.parse_args()

    import sys

    prove_py = _REPO_ROOT / "prove-py"
    sys.path.insert(0, str(prove_py / "src"))

    import importlib.util

    script_path = prove_py / "scripts" / "build_stores.py"
    spec = importlib.util.spec_from_file_location("build_stores", script_path)
    if spec is None or spec.loader is None:
        print("error: could not load build_stores.py")
        return
    build_stores = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(build_stores)
    build_stores.build_lsp_ml_stores(repo_root=_REPO_ROOT, top_k=args.top_k)


if __name__ == "__main__":
    main()
