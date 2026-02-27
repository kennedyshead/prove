"""Project scaffolding for `prove new`."""

from __future__ import annotations

import shutil
from pathlib import Path

_PROVE_TOML_TEMPLATE = """\
[package]
name = "{name}"
version = "0.1.0"
authors = []
license = ""

[build]
target = "native"
optimize = false

[test]
property_rounds = 1000
"""

_MAIN_PRV_TEMPLATE = """\
/// Hello from Prove!
main() Result<Unit, Error>!
    from
        println("Hello from Prove!")
"""

_GITIGNORE = """\
build/
__pycache__/
.prove/
"""


def scaffold(name: str, parent: Path | None = None) -> Path:
    """Create a new Prove project directory. Returns the project path."""
    base = parent or Path.cwd()
    project_dir = base / name

    if project_dir.exists():
        raise FileExistsError(f"Directory '{name}' already exists")

    # Create directories
    src_dir = project_dir / "src"
    src_dir.mkdir(parents=True)

    # prove.toml
    (project_dir / "prove.toml").write_text(_PROVE_TOML_TEMPLATE.format(name=name))

    # src/main.prv
    (src_dir / "main.prv").write_text(_MAIN_PRV_TEMPLATE)

    # .gitignore
    (project_dir / ".gitignore").write_text(_GITIGNORE)

    # LICENSE — copy from workspace root if available
    workspace_license = Path("/workspace/LICENSE")
    if workspace_license.exists():
        shutil.copy2(workspace_license, project_dir / "LICENSE")

    return project_dir
