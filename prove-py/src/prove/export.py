"""Export syntax highlighting definitions from canonical token lists.

Generates keyword sections for Pygments and Chroma lexers using sentinel
comments (PROVE-EXPORT-BEGIN/END markers) to identify replaceable sections.

For tree-sitter, grammar.js and highlights.scm are fully hand-maintained.
The `validate_treesitter()` function checks that tokens.py stays in sync
with the grammar, but does not modify any tree-sitter files.

NOTE: The Prove source file `prove/src/tokens.prv` defines TokenKind with
a [Lookup] variant type. This export reads from Python's tokens.py which
has a flat KEYWORDS dict. Variants with multiple string values (like
BooleanLit with "true" and "false") are handled as separate dict entries.
The [Lookup] variant information is not currently used by the export.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import click

from prove.tokens import KEYWORDS, TokenKind

# ── Canonical data sources ─────────────────────────────────────────

# TokenKind groups for categorization
_VERB_KINDS = frozenset(
    {
        TokenKind.TRANSFORMS,
        TokenKind.INPUTS,
        TokenKind.OUTPUTS,
        TokenKind.VALIDATES,
        TokenKind.READS,
        TokenKind.CREATES,
        TokenKind.MATCHES,
    }
)

_CONTRACT_KINDS = frozenset(
    {
        TokenKind.ENSURES,
        TokenKind.REQUIRES,
        TokenKind.EXPLAIN,
        TokenKind.WHEN,
        TokenKind.TERMINATES,
        TokenKind.TRUSTED,
    }
)

_AI_KINDS = frozenset(
    {
        TokenKind.WHY_NOT,
        TokenKind.CHOSEN,
        TokenKind.NEAR_MISS,
        TokenKind.KNOW,
        TokenKind.ASSUME,
        TokenKind.BELIEVE,
        TokenKind.INTENT,
        TokenKind.NARRATIVE,
        TokenKind.TEMPORAL,
        TokenKind.SATISFIES,
        TokenKind.INVARIANT_NETWORK,
    }
)

_KEYWORD_KINDS = frozenset(
    {
        TokenKind.MAIN,
        TokenKind.FROM,
        TokenKind.TYPE,
        TokenKind.IS,
        TokenKind.AS,
        TokenKind.WHERE,
        TokenKind.MATCH,
        TokenKind.COMPTIME,
        TokenKind.VALID,
        TokenKind.MODULE,
        TokenKind.DOMAIN,
        TokenKind.BINARY,
        TokenKind.TYPES,
        TokenKind.CONSTANTS,
        TokenKind.FOREIGN,
    }
)


def read_canonical_lists() -> dict[str, list[str]]:
    """Read all keyword/type/operator lists from compiler source."""
    from prove.checker import _BUILTIN_TYPE_NAMES
    from prove.types import BUILTIN_FUNCTIONS, BUILTINS

    verbs: list[str] = []
    keywords: list[str] = []
    contract_keywords: list[str] = []
    ai_keywords: list[str] = []

    for word, kind in KEYWORDS.items():
        if kind in _VERB_KINDS:
            verbs.append(word)
        elif kind in _CONTRACT_KINDS:
            contract_keywords.append(word)
        elif kind in _AI_KINDS:
            ai_keywords.append(word)
        elif kind in _KEYWORD_KINDS:
            keywords.append(word)
        # Skip BOOLEAN_LIT — handled in literals

    # Sort for stable output
    verbs.sort()
    keywords.sort()
    contract_keywords.sort()
    ai_keywords.sort()

    builtin_types = sorted(BUILTINS.keys())
    generic_types = sorted(name for name in _BUILTIN_TYPE_NAMES if name not in BUILTINS)
    builtin_functions = sorted(BUILTIN_FUNCTIONS)

    return {
        "verbs": verbs,
        "keywords": keywords,
        "contract_keywords": contract_keywords,
        "ai_keywords": ai_keywords,
        "builtin_types": builtin_types,
        "generic_types": generic_types,
        "builtin_functions": builtin_functions,
        "literals": ["true", "false"],
    }


# ── Sentinel replacement ──────────────────────────────────────────


def replace_sentinel_section(
    content: str,
    category: str,
    replacement: str,
) -> str:
    """Replace content between PROVE-EXPORT-BEGIN/END markers."""
    begin_marker = f"PROVE-EXPORT-BEGIN: {category}"
    end_marker = f"PROVE-EXPORT-END: {category}"

    begin_idx = content.find(begin_marker)
    if begin_idx == -1:
        raise ValueError(f"Sentinel pair PROVE-EXPORT-BEGIN/END: {category} not found")

    # Find end of the BEGIN line (after the newline)
    body_start = content.index("\n", begin_idx) + 1

    end_idx = content.find(end_marker, body_start)
    if end_idx == -1:
        raise ValueError(f"Sentinel pair PROVE-EXPORT-BEGIN/END: {category} not found")

    # Find start of the END line (back up to the line start)
    end_line_start = content.rfind("\n", body_start, end_idx) + 1

    return content[:body_start] + replacement + content[end_line_start:]


# ── Tree-sitter validation ────────────────────────────────────────

_GRAMMAR_LITERAL_RE = re.compile(r"'([a-z_]+)'")


def _ts_grammar_literals(grammar_path: Path) -> frozenset[str]:
    """Extract all single-quoted string literals from grammar.js."""
    text = grammar_path.read_text()
    return frozenset(_GRAMMAR_LITERAL_RE.findall(text))


def _ts_highlights_keywords(scm_path: Path) -> frozenset[str]:
    """Extract all double-quoted keyword strings from highlights.scm."""
    text = scm_path.read_text()
    return frozenset(re.findall(r'"([a-z_]+)"', text))


def validate_treesitter(lists: dict, workspace: Path) -> bool:
    """Validate that tokens.py is in sync with grammar.js and highlights.scm.

    Checks that every verb and keyword in tokens.py appears as a literal
    in grammar.js, and that highlights.scm references them. Reports drift
    but does not modify any files.

    Returns True if no drift is found.
    """
    ts_dir = workspace / "tree-sitter-prove"
    if not ts_dir.is_dir():
        click.echo(f"  skip: {ts_dir} not found", err=True)
        return True  # Not an error — tree-sitter-prove may not be present

    grammar_path = ts_dir / "grammar.js"
    grammar_lits = _ts_grammar_literals(grammar_path)

    # Collect all keywords from tokens.py that should appear in grammar.js
    expected_verbs = set(lists["verbs"])
    expected_keywords = set(lists["keywords"]) - {"main", "types", "constants"}
    # trusted is highlighted via (trusted_annotation) node, not as a bare keyword
    expected_contract = set(lists["contract_keywords"]) - {"trusted"}
    expected_ai = set(lists["ai_keywords"])

    all_expected = expected_verbs | expected_keywords | expected_contract | expected_ai
    missing_from_grammar = all_expected - grammar_lits

    ok = True
    if missing_from_grammar:
        ok = False
        click.echo("  drift: tokens.py keywords missing from grammar.js:", err=True)
        for kw in sorted(missing_from_grammar):
            click.echo(f"    - {kw}", err=True)

    # Check highlights.scm files
    for scm_path in [
        ts_dir / "queries" / "highlights.scm",
        ts_dir / "queries" / "prove" / "highlights.scm",
    ]:
        if not scm_path.exists():
            continue
        scm_keywords = _ts_highlights_keywords(scm_path)
        # Only check keywords that are in grammar.js (highlights can only
        # reference grammar literals)
        checkable = all_expected & grammar_lits
        missing_from_scm = checkable - scm_keywords
        if missing_from_scm:
            ok = False
            rel = scm_path.relative_to(workspace)
            click.echo(f"  drift: keywords missing from {rel}:", err=True)
            for kw in sorted(missing_from_scm):
                click.echo(f"    - {kw}", err=True)

    if ok:
        click.echo("  validate: grammar.js ↔ tokens.py in sync")
    return ok


# ── Pygments generator ─────────────────────────────────────────────


def _pygments_verbs(lists: dict) -> str:
    """Generate Pygments verbs section."""
    items = lists["verbs"]
    word_args = ", ".join(f'"{w}"' for w in items)
    return (
        "            # Intent verbs (function declaration keywords)\n"
        "            (\n"
        "                words(\n"
        f"                    (\n"
        f"                        {word_args},\n"
        f"                    ),\n"
        '                    prefix=r"\\b",\n'
        '                    suffix=r"\\b",\n'
        "                ),\n"
        "                Keyword.Declaration,\n"
        "            ),\n"
    )


def _pygments_contract(lists: dict) -> str:
    """Generate Pygments contract keywords section."""
    items = lists["contract_keywords"]
    word_args = ", ".join(f'"{w}"' for w in items)
    return (
        "            # Contract keywords\n"
        "            (\n"
        "                words(\n"
        f"                    (\n"
        f"                        {word_args},\n"
        f"                    ),\n"
        '                    prefix=r"\\b",\n'
        '                    suffix=r"\\b",\n'
        "                ),\n"
        "                Keyword.Namespace,\n"
        "            ),\n"
    )


def _pygments_keywords(lists: dict) -> str:
    """Generate Pygments core keywords section."""
    items = lists["keywords"]
    # Format with one per line for readability
    lines = "\n".join(f'                        "{k}",' for k in items)
    return (
        "            # Core keywords\n"
        "            (\n"
        "                words(\n"
        "                    (\n"
        f"{lines}\n"
        "                    ),\n"
        '                    prefix=r"\\b",\n'
        '                    suffix=r"\\b",\n'
        "                ),\n"
        "                Keyword,\n"
        "            ),\n"
    )


def _pygments_ai(lists: dict) -> str:
    """Generate Pygments AI keywords section."""
    items = lists["ai_keywords"]
    lines = "\n".join(f'                        "{k}",' for k in items)
    return (
        "            # AI-resistance and annotation keywords\n"
        "            (\n"
        "                words(\n"
        "                    (\n"
        f"{lines}\n"
        "                    ),\n"
        '                    prefix=r"\\b",\n'
        '                    suffix=r"\\b",\n'
        "                ),\n"
        "                Keyword.Namespace,\n"
        "            ),\n"
    )


def _pygments_literals(lists: dict) -> str:
    """Generate Pygments literals section."""
    items = lists["literals"]
    alts = "|".join(items)
    return f'            # Boolean constants\n            (r"\\b({alts})\\b", Keyword.Constant),\n'


def _pygments_builtin_types(lists: dict) -> str:
    """Generate Pygments builtin types section."""
    all_types = sorted(lists["builtin_types"] + lists["generic_types"])
    lines = "\n".join(f'                        "{t}",' for t in all_types)
    return (
        "            # Built-in types\n"
        "            (\n"
        "                words(\n"
        "                    (\n"
        f"{lines}\n"
        "                    ),\n"
        '                    prefix=r"\\b",\n'
        '                    suffix=r"\\b",\n'
        "                ),\n"
        "                Keyword.Type,\n"
        "            ),\n"
    )


def generate_pygments(lists: dict, workspace: Path) -> bool:
    """Write __init__.py keyword/type/operator sections.

    Returns True if target directory exists and was updated.
    """
    pg_dir = workspace / "pygments-prove"
    if not pg_dir.is_dir():
        click.echo(f"  skip: {pg_dir} not found", err=True)
        return False

    init_path = pg_dir / "pygments_prove" / "__init__.py"
    content = init_path.read_text()

    content = replace_sentinel_section(
        content,
        "verbs",
        _pygments_verbs(lists),
    )
    content = replace_sentinel_section(
        content,
        "contract-keywords",
        _pygments_contract(lists),
    )
    content = replace_sentinel_section(
        content,
        "keywords",
        _pygments_keywords(lists),
    )
    content = replace_sentinel_section(
        content,
        "ai-keywords",
        _pygments_ai(lists),
    )
    content = replace_sentinel_section(
        content,
        "literals",
        _pygments_literals(lists),
    )
    content = replace_sentinel_section(
        content,
        "builtin-types",
        _pygments_builtin_types(lists),
    )

    init_path.write_text(content)
    click.echo(f"  wrote {init_path}")
    return True


# ── Chroma generator ──────────────────────────────────────────────


def _chroma_regex_line(
    items: list[str],
    token: str,
) -> str:
    """Generate a single Chroma regex alternation line."""
    alts = "|".join(items)
    return f"\t\t\t\t{{`\\b({alts})\\b`, chroma.{token}, nil}},\n"


def generate_chroma(lists: dict, workspace: Path) -> bool:
    """Write lexer.go keyword/type/operator sections.

    Returns True if target directory exists and was updated.
    """
    ch_dir = workspace / "chroma-lexer-prove"
    if not ch_dir.is_dir():
        click.echo(f"  skip: {ch_dir} not found", err=True)
        return False

    lexer_path = ch_dir / "prove" / "lexer.go"
    content = lexer_path.read_text()

    content = replace_sentinel_section(
        content,
        "verbs",
        _chroma_regex_line(lists["verbs"], "KeywordDeclaration"),
    )
    content = replace_sentinel_section(
        content,
        "contract-keywords",
        _chroma_regex_line(lists["contract_keywords"], "KeywordNamespace"),
    )
    content = replace_sentinel_section(
        content,
        "keywords",
        _chroma_regex_line(lists["keywords"], "Keyword"),
    )
    content = replace_sentinel_section(
        content,
        "ai-keywords",
        _chroma_regex_line(lists["ai_keywords"], "KeywordNamespace"),
    )

    lit_alts = "|".join(lists["literals"])
    content = replace_sentinel_section(
        content,
        "literals",
        f"\t\t\t\t{{`\\b({lit_alts})\\b`, chroma.KeywordConstant, nil}},\n",
    )

    all_types = sorted(lists["builtin_types"] + lists["generic_types"])
    content = replace_sentinel_section(
        content,
        "builtin-types",
        _chroma_regex_line(all_types, "KeywordType"),
    )

    lexer_path.write_text(content)
    click.echo(f"  wrote {lexer_path}")
    return True


# ── Build helpers ──────────────────────────────────────────────────


def _run_build(cmd: list[str], cwd: Path, label: str) -> bool:
    """Run a build command, reporting success/failure."""
    click.echo(f"  build: {label}...")
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0:
        click.echo(f"  build FAILED: {label}", err=True)
        if result.stderr:
            click.echo(result.stderr, err=True)
        return False
    click.echo(f"  build: {label} ok")
    return True


def build_treesitter(workspace: Path) -> bool:
    """Run tree-sitter generate and test."""
    ts_dir = workspace / "tree-sitter-prove"
    ok = _run_build(
        ["tree-sitter", "generate"],
        ts_dir,
        "tree-sitter generate",
    )
    if ok:
        _run_build(["tree-sitter", "test"], ts_dir, "tree-sitter test")
    return ok


def build_pygments(workspace: Path) -> bool:
    """Install pygments-prove in dev mode."""
    pg_dir = workspace / "pygments-prove"
    return _run_build(
        ["pip", "install", "-e", "."],
        pg_dir,
        "pip install pygments-prove",
    )


def build_chroma(workspace: Path) -> bool:
    """Build chroma-lexer-prove."""
    ch_dir = workspace / "chroma-lexer-prove"
    return _run_build(
        ["go", "build", "./..."],
        ch_dir,
        "go build chroma-lexer-prove",
    )
