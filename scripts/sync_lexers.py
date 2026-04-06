#!/usr/bin/env python3
"""Sync keyword lists from keywords.toml into Chroma and Pygments lexers.

Reads the canonical keyword definitions from keywords.toml and updates
all PROVE-EXPORT-BEGIN/END blocks in the lexer source files.

Usage:
    python scripts/sync_lexers.py          # update lexers in-place
    python scripts/sync_lexers.py --check  # exit 1 if lexers are out of date
"""

import re
import sys
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

REPO_ROOT = Path(__file__).resolve().parent.parent
KEYWORDS_FILE = REPO_ROOT / "keywords.toml"

LEXER_FILES = [
    REPO_ROOT / "chroma-lexer-prove" / "prove" / "lexer.go",
    REPO_ROOT / "pygments-prove" / "pygments_prove" / "__init__.py",
]

# ── Token type mappings per category ──────────────────────────

CHROMA_TOKENS = {
    "verbs": "chroma.KeywordDeclaration",
    "contract-keywords": "chroma.KeywordNamespace",
    "keywords": "chroma.Keyword",
    "ai-keywords": "chroma.KeywordNamespace",
    "literals": "chroma.KeywordConstant",
    "builtin-types": "chroma.KeywordType",
    "intent-sections": "chroma.Keyword",
}

PYGMENTS_TOKENS = {
    "verbs": "Keyword.Declaration",
    "contract-keywords": "Keyword.Namespace",
    "keywords": "Keyword",
    "ai-keywords": "Keyword.Namespace",
    "literals": "Keyword.Constant",
    "builtin-types": "Keyword.Type",
    "intent-sections": "Keyword",
}

CATEGORY_DESCRIPTIONS = {
    "verbs": "Verb keywords",
    "contract-keywords": "Contract keywords",
    "keywords": "Core keywords",
    "ai-keywords": "AI-resistance and annotation keywords",
    "literals": "Boolean constants",
    "builtin-types": "Built-in types",
    "intent-sections": "Section keywords",
}

EXPORT_BLOCK_RE = re.compile(
    r"([ \t]*(?:#|//) PROVE-EXPORT-BEGIN: (\S+)\n)"
    r"(.*?)"
    r"([ \t]*(?:#|//) PROVE-EXPORT-END: \2)",
    re.DOTALL,
)


# ── Chroma (Go) generators ───────────────────────────────────


def gen_chroma(category: str, words: list[str], token: str) -> str:
    joined = "|".join(words)
    return f"\t\t\t\t{{`\\b({joined})\\b`, {token}, nil}},"


# ── Pygments (Python) generators ─────────────────────────────


def gen_pygments(category: str, words: list[str], token: str) -> str:
    desc = CATEGORY_DESCRIPTIONS.get(category, category)
    if category == "literals":
        joined = "|".join(words)
        return f'            # {desc}\n            (r"\\b({joined})\\b", {token}),'

    items = "\n".join(f'                        "{w}",' for w in words)
    return (
        f"            # {desc}\n"
        f"            (\n"
        f"                words(\n"
        f"                    (\n"
        f"{items}\n"
        f"                    ),\n"
        f'                    prefix=r"\\b",\n'
        f'                    suffix=r"\\b",\n'
        f"                ),\n"
        f"                {token},\n"
        f"            ),"
    )


# ── Block replacement ────────────────────────────────────────


def replace_export_blocks(
    content: str,
    keywords: dict[str, list[str]],
    gen_fn,
    token_map: dict[str, str],
) -> str:
    def replacer(m: re.Match) -> str:
        begin = m.group(1)
        category = m.group(2)
        end = m.group(4)

        if category not in keywords:
            print(f"  WARNING: unknown category '{category}', skipping")
            return m.group(0)
        if category not in token_map:
            print(f"  WARNING: no token mapping for '{category}', skipping")
            return m.group(0)

        body = gen_fn(category, keywords[category], token_map[category])
        return f"{begin}{body}\n{end}"

    return EXPORT_BLOCK_RE.sub(replacer, content)


def sync_file(
    path: Path,
    keywords: dict[str, list[str]],
    check_only: bool,
) -> bool:
    if not path.exists():
        print(f"  {path.name}: NOT FOUND, skipping")
        return True

    # Pick generator + token map based on file extension
    if path.suffix == ".go":
        gen_fn, token_map = gen_chroma, CHROMA_TOKENS
    else:
        gen_fn, token_map = gen_pygments, PYGMENTS_TOKENS

    original = path.read_text()
    updated = replace_export_blocks(original, keywords, gen_fn, token_map)

    if original == updated:
        print(f"  {path.name}: up to date")
        return True

    if check_only:
        print(f"  {path.name}: OUT OF DATE")
        return False

    path.write_text(updated)
    print(f"  {path.name}: updated")
    return True


# ── Main ─────────────────────────────────────────────────────


def main() -> None:
    check_only = "--check" in sys.argv

    with open(KEYWORDS_FILE, "rb") as f:
        raw = tomllib.load(f)

    keywords = {k: sorted(v["words"]) for k, v in raw.items()}
    total = sum(len(v) for v in keywords.values())
    print(f"Loaded {total} keywords in {len(keywords)} categories from keywords.toml")

    all_ok = True
    for path in LEXER_FILES:
        print(f"\n  Syncing {path.relative_to(REPO_ROOT)} ...")
        ok = sync_file(path, keywords, check_only)
        all_ok = all_ok and ok

    if not all_ok:
        print("\nLexers are out of date. Run: python scripts/sync_lexers.py")
        sys.exit(1)

    print("\nDone.")


if __name__ == "__main__":
    main()
