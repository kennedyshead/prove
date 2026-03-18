"""Verify that DIAGNOSTIC_DOCS registry and diagnostics.md stay in sync."""

import re
from pathlib import Path

from prove.errors import DIAGNOSTIC_DOCS  # noqa: I001

_DOCS_PATH = Path(__file__).resolve().parents[2] / "docs" / "diagnostics.md"


def _parse_doc_headings() -> set[str]:
    """Extract diagnostic codes from ### headings in diagnostics.md."""
    text = _DOCS_PATH.read_text()
    # Match headings like: ### E100 — Tab character not allowed
    codes: set[str] = set()
    for m in re.finditer(r"^###\s+([EWI]\d+)\s", text, re.MULTILINE):
        codes.add(m.group(1))
    return codes


def test_all_registry_codes_documented():
    """Every code in DIAGNOSTIC_DOCS must have a heading in diagnostics.md."""
    doc_codes = _parse_doc_headings()
    missing = set(DIAGNOSTIC_DOCS.keys()) - doc_codes
    assert not missing, (
        f"Codes in DIAGNOSTIC_DOCS but missing from diagnostics.md: {sorted(missing)}"
    )


def test_all_documented_codes_in_registry():
    """Every heading code in diagnostics.md must be in DIAGNOSTIC_DOCS."""
    doc_codes = _parse_doc_headings()
    missing = doc_codes - set(DIAGNOSTIC_DOCS.keys())
    assert not missing, (
        f"Codes in diagnostics.md but missing from DIAGNOSTIC_DOCS: {sorted(missing)}"
    )
