#!/usr/bin/env python3
"""Verify DIAGNOSTIC_DOCS registry matches diagnostics.md headings.

Exit 0 if in sync, exit 1 with details if not.
Usage: python scripts/check_doc_links.py
"""

import re
import sys
from pathlib import Path

# Adjust path so we can import prove
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "prove-py" / "src"))

from prove.errors import DIAGNOSTIC_DOCS  # noqa: E402

DOCS_PATH = Path(__file__).resolve().parents[1] / "docs" / "diagnostics.md"


def parse_doc_headings() -> set[str]:
    text = DOCS_PATH.read_text()
    codes: set[str] = set()
    for m in re.finditer(r"^###\s+([EWI]\d+)\s", text, re.MULTILINE):
        codes.add(m.group(1))
    return codes


def main() -> int:
    doc_codes = parse_doc_headings()
    registry_codes = set(DIAGNOSTIC_DOCS.keys())

    undocumented = registry_codes - doc_codes
    unregistered = doc_codes - registry_codes

    ok = True
    if undocumented:
        print(f"In registry but not in docs: {sorted(undocumented)}")
        ok = False
    if unregistered:
        print(f"In docs but not in registry: {sorted(unregistered)}")
        ok = False

    if ok:
        print(f"All {len(registry_codes)} codes in sync.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
