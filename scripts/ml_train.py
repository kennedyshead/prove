"""Phase 2 — Model Training for LSP ML PoC.

Reads data/completions_raw.json and builds n-gram frequency tables.

Outputs:
  data/completions_model.json  — bigram model: {(prev2, prev1): [(token, count), ...]}
  data/bigrams_model.json      — unigram fallback: {prev1: [(token, count), ...]}

Usage:
    python scripts/ml_train.py [--input data/completions_raw.json] [--top-k 10]
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path


def load_ngrams(input_path: Path) -> list[dict]:
    with open(input_path, encoding="utf-8") as f:
        records = json.load(f)
    return [r for r in records if r.get("kind") not in ("function_triple", "docstring_mapping")]


def load_docstring_records(input_path: Path) -> list[dict]:
    with open(input_path, encoding="utf-8") as f:
        records = json.load(f)
    return [r for r in records if r.get("kind") == "docstring_mapping"]


def build_bigram_model(ngrams: list[dict], top_k: int) -> dict[str, list[list]]:
    """Build (prev2, prev1) → top-K next tokens."""
    counts: dict[tuple[str, str], Counter] = defaultdict(Counter)
    for r in ngrams:
        key = (r["prev2"], r["prev1"])
        counts[key][r["next"]] += 1

    model: dict[str, list[list]] = {}
    for (prev2, prev1), counter in counts.items():
        key_str = json.dumps([prev2, prev1])
        top = counter.most_common(top_k)
        model[key_str] = [[tok, cnt] for tok, cnt in top]
    return model


def build_unigram_model(ngrams: list[dict], top_k: int) -> dict[str, list[list]]:
    """Build prev1 → top-K next tokens (fallback)."""
    counts: dict[str, Counter] = defaultdict(Counter)
    for r in ngrams:
        counts[r["prev1"]][r["next"]] += 1

    model: dict[str, list[list]] = {}
    for prev1, counter in counts.items():
        top = counter.most_common(top_k)
        model[prev1] = [[tok, cnt] for tok, cnt in top]
    return model


def build_docstring_index(records: list[dict]) -> dict[str, list[dict]]:
    """Build word -> function mapping from docstring_mapping records.

    Returns: {"hash": [{"module": "Hash", "name": "sha256", ...}, ...], ...}
    """
    index: dict[str, list[dict]] = defaultdict(list)
    for rec in records:
        words = set(re.findall(r"[a-zA-Z]{3,}", rec["doc"].lower()))
        entry = {
            "module": rec["module"],
            "name": rec["name"],
            "verb": rec["verb"],
            "doc": rec["doc"],
            "first_param_type": rec.get("first_param_type"),
            "return_type": rec.get("return_type"),
        }
        for word in words:
            index[word].append(entry)
    return dict(index)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="data/completions_raw.json")
    parser.add_argument("--top-k", type=int, default=10, dest="top_k")
    parser.add_argument("--output-dir", default="data")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent.parent
    input_path = repo_root / args.input
    output_dir = repo_root / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Loading {input_path} ...")
    ngrams = load_ngrams(input_path)
    print(f"  {len(ngrams)} ngram records")

    docstring_recs = load_docstring_records(input_path)
    print(f"  {len(docstring_recs)} docstring records")

    print("Building bigram model ...")
    bigram_model = build_bigram_model(ngrams, args.top_k)
    print(f"  {len(bigram_model)} contexts")

    print("Building unigram fallback model ...")
    unigram_model = build_unigram_model(ngrams, args.top_k)
    print(f"  {len(unigram_model)} contexts")

    print("Building docstring index ...")
    docstring_index = build_docstring_index(docstring_recs)
    print(f"  {len(docstring_index)} keywords")

    completions_out = output_dir / "completions_model.json"
    bigrams_out = output_dir / "bigrams_model.json"
    docstrings_out = output_dir / "docstring_index.json"

    with open(completions_out, "w", encoding="utf-8") as f:
        json.dump(bigram_model, f, indent=2)
    print(f"Wrote {completions_out}")

    with open(bigrams_out, "w", encoding="utf-8") as f:
        json.dump(unigram_model, f, indent=2)
    print(f"Wrote {bigrams_out}")

    with open(docstrings_out, "w", encoding="utf-8") as f:
        json.dump(docstring_index, f, indent=2)
    print(f"Wrote {docstrings_out}")

    # Spot-check: show top completions for a few common contexts
    print("\nSpot-check (bigram):")
    for sample_key in [
        '["transforms", "<START>"]',
        '["from", "from"]',
        '["<START>", "transforms"]',
        '["verb", "name"]',
    ]:
        if sample_key in bigram_model:
            top3 = bigram_model[sample_key][:3]
            print(f"  {sample_key} → {top3}")

    print("\nSpot-check (unigram):")
    for sample_key in ["transforms", "from", "type", "as"]:
        if sample_key in unigram_model:
            top3 = unigram_model[sample_key][:3]
            print(f"  {sample_key!r} → {top3}")


if __name__ == "__main__":
    main()
