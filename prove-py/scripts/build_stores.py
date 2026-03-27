#!/usr/bin/env python3
"""Regenerate PDAT store files shipped as package data.

Run from the prove-py directory:
    python scripts/build_stores.py
"""

from __future__ import annotations

import shutil
from pathlib import Path

from prove._nl_intent import VERB_SYNONYMS
from prove.store_binary import read_pdat, write_pdat

DATA_DIR = Path(__file__).resolve().parent.parent / "src" / "prove" / "data"


def build_verb_synonyms() -> None:
    """Write verb_synonyms.dat, expanded with spaCy word vectors if available.

    When spaCy and a vector model are available, additional synonyms are
    discovered via word-vector similarity and merged with the hardcoded list.
    Falls back to the hardcoded VERB_SYNONYMS when spaCy is not available.
    """
    try:
        from prove.nlp_store import build_verb_synonyms_spacy as _build_spacy

        out = _build_spacy(out_path=DATA_DIR / "verb_synonyms.dat")
        data = read_pdat(out)
        hardcoded = sum(len(v) for v in VERB_SYNONYMS.values())
        expanded = len(data["variants"])
        print(f"wrote {out} ({expanded} entries, +{expanded - hardcoded} spaCy-expanded)")
        return
    except Exception as e:
        reason = str(e).split("\n")[0].strip() or type(e).__name__
        print(f"spaCy expansion unavailable ({reason}), using hardcoded synonyms")

    variants: list[tuple[str, list[str]]] = [
        (syn, [canonical]) for canonical, syns in VERB_SYNONYMS.items() for syn in syns
    ]
    out_path = DATA_DIR / "verb_synonyms.dat"
    write_pdat(out_path, "VerbSynonyms", ["String"], variants)
    out = out_path
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
        out = _build(out_path=DATA_DIR / "synonym_cache.dat")
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


def _prv_str(value: str) -> str:
    """Encode a Python string as a Prove string literal."""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _row_id(index: int) -> str:
    """Generate a valid Prove identifier for a table row."""
    return f"r{index:05d}"


def _strip_quotes(s: str) -> str:
    """Strip leading/trailing double-quotes from a Prove string literal."""
    if s.startswith('"') and s.endswith('"'):
        return s[1:-1]
    return s


def build_lsp_ml_stores(
    repo_root: Path | None = None,
    package_only: bool = False,
    top_k: int = 5,
) -> None:
    """Build LSP ML store files.

    Args:
        repo_root: Root of the prove repository (contains build/, prove-py/).
        package_only: If True, only write to src/prove/data/lsp/ (for pip).
                      If False, also writes build/lsp-ml-stores.tar.gz (for download).
        top_k: Max completions per context to store.
    """
    if repo_root is None:
        repo_root = Path(__file__).resolve().parent.parent.parent

    build_dir = repo_root / "build"
    data_dir = repo_root / "build"
    package_lsp_dir = repo_root / "prove-py" / "src" / "prove" / "data" / "lsp"

    # Write to package dir (always)
    _write_lsp_stores(data_dir, package_lsp_dir, top_k=top_k)

    if not package_only:
        import shutil

        # Write to build/ for download
        _write_lsp_stores(data_dir, build_dir / "lsp-ml-stores", top_k=top_k)

        # Bundle PDAT files (verb_synonyms.dat, synonym_cache.dat) into the tarball
        package_data_dir = repo_root / "prove-py" / "src" / "prove" / "data"
        pdat_out = build_dir / "lsp-ml-stores" / "pdat"
        pdat_out.mkdir(parents=True, exist_ok=True)
        for dat in ("verb_synonyms.dat", "synonym_cache.dat"):
            src = package_data_dir / dat
            if src.exists():
                shutil.copy2(src, pdat_out / dat)

        # Create tarball for distribution
        _create_tarball(build_dir / "lsp-ml-stores", build_dir / "lsp-ml-stores.tar.gz")


