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

[style]
line_length = 90
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

_README_TEMPLATE = """\
# {name}

A [Prove](https://prove-lang.org) project.

## Build

```bash
prove build
```

## Test

```bash
prove test
```
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

    # README.md
    (project_dir / "README.md").write_text(_README_TEMPLATE.format(name=name))

    # LICENSE — copy from package or workspace if available
    license_src = _find_license()
    if license_src is not None:
        shutil.copy2(license_src, project_dir / "LICENSE")

    return project_dir


def _find_license() -> Path | None:
    """Find a LICENSE file to copy into new projects."""
    # Try package-relative paths first, then workspace root
    candidates = [
        Path(__file__).parent.parent.parent / "LICENSE",  # src/../LICENSE
        Path.cwd() / "LICENSE",
    ]
    for p in candidates:
        if p.is_file():
            return p
    return None
