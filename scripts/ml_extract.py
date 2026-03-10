"""Phase 1 — Data Extraction for LSP ML PoC.

Walks all .prv source files in stdlib, examples, and test fixtures.
Produces data/completions_raw.json: token trigrams + FunctionDef triples.

Usage:
    python scripts/ml_extract.py [--output data/completions_raw.json]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Allow running from repo root without install
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "prove-py" / "src"))

from prove.ast_nodes import FunctionDef, GenericType, ModifiedType, SimpleType, TypeExpr
from prove.lexer import Lexer
from prove.parser import Parser
from prove.tokens import TokenKind

# Token kinds to skip entirely — structural noise with no completion value
_SKIP_KINDS = frozenset(
    {
        TokenKind.NEWLINE,
        TokenKind.INDENT,
        TokenKind.DEDENT,
        TokenKind.EOF,
        TokenKind.DOC_COMMENT,
    }
)

# Source directories to walk (relative to repo root)
_SOURCE_DIRS = [
    Path("prove-py/src/prove/stdlib"),
    Path("examples"),
    Path("prove-py/tests/fixtures"),
]


def _token_text(tok_kind: TokenKind, tok_value: str) -> str:
    """Return a stable string representation of a token for the model."""
    if tok_value:
        return tok_value
    return f"<{tok_kind.name}>"


def _type_expr_to_str(te: TypeExpr) -> str:
    if isinstance(te, SimpleType):
        return te.name
    if isinstance(te, GenericType):
        args = ", ".join(_type_expr_to_str(a) for a in te.args)
        return f"{te.name}[{args}]"
    if isinstance(te, ModifiedType):
        mods = " ".join(m.value for m in te.modifiers)
        return f"{te.name}:[{mods}]"
    return str(te)


def extract_file(path: Path, rel_path: str) -> tuple[list[dict], list[dict]]:
    """Return (ngram_records, triple_records) for one .prv file."""
    try:
        source = path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"  skip {rel_path}: {exc}", file=sys.stderr)
        return [], []

    try:
        tokens = Lexer(source, str(path)).lex()
    except Exception as exc:
        print(f"  lex error {rel_path}: {exc}", file=sys.stderr)
        return [], []

    # Filter tokens to meaningful ones
    filtered = [
        t for t in tokens if t.kind not in _SKIP_KINDS
    ]

    # Build ngram records
    ngrams: list[dict] = []
    for i, tok in enumerate(filtered):
        prev2 = _token_text(filtered[i - 2].kind, filtered[i - 2].value) if i >= 2 else "<START>"
        prev1 = _token_text(filtered[i - 1].kind, filtered[i - 1].value) if i >= 1 else "<START>"
        next_tok = _token_text(tok.kind, tok.value)
        ngrams.append(
            {
                "prev2": prev2,
                "prev1": prev1,
                "next": next_tok,
                "file": rel_path,
                "line": tok.span.start_line,
            }
        )

    # Build FunctionDef triples via Parser
    triples: list[dict] = []
    try:
        module = Parser(tokens, str(path)).parse()
        for decl in module.declarations:
            if not isinstance(decl, FunctionDef):
                continue
            first_param_type = (
                _type_expr_to_str(decl.params[0].type_expr)
                if decl.params
                else None
            )
            return_type = (
                _type_expr_to_str(decl.return_type)
                if decl.return_type is not None
                else None
            )
            triples.append(
                {
                    "kind": "function_triple",
                    "verb": decl.verb,
                    "name": decl.name,
                    "first_param_type": first_param_type,
                    "return_type": return_type,
                    "can_fail": decl.can_fail,
                    "file": rel_path,
                    "line": decl.span.start_line,
                }
            )
    except Exception as exc:
        print(f"  parse error {rel_path}: {exc}", file=sys.stderr)

    return ngrams, triples


def collect_prv_files(repo_root: Path) -> list[tuple[Path, str]]:
    """Return list of (absolute_path, relative_path) for all .prv files."""
    results: list[tuple[Path, str]] = []
    for src_dir in _SOURCE_DIRS:
        abs_dir = repo_root / src_dir
        if not abs_dir.exists():
            print(f"  warning: source dir not found: {src_dir}", file=sys.stderr)
            continue
        for prv_file in sorted(abs_dir.rglob("*.prv")):
            rel = str(prv_file.relative_to(repo_root))
            results.append((prv_file, rel))
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        default="data/completions_raw.json",
        help="Output JSON file path (default: data/completions_raw.json)",
    )
    args = parser.parse_args()

    repo_root = _REPO_ROOT
    output_path = repo_root / args.output

    files = collect_prv_files(repo_root)
    print(f"Found {len(files)} .prv files")

    all_records: list[dict] = []
    total_ngrams = 0
    total_triples = 0

    for abs_path, rel_path in files:
        ngrams, triples = extract_file(abs_path, rel_path)
        all_records.extend(ngrams)
        all_records.extend(triples)
        total_ngrams += len(ngrams)
        total_triples += len(triples)
        print(f"  {rel_path}: {len(ngrams)} ngrams, {len(triples)} triples")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(all_records, f, indent=2)

    print(
        f"\nWrote {len(all_records)} records "
        f"({total_ngrams} ngrams + {total_triples} triples) "
        f"→ {output_path}"
    )


if __name__ == "__main__":
    main()
