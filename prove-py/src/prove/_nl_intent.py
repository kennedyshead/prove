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

# ── Verb synonym map ────────────────────────────────────────────
# Canonical Prove verb → all recognized prose synonyms (including singular forms).
VERB_SYNONYMS: dict[str, list[str]] = {
    "transforms": ["transforms", "transform", "converts", "convert", "computes", "compute",
                    "calculates", "calculate", "processes", "process", "produces", "produce"],
    "validates":  ["validates", "validate", "checks", "check", "verifies", "verify",
                    "ensures", "ensure", "guards", "guard"],
    "reads":      ["reads", "read", "fetches", "fetch", "loads", "load",
                    "retrieves", "retrieve", "queries", "query"],
    "creates":    ["creates", "create", "makes", "make", "builds", "build",
                    "constructs", "construct", "generates", "generate"],
    "matches":    ["matches", "match", "compares", "compare", "classifies", "classify",
                    "selects", "select"],
    "outputs":    ["outputs", "output", "writes", "write", "prints", "print",
                    "sends", "send", "emits", "emit", "logs", "log", "displays", "display"],
    "inputs":     ["inputs", "input", "receives", "receive", "accepts", "accept",
                    "parses", "parse", "takes", "take"],
    "listens":    ["listens", "listen", "monitors", "monitor", "watches", "watch",
                    "waits", "wait"],
    "detached":   ["detached", "detach", "fires", "fire", "spawns", "spawn",
                    "forks", "fork", "backgrounds", "background"],
    "attached":   ["attached", "attach", "awaits", "await", "joins", "join",
                    "child", "worker"],
    "streams":    ["streams", "stream", "blocks", "block", "polls", "poll",
                    "loops", "loop"],
}

_SYNONYM_TO_VERB: dict[str, str] = {
    syn: verb for verb, syns in VERB_SYNONYMS.items() for syn in syns
}


def normalize_verb(word: str) -> str | None:
    """Return canonical verb for a synonym/singular, or None if not recognized."""
    return _SYNONYM_TO_VERB.get(word.lower())


def implied_verbs(text: str) -> set[str]:
    """Return Prove verb keywords implied by action words in prose text."""
    words = re.findall(r"[a-z]+", text.lower())
    result: set[str] = set()
    for word in words:
        canonical = _SYNONYM_TO_VERB.get(word)
        if canonical is not None:
            result.add(canonical)
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


def normalize_noun(word: str) -> str:
    """Reduce a noun to its root form via ordered suffix stripping.

    Ordered rules (first match wins):
    1. -ation/-tion → strip
    2. -ment/-ments → strip
    3. -ness → strip
    4. -ing → strip (keep if root < 3 chars)
    5. -ies → replace with y
    6. -es → strip (only if root ends in s/x/z/sh/ch)
    7. -ed → strip (keep if root < 3 chars)
    8. -s → strip (not -ss)
    """
    w = word.lower()
    if w.endswith("ation"):
        root = w[:-5]
        if len(root) >= 3:
            return root
    if w.endswith("tion"):
        root = w[:-4]
        if len(root) >= 3:
            return root
    if w.endswith("ments"):
        root = w[:-5]
        if len(root) >= 3:
            return root
    if w.endswith("ment"):
        root = w[:-4]
        if len(root) >= 3:
            return root
    if w.endswith("ness"):
        root = w[:-4]
        if len(root) >= 3:
            return root
    if w.endswith("ing"):
        root = w[:-3]
        if len(root) >= 3:
            return root
        return w
    if w.endswith("ies"):
        root = w[:-3]
        if len(root) >= 1:
            return root + "y"
    if w.endswith("es"):
        root = w[:-2]
        if root and root[-1] in ("s", "x", "z") or root.endswith("sh") or root.endswith("ch"):
            if len(root) >= 3:
                return root
    if w.endswith("ed"):
        root = w[:-2]
        if len(root) >= 3:
            return root
        return w
    if w.endswith("s") and not w.endswith("ss"):
        root = w[:-1]
        if len(root) >= 3:
            return root
    return w


def split_name(name: str) -> list[str]:
    """Split a snake_case name into lowercase parts.

    ``hash_password`` → ``["hash", "password"]``
    """
    return [p.lower() for p in name.split("_") if p]


def prose_overlaps(prose: str, tokens: set[str]) -> bool:
    """True if any word in prose matches a body token after normalization.

    Both prose words and token parts (split on ``_``) are reduced to their
    root form via ``normalize_noun`` before comparison.
    """
    prose_words = {normalize_noun(w.lower())
                   for w in re.findall(r"[a-zA-Z_][a-zA-Z0-9_]*", prose)}
    token_roots: set[str] = set()
    for t in tokens:
        for part in split_name(t):
            token_roots.add(normalize_noun(part))
    return bool(prose_words & token_roots)


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

    Returns normalized lowercase words that are likely to become function
    names, type names, or parameter names.  Preserves order of first
    occurrence (by normalized form).
    """
    words = re.findall(r"[a-zA-Z_][a-zA-Z0-9_]*", text)
    seen: set[str] = set()
    nouns: list[str] = []

    for word in words:
        low = word.lower()
        if low in _NOUN_STOPS or len(low) < 3:
            continue
        # Skip words that are verb synonyms
        if low in _SYNONYM_TO_VERB:
            continue
        norm = normalize_noun(low)
        if norm in seen:
            continue
        seen.add(norm)
        nouns.append(norm)

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
