#!/usr/bin/env python3
"""Regenerate PDAT store files shipped as package data.

Run from the prove-py directory:
    python scripts/build_stores.py
"""

from __future__ import annotations

from pathlib import Path

from prove._nl_intent import VERB_SYNONYMS
from prove.store_binary import write_pdat

DATA_DIR = Path(__file__).resolve().parent.parent / "src" / "prove" / "data"


def build_verb_synonyms() -> None:
    """Write verb_synonyms.dat from the VERB_SYNONYMS dict."""
    variants: list[tuple[str, list[str]]] = []
    for canonical, syns in VERB_SYNONYMS.items():
        for syn in syns:
            variants.append((syn, [canonical]))

    out = DATA_DIR / "verb_synonyms.dat"
    write_pdat(out, "VerbSynonyms", ["String"], variants)
    print(f"wrote {out} ({len(variants)} entries)")


if __name__ == "__main__":
    build_verb_synonyms()
