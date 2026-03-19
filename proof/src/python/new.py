"""Create a new scaffold project for prove through python.

This script is embedded as a comptime string in new.prv and executed via
PyRun_SimpleString. The caller (py_set_string) must inject the following
variable into __main__ before running this script:

  name  (str) — project name / directory to create
"""

from __future__ import annotations
from typing import cast

# pylint: disable=invalid-name

name: str = cast(str, globals().get("name", ""))

if __name__ == "__main__":
    import shutil
    from pathlib import Path

    _PROVE_TOML = """\
[package]
name = "{name}"
version = "0.1.0"
authors = []
license = ""

[build]
target = "native"
optimize = true
mutate = true
debug = false

[test]
property_rounds = 1000

[style]
line_length = 90
"""

    _MAIN_PRV = """\
module Main
  narrative: \"\"\"A new Prove project.\"\"\"
  System outputs console

main() Result<Unit, Error>!
from
    console("Hello from Prove!")
"""

    _INTENT = """\
project {name}
  purpose: A new Prove project

  module Main
    outputs greeting to console
"""

    _GITIGNORE = """\
build/
dist/
__pycache__/
.prove/
"""

    base = Path.cwd()
    project_dir = base / name

    if project_dir.exists():
        raise FileExistsError(f"Directory '{name}' already exists")

    src_dir = project_dir / "src"
    src_dir.mkdir(parents=True)
    (project_dir / ".prove").mkdir()

    _ = (project_dir / "prove.toml").write_text(_PROVE_TOML.format(name=name))
    _ = (src_dir / "main.prv").write_text(_MAIN_PRV)
    _ = (project_dir / "project.intent").write_text(_INTENT.format(name=name))
    _ = (project_dir / ".gitignore").write_text(_GITIGNORE)

    for candidate in [
        Path(__file__).parent.parent.parent / "LICENSE",
        base / "LICENSE",
    ]:
        if candidate.is_file():
            _ = shutil.copy2(candidate, project_dir / "LICENSE")
            break

    raise SystemExit(0)
