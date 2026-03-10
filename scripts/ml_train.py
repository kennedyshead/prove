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
from collections import Counter, defaultdict
from pathlib import Path


def load_ngrams(input_path: Path) -> list[dict]:
    with open(input_path, encoding="utf-8") as f:
        records = json.load(f)
    return [r for r in records if r.get("kind") != "function_triple"]


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

    print("Building bigram model ...")
    bigram_model = build_bigram_model(ngrams, args.top_k)
    print(f"  {len(bigram_model)} contexts")

    print("Building unigram fallback model ...")
    unigram_model = build_unigram_model(ngrams, args.top_k)
    print(f"  {len(unigram_model)} contexts")

    completions_out = output_dir / "completions_model.json"
    bigrams_out = output_dir / "bigrams_model.json"

    with open(completions_out, "w", encoding="utf-8") as f:
        json.dump(bigram_model, f, indent=2)
    print(f"Wrote {completions_out}")

    with open(bigrams_out, "w", encoding="utf-8") as f:
        json.dump(unigram_model, f, indent=2)
    print(f"Wrote {bigrams_out}")

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
