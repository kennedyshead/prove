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


def build_synonym_cache() -> None:
    """Write synonym_cache.dat with WordNet-expanded synonyms.

    Requires NLTK with WordNet data.  Gracefully skips if unavailable.
    """
    try:
        from prove.nlp_store import build_synonym_cache as _build
    except Exception:
        print("skipping synonym_cache.dat (import error)")
        return

    try:
        out = _build()
        from prove.store_binary import read_pdat

        data = read_pdat(out)
        print(f"wrote {out} ({len(data['variants'])} entries)")
    except Exception as e:
        reason = str(e).split("\n")[0].strip() or type(e).__name__
        print(f"skipping synonym_cache.dat ({reason})")


def build_similarity_matrix() -> None:
    """Write similarity_matrix.dat with pairwise stdlib function similarity.

    Requires spaCy.  Gracefully skips if unavailable.
    """
    try:
        from prove.nlp_store import build_similarity_matrix as _build
    except Exception:
        print("skipping similarity_matrix.dat (import error)")
        return

    try:
        out = _build()
        from prove.store_binary import read_pdat

        data = read_pdat(out)
        print(f"wrote {out} ({len(data['variants'])} pairs)")
    except Exception as e:
        print(f"skipping similarity_matrix.dat ({e})")


def build_semantic_features() -> None:
    """Write semantic_features.dat with lemmatized keywords per function.

    Requires spaCy for lemmatization.  Gracefully skips if unavailable.
    """
    try:
        from prove.nlp_store import build_semantic_features as _build
    except Exception:
        print("skipping semantic_features.dat (import error)")
        return

    try:
        out = _build()
        from prove.store_binary import read_pdat

        data = read_pdat(out)
        print(f"wrote {out} ({len(data['variants'])} entries)")
    except Exception as e:
        print(f"skipping semantic_features.dat ({e})")


def build_stdlib_index() -> None:
    """Write stdlib_index.dat in current directory's .prove/ dir."""
    try:
        from prove.nlp_store import build_stdlib_index as _build

        out = _build()
        from prove.store_binary import read_pdat

        data = read_pdat(out)
        print(f"wrote {out} ({len(data['variants'])} entries)")
    except Exception as e:
        print(f"skipping stdlib_index.dat ({e})")


if __name__ == "__main__":
    build_verb_synonyms()
    build_synonym_cache()
    build_similarity_matrix()
    build_semantic_features()
    build_stdlib_index()
