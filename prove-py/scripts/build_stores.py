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
        from nltk.corpus import wordnet  # type: ignore[import-untyped]

        # Probe that data is actually downloaded
        wordnet.synsets("test")
    except Exception:
        print("skipping synonym_cache.dat (NLTK/WordNet not available)")
        return

    # Collect all words from VERB_SYNONYMS + common intent nouns
    seed_words: set[str] = set()
    for syns in VERB_SYNONYMS.values():
        seed_words.update(syns)
    # Common intent domain nouns
    seed_words.update([
        "file", "text", "string", "number", "list", "array", "table",
        "path", "hash", "format", "parse", "error", "result", "option",
        "byte", "character", "pattern", "time", "random", "network",
        "log", "system", "math", "length", "split", "join", "sort",
        "filter", "map", "reduce", "count", "find", "search", "replace",
    ])

    variants: list[tuple[str, list[str]]] = []
    for word in sorted(seed_words):
        syns_set: set[str] = set()
        for pos in ("v", "n"):
            for synset in wordnet.synsets(word, pos=pos):
                for lemma in synset.lemmas():
                    name = lemma.name().replace("_", " ").lower()
                    if name != word.lower():
                        syns_set.add(name)
        if syns_set:
            variants.append((word.lower(), ["|".join(sorted(syns_set))]))

    out = DATA_DIR / "synonym_cache.dat"
    write_pdat(out, "SynonymCache", ["String"], variants)
    print(f"wrote {out} ({len(variants)} entries)")


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


if __name__ == "__main__":
    build_verb_synonyms()
    build_synonym_cache()
    build_similarity_matrix()
    build_semantic_features()
