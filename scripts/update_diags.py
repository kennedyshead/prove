import os
from pathlib import Path

src_dir = Path("examples/diagnostics_demo/src")
for prv in src_dir.glob("*.prv"):
    if prv.name == "main.prv":
        continue
    content = prv.read_text()
    code = prv.stem
    if "Expected diagnostics:" not in content:
        # Add a narrative block right after module decl
        lines = content.splitlines()
        if lines and lines[0].startswith("module "):
            new_lines = [
                lines[0],
                f'  narrative: """\n  Expected diagnostics: {code}\n  """',
            ] + lines[1:]
            prv.write_text("\n".join(new_lines) + "\n")
            print(f"Updated {prv.name}")
