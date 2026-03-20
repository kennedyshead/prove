"""Rebuild the .prove/cache ML completion index.

This script is embedded as a comptime string in index.prv and executed via
PyRun_SimpleString.
"""

from __future__ import annotations

from typing import cast

# pylint: disable=invalid-name

path: str = cast(str, globals().get("path", "."))

if __name__ == "__main__":
    from pathlib import Path

    from prove.config import find_config
    from prove.lsp import _ProjectIndexer

    config_path = find_config(Path(path))
    project_dir = config_path.parent
    print("indexing...")
    indexer = _ProjectIndexer(project_dir)
    indexer.index_all_files()
    print(
        f"indexed {len(indexer._file_ngrams)} files -> {project_dir / '.prove' / 'cache'}"
    )
    raise SystemExit(0)
