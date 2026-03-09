#!/usr/bin/env python3
"""Validate and fix Expected diagnostics annotations in diagnostics_demo files.

Usage:
    python scripts/update_diags.py          # report issues
    python scripts/update_diags.py --fix    # auto-fix missing/wrong annotations
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

SRC_DIR = Path("examples/diagnostics_demo/src")


def check_file(prv: Path, fix: bool) -> bool:
    """Check a single .prv file. Returns True if OK (or fixed)."""
    code = prv.stem
    content = prv.read_text()

    # Check for Expected diagnostics line with correct code
    pattern = rf"Expected diagnostics:\s*{re.escape(code)}\b"
    if re.search(pattern, content):
        return True

    # File is missing or has wrong Expected diagnostics
    has_any = "Expected diagnostics:" in content

    if has_any:
        # Has the line but with wrong code
        match = re.search(r"Expected diagnostics:\s*([\w,\s]+)", content)
        existing = match.group(1).strip() if match else "?"
        print(f"  WRONG: {prv.name} — has '{existing}', expected '{code}'")
        if fix:
            content = re.sub(
                r"Expected diagnostics:\s*[\w,\s]+",
                f"Expected diagnostics: {code}",
                content,
            )
            prv.write_text(content)
            print("    -> fixed")
            return True
        return False

    # Missing entirely
    print(f"  MISSING: {prv.name} — no 'Expected diagnostics: {code}'")
    if fix:
        lines = content.splitlines()
        if lines and lines[0].startswith("module "):
            # Has module decl — add narrative after it
            has_narrative = any("narrative:" in line for line in lines)
            if has_narrative:
                # Insert into existing narrative
                for i, line in enumerate(lines):
                    if "narrative:" in line:
                        # Find the closing """ and insert before it
                        for j in range(i + 1, len(lines)):
                            if '"""' in lines[j]:
                                lines.insert(j, f"  Expected diagnostics: {code}")
                                break
                        break
            else:
                # Add new narrative block after module line
                lines.insert(1, f'  narrative: """\n  Expected diagnostics: {code}\n  """')
            prv.write_text("\n".join(lines) + "\n")
        else:
            # No module declaration (like I201.prv) — add as comment
            lines = content.splitlines()
            lines.insert(0, f"// Expected diagnostics: {code}")
            prv.write_text("\n".join(lines) + "\n")
        print("    -> fixed")
        return True
    return False


def main() -> int:
    fix = "--fix" in sys.argv

    if not SRC_DIR.is_dir():
        print(f"error: {SRC_DIR} not found (run from workspace root)")
        return 1

    prv_files = sorted(SRC_DIR.glob("*.prv"))
    if not prv_files:
        print("warning: no .prv files found")
        return 0

    print(f"Checking {len(prv_files)} files in {SRC_DIR}")
    issues = 0

    for prv in prv_files:
        if prv.name == "main.prv":
            continue
        if not check_file(prv, fix):
            issues += 1

    if issues:
        print(f"\n{issues} file(s) need attention")
        if not fix:
            print("Run with --fix to auto-repair")
        return 1
    else:
        print("All files OK")
        return 0


if __name__ == "__main__":
    sys.exit(main())
