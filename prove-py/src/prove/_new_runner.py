"""New project command logic — click-free.

Called by both the click CLI (cli.py) and the proof binary (via PyRun_SimpleString).
Keep this file free of click imports so it remains embeddable.
"""

from __future__ import annotations

import sys


def run_new(name: str) -> int:
    """Create a new Prove project. Returns 0 on success, 1 on failure."""
    from prove.project import scaffold

    try:
        project_dir = scaffold(name)
        print(f"created project '{name}' at {project_dir}")
        return 0
    except FileExistsError as e:
        sys.stderr.write(f"error: {e}\n")
        return 1