def _write_lsp_stores(data_dir: Path, out_dir: Path, top_k: int = 5) -> None:
    """Write LSP ML store .prv files from JSON models in data_dir."""
    out_dir.mkdir(parents=True, exist_ok=True)

    bigrams_in = data_dir / "bigrams_model.json"
    bigrams_out = out_dir / "bigrams" / "current.prv"
    if bigrams_in.exists():
        import json

        with open(bigrams_in, encoding="utf-8") as f:
            unigram_model = json.load(f)
        rows: list[tuple[str, str, int]] = []
        for prev1, entries in unigram_model.items():
            for next_tok, count in entries[:top_k]:
                rows.append((prev1, next_tok, count))
        lines = [
            "// Bigram frequency table for LSP ML completions",
            "// Auto-generated by prove-py/scripts/build_stores.py",
            "type Bigram:[Lookup] is String | String | Integer where",
        ]
        for i, (prev1, next_tok, count) in enumerate(rows):
            lines.append(f"    {_row_id(i)} | {_prv_str(prev1)} | {_prv_str(next_tok)} | {count}")
        bigrams_out.parent.mkdir(parents=True, exist_ok=True)
        (bigrams_out.parent / "versions").mkdir(parents=True, exist_ok=True)
        bigrams_out.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"wrote {bigrams_out} ({len(rows)} rows)")

    comps_in = data_dir / "completions_model.json"
    comps_out = out_dir / "completions" / "current.prv"
    if comps_in.exists():
        import json

        with open(comps_in, encoding="utf-8") as f:
            bigram_model = json.load(f)
        lines = [
            "// Completion context table for LSP ML completions",
            "// Auto-generated by prove-py/scripts/build_stores.py",
            "type Completion:[Lookup] is String | String | String where",
        ]
        for i, (key_json, entries) in enumerate(bigram_model.items()):
            prev2, prev1 = json.loads(key_json)
            top_tokens = [tok for tok, _count in entries[:top_k]]
            completion_str = "|".join(top_tokens)
            row = (
                f"    {_row_id(i)} | {_prv_str(prev2)}"
                f" | {_prv_str(prev1)} | {_prv_str(completion_str)}"
            )
            lines.append(row)
        comps_out.parent.mkdir(parents=True, exist_ok=True)
        (comps_out.parent / "versions").mkdir(parents=True, exist_ok=True)
        comps_out.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"wrote {comps_out} ({len(bigram_model)} contexts)")

    fb_in = data_dir / "from_blocks_model.json"
    fb_out = out_dir / "from_blocks" / "current.prv"
    if fb_in.exists():
        import json

        with open(fb_in, encoding="utf-8") as f:
            from_block_model = json.load(f)
        lines = [
            "// From-block n-gram table for LSP ML completions",
            "// Auto-generated by prove-py/scripts/build_stores.py",
            "type FromBlockML:[Lookup] is String | String | String where",
        ]
        for i, (key_json, entries) in enumerate(from_block_model.items()):
            prev2, prev1 = json.loads(key_json)
            top_tokens = [tok for tok, _count in entries[:top_k]]
            tokens_str = "|".join(top_tokens)
            lines.append(
                f"    {_row_id(i)} | {_prv_str(prev2)} | {_prv_str(prev1)} | {_prv_str(tokens_str)}"
            )
        fb_out.parent.mkdir(parents=True, exist_ok=True)
        (fb_out.parent / "versions").mkdir(parents=True, exist_ok=True)
        fb_out.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"wrote {fb_out} ({len(from_block_model)} contexts)")

    doc_in = data_dir / "docstring_index.json"
    doc_out = out_dir / "docstrings" / "current.prv"
    if doc_in.exists():
        import json

        with open(doc_in, encoding="utf-8") as f:
            docstring_index = json.load(f)
        lines = [
            "// Docstring knowledge base for LSP intent completions",
            "// Auto-generated by prove-py/scripts/build_stores.py",
            "type DocstringMap:[Lookup] is String | String | String | String | String where",
        ]
        row_count = 0
        for keyword in sorted(docstring_index):
            for entry in docstring_index[keyword]:
                lines.append(
                    f"    {_row_id(row_count)} | {_prv_str(keyword)} "
                    f"| {_prv_str(entry['module'])} | {_prv_str(entry['name'])} "
                    f"| {_prv_str(entry['verb'])} | {_prv_str(entry['doc'])}"
                )
                row_count += 1
        doc_out.parent.mkdir(parents=True, exist_ok=True)
        (doc_out.parent / "versions").mkdir(parents=True, exist_ok=True)
        doc_out.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"wrote {doc_out} ({row_count} entries)")


def _create_tarball(source_dir: Path, out_path: Path) -> None:
    """Create a tar.gz archive of the lsp-ml-stores directory."""
    # Build version file
    import datetime
    import tarfile
    import tempfile

    version_file = source_dir / "VERSION.txt"
    version_file.write_text(
        f"lsp-ml-stores v1\ngenerated: {datetime.datetime.utcnow().isoformat()}Z\n"
    )

    with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as tmp:
        tmp_path = Path(tmp.name)

    with tarfile.open(tmp_path, "w:gz") as tar:
        tar.add(source_dir, arcname="lsp-ml-stores")

    shutil.move(str(tmp_path), str(out_path))
    size_kb = out_path.stat().st_size // 1024
    print(f"wrote {out_path} ({size_kb} KB)")


if __name__ == "__main__":
    import argparse

    _parser = argparse.ArgumentParser(description=__doc__)
    _parser.add_argument(
        "--package-only", action="store_true", help="Only write package data, skip tarball"
    )
    _parser.add_argument(
        "--top-k",
        type=int,
        default=5,
        dest="top_k",
        help="Max completions per context (default: 5)",
    )
    _args = _parser.parse_args()

    build_verb_synonyms()
    build_synonym_cache()
    build_similarity_matrix()
    build_semantic_features()
    build_stdlib_index()
    build_lsp_ml_stores(package_only=_args.package_only, top_k=_args.top_k)
