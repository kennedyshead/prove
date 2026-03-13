"""Natural language intent analysis for Prove prose blocks.

Maps English action words to Prove verb keywords and extracts
semantic tokens from prose and function bodies.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

    from prove.ast_nodes import FunctionDef

# Each entry: (regex pattern, prove_verb_keyword)
# Patterns match word stems — checked against individual lowercased words.
_PROSE_STEMS: list[tuple[str, str]] = [
    (r"transform|convert|comput|calculat|process|produc", "transforms"),
    (r"validat|check|verif|ensur|guard", "validates"),
    (r"\bread|fetch|load|retriev|queri", "reads"),
    (r"creat|make|build|construct|generat", "creates"),
    (r"match|compar|classif|select", "matches"),
    (r"output|write|print|send|emit|log|display", "outputs"),
    (r"input|receiv|accept|pars|tak", "inputs"),
    (r"listen|watch|monitor|wait", "listens"),
    (r"detach|fire|spawn|fork|background", "detached"),
    (r"attach|await|join|child|worker", "attached"),
    (r"stream|block|poll|loop", "streams"),
]


def implied_verbs(text: str) -> set[str]:
    """Return Prove verb keywords implied by action words in prose text."""
    words = re.findall(r"[a-z]+", text.lower())
    result: set[str] = set()
    for word in words:
        for pattern, verb in _PROSE_STEMS:
            if re.search(pattern, word):
                result.add(verb)
                break
    return result


def body_tokens(fd: FunctionDef) -> set[str]:
    """Return param names + called function names from the from-body.

    Walks the AST recursively, collecting:
    - Parameter names from the function signature
    - Names of functions called directly (IdentifierExpr as func in CallExpr)
    """
    from prove.ast_nodes import CallExpr, IdentifierExpr

    names: set[str] = {p.name for p in fd.params}

    def _collect(node: object) -> None:
        if node is None:
            return
        if isinstance(node, (list, tuple)):
            for item in node:
                _collect(item)
            return
        if isinstance(node, CallExpr):
            if isinstance(node.func, IdentifierExpr):
                names.add(node.func.name)
        if hasattr(node, "__dataclass_fields__"):
            for val in vars(node).values():
                _collect(val)

    for stmt in fd.body:
        _collect(stmt)
    return names


def prose_overlaps(prose: str, tokens: set[str]) -> bool:
    """True if any word in prose matches a body token (case-insensitive, with stemming).

    Checks both direct matches and 4-character prefix stems, so "hashing"
    matches "hash" and vice versa.
    """
    prose_words = {w.lower() for w in re.findall(r"[a-zA-Z_][a-zA-Z0-9_]*", prose)}
    lower_tokens = {t.lower() for t in tokens}
    if prose_words & lower_tokens:
        return True
    for pw in prose_words:
        if len(pw) >= 4:
            for t in lower_tokens:
                if t.startswith(pw) or pw.startswith(t[:4]):
                    return True
    return False


# ── Noun extraction ──────────────────────────────────────────────

_NOUN_STOPS = frozenset({
    "the", "a", "an", "this", "that", "each", "every", "all", "some",
    "is", "are", "was", "were", "be", "been", "being",
    "has", "have", "had", "do", "does", "did",
    "will", "would", "could", "should", "can", "may", "might",
    "and", "or", "but", "not", "no", "nor",
    "from", "into", "with", "for", "to", "of", "in", "on", "at", "by",
    "it", "its", "them", "their", "they",
    "module", "function", "type", "using", "against", "between",
})


def extract_nouns(text: str) -> list[str]:
    """Extract candidate noun phrases from prose (domain objects, not verbs).

    Returns lowercase words that are likely to become function names,
    type names, or parameter names. Preserves order of first occurrence.
    """
    words = re.findall(r"[a-zA-Z_][a-zA-Z0-9_]*", text)
    seen: set[str] = set()
    nouns: list[str] = []

    for word in words:
        low = word.lower()
        if low in _NOUN_STOPS or low in seen or len(low) < 3:
            continue
        # Skip words that match verb stems
        is_verb = False
        for pattern, _ in _PROSE_STEMS:
            if re.search(pattern, low):
                is_verb = True
                break
        if is_verb:
            continue
        seen.add(low)
        nouns.append(low)

    return nouns


# ── Stub generation ──────────────────────────────────────────────

@dataclass
class FunctionStub:
    verb: str
    name: str
    params: list[tuple[str, str]] = field(default_factory=list)
    return_type: str = "String"
    confidence: float = 0.5


# Heuristic parameter and return type defaults per verb family
_VERB_PARAM_HINTS: dict[str, list[tuple[str, str]]] = {
    "validates": [("value", "String")],
    "transforms": [("value", "String")],
    "reads": [("source", "String")],
    "creates": [],
    "matches": [("value", "Value")],
    "inputs": [("path", "String")],
    "outputs": [("value", "String")],
}

_VERB_RETURN_DEFAULTS: dict[str, str] = {
    "validates": "Boolean",
    "transforms": "String",
    "reads": "String",
    "creates": "String",
    "matches": "Boolean",
    "inputs": "String",
    "outputs": "Unit",
}


def pair_verbs_nouns(
    verbs: set[str],
    nouns: list[str],
    model_predict: Callable[[str, str], list[str]] | None = None,
) -> list[FunctionStub]:
    """Generate verb+noun pairings ranked by confidence.

    Each verb is paired with each noun. The model (if available) predicts
    likely parameter types and return types.
    """
    stubs: list[FunctionStub] = []
    for verb in sorted(verbs):
        for noun in nouns:
            params = _VERB_PARAM_HINTS.get(verb, [("value", "String")])
            ret = _VERB_RETURN_DEFAULTS.get(verb, "String")
            conf = 0.5
            if model_predict is not None:
                hits = model_predict(verb, noun)
                if noun in [h.lower() for h in hits]:
                    conf = 0.9
                else:
                    conf = 0.3
            stubs.append(FunctionStub(
                verb=verb, name=noun,
                params=params, return_type=ret,
                confidence=conf,
            ))
    return sorted(stubs, key=lambda s: -s.confidence)


# ── Docstring-based function lookup ─────────────────────────────


def implied_functions(
    text: str,
    docstring_index: dict[str, list[dict]] | None = None,
) -> list[dict]:
    """Return stdlib functions implied by words in prose text.

    Each result: {"module": "Hash", "name": "sha256", "verb": "creates",
                  "doc": "Hash a byte array to SHA-256 digest", "score": 0.8}

    Score is based on word overlap between text and function docstring.
    """
    if docstring_index is None:
        return []
    words = set(re.findall(r"[a-z]{3,}", text.lower()))
    if not words:
        return []
    candidates: dict[tuple[str, str], dict] = {}  # (module, name) → best entry

    for word in words:
        for entry in docstring_index.get(word, []):
            key = (entry["module"], entry["name"])
            if key not in candidates:
                candidates[key] = {**entry, "matched_words": set()}
            candidates[key]["matched_words"].add(word)

    results = []
    for _key, entry in candidates.items():
        doc_words = set(re.findall(r"[a-z]{3,}", entry["doc"].lower()))
        overlap = entry["matched_words"] & doc_words
        score = len(overlap) / max(len(words), 1)
        results.append({
            "module": entry["module"],
            "name": entry["name"],
            "verb": entry["verb"],
            "doc": entry["doc"],
            "score": round(score, 3),
        })

    return sorted(results, key=lambda r: -r["score"])
