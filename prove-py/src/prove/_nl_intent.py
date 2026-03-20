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
    "transforms": [
        "transforms",
        "transform",
        "converts",
        "convert",
        "computes",
        "compute",
        "calculates",
        "calculate",
        "processes",
        "process",
        "produces",
        "produce",
        "updates",
        "update",
        "modifies",
        "modify",
    ],
    "validates": [
        "validates",
        "validate",
        "checks",
        "check",
        "verifies",
        "verify",
        "ensures",
        "ensure",
        "guards",
        "guard",
    ],
    "reads": [
        "reads",
        "read",
        "fetches",
        "fetch",
        "loads",
        "load",
        "retrieves",
        "retrieve",
        "queries",
        "query",
    ],
    "creates": [
        "creates",
        "create",
        "makes",
        "make",
        "builds",
        "build",
        "constructs",
        "construct",
        "generates",
        "generate",
    ],
    "matches": [
        "matches",
        "match",
        "compares",
        "compare",
        "classifies",
        "classify",
        "selects",
        "select",
    ],
    "outputs": [
        "outputs",
        "output",
        "writes",
        "write",
        "prints",
        "print",
        "sends",
        "send",
        "emits",
        "emit",
        "logs",
        "log",
        "displays",
        "display",
        "saves",
        "save",
        "stores",
        "store",
        "persists",
        "persist",
    ],
    "inputs": [
        "inputs",
        "input",
        "receives",
        "receive",
        "accepts",
        "accept",
        "parses",
        "parse",
        "takes",
        "take",
    ],
    "listens": ["listens", "listen", "monitors", "monitor", "watches", "watch", "waits", "wait"],
    "detached": [
        "detached",
        "detach",
        "fires",
        "fire",
        "spawns",
        "spawn",
        "forks",
        "fork",
        "backgrounds",
        "background",
    ],
    "attached": ["attached", "attach", "awaits", "await", "joins", "join", "child", "worker"],
    "streams": ["streams", "stream", "blocks", "block", "polls", "poll", "loops", "loop"],
}

_HARDCODED_SYNONYM_TO_VERB: dict[str, str] = {
    syn: verb for verb, syns in VERB_SYNONYMS.items() for syn in syns
}

try:
    from prove.nlp_store import load_verb_synonyms

    _SYNONYM_TO_VERB: dict[str, str] = {**_HARDCODED_SYNONYM_TO_VERB, **load_verb_synonyms()}
except Exception:
    _SYNONYM_TO_VERB: dict[str, str] = _HARDCODED_SYNONYM_TO_VERB


def normalize_verb(word: str) -> str | None:
    """Return canonical verb for a synonym/singular, or None if not recognized."""
    return _SYNONYM_TO_VERB.get(word.lower())


def implied_verbs(text: str) -> set[str]:
    """Return Prove verb keywords implied by action words in prose text.

    When spaCy is available, NLP results are merged with the exact-synonym
    fallback.  This compensates for POS-tagging errors on short imperative
    sentences (spaCy often misclassifies sentence-initial verbs as nouns).
    """
    result = _implied_verbs_fallback(text)
    from prove.nlp import extract_parts, has_nlp_backend

    if has_nlp_backend():
        parts = extract_parts(text)
        for v in parts.verbs:
            canonical = normalize_verb(v)
            if canonical:
                result.add(canonical)
    return result


def _implied_verbs_fallback(text: str) -> set[str]:
    """Return Prove verb keywords implied by action words in prose text (no NLP)."""
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

    names: set[str] = {p.name for p in fd.params}  # noqa: E501

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
    """Return the root form of *word*, using NLP lemmatizer when available."""
    from prove.nlp import has_nlp_backend, lemmatize

    if has_nlp_backend():
        return lemmatize(word)
    return _normalize_noun_fallback(word)


def _normalize_noun_fallback(word: str) -> str:
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
    """True if any word in prose matches a body token after normalization."""
    from prove.nlp import has_nlp_backend, text_similarity

    if has_nlp_backend():
        score = text_similarity(prose, " ".join(tokens))
        if score > 0.2:
            return True
    return _prose_overlaps_fallback(prose, tokens)


def _prose_overlaps_fallback(prose: str, tokens: set[str]) -> bool:
    """True if any word in prose matches a body token after normalization (no NLP).

    Both prose words and token parts (split on ``_``) are reduced to their
    root form via ``_normalize_noun_fallback`` before comparison.
    """
    prose_words = {
        _normalize_noun_fallback(w.lower()) for w in re.findall(r"[a-zA-Z_][a-zA-Z0-9_]*", prose)
    }
    token_roots: set[str] = set()
    for t in tokens:
        for part in split_name(t):
            token_roots.add(_normalize_noun_fallback(part))
    return bool(prose_words & token_roots)


# ── Noun extraction ──────────────────────────────────────────────

_NOUN_STOPS = frozenset(
    {
        "the",
        "a",
        "an",
        "this",
        "that",
        "each",
        "every",
        "all",
        "some",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "has",
        "have",
        "had",
        "do",
        "does",
        "did",
        "will",
        "would",
        "could",
        "should",
        "can",
        "may",
        "might",
        "and",
        "or",
        "but",
        "not",
        "no",
        "nor",
        "from",
        "into",
        "with",
        "for",
        "to",
        "of",
        "in",
        "on",
        "at",
        "by",
        "it",
        "its",
        "them",
        "their",
        "they",
        "module",
        "function",
        "type",
        "using",
        "against",
        "between",
    }
)


def extract_nouns(text: str) -> list[str]:
    """Extract candidate noun phrases from prose (domain objects, not verbs)."""
    from prove.nlp import extract_parts, has_nlp_backend

    if has_nlp_backend():
        parts = extract_parts(text)
        return parts.nouns
    return _extract_nouns_fallback(text)


def _extract_nouns_fallback(text: str) -> list[str]:
    """Extract candidate noun phrases from prose (no NLP).

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
        norm = _normalize_noun_fallback(low)
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
            stubs.append(
                FunctionStub(
                    verb=verb,
                    name=noun,
                    params=params,
                    return_type=ret,
                    confidence=conf,
                )
            )
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
        results.append(
            {
                "module": entry["module"],
                "name": entry["name"],
                "verb": entry["verb"],
                "doc": entry["doc"],
                "score": round(score, 3),
            }
        )

    return sorted(results, key=lambda r: -r["score"])


# ── Type body inference ──────────────────────────────────────────

_RECORD_INDICATORS = frozenset(
    {
        "paired with",
        "has a",
        "contains",
        "consisting of",
        "with a",
        "composed of",
        "made up of",
    }
)
_ALGEBRAIC_INDICATORS = frozenset(
    {
        "either",
        "one of",
    }
)
_REFINEMENT_INDICATORS = frozenset(
    {
        "where",
        "within",
        "bounded",
        "positive",
        "non-negative",
        "at least",
        "at most",
        "greater than",
        "less than",
    }
)


@dataclass
class TypeBodyHint:
    """Inferred structure for a vocabulary type definition."""

    kind: str  # "record", "algebraic", "refinement", "opaque"
    fields: list[tuple[str, str]] = field(default_factory=list)
    variants: list[tuple[str, list[tuple[str, str]]]] = field(default_factory=list)
    base_type: str | None = None
    constraint: str | None = None


def _infer_type_body_nlp(description: str) -> TypeBodyHint | None:
    """Try to infer type body via spaCy dependency parse."""
    from prove.nlp import has_spacy

    if not has_spacy():
        return None
    from prove.nlp import _nlp_model

    assert _nlp_model is not None
    doc = _nlp_model(description)

    # Look for conjunction patterns indicating algebraic types
    has_conj = any(tok.dep_ == "conj" for tok in doc)
    desc_lower = description.lower()
    if has_conj and any(ind in desc_lower for ind in _ALGEBRAIC_INDICATORS):
        variants = _extract_variants_from_text(description)
        if variants:
            return TypeBodyHint(kind="algebraic", variants=variants)

    # Look for prepositional phrases indicating record fields
    if any(ind in desc_lower for ind in _RECORD_INDICATORS):
        fields = _extract_fields_from_text(description)
        if fields:
            return TypeBodyHint(kind="record", fields=fields)

    # Look for adjective modifiers indicating refinement
    if any(ind in desc_lower for ind in _REFINEMENT_INDICATORS):
        base, constraint = _extract_refinement_from_text(description)
        if base and constraint:
            return TypeBodyHint(kind="refinement", base_type=base, constraint=constraint)

    return None


def infer_type_body(description: str) -> TypeBodyHint:
    """Infer type body structure from vocabulary description.

    3-tier: spaCy dep parse, keyword matching, opaque fallback.
    """
    # Tier 1: NLP-based inference
    nlp_hint = _infer_type_body_nlp(description)
    if nlp_hint is not None:
        return nlp_hint

    # Tier 2: Keyword matching
    desc_lower = description.lower()

    # Algebraic: "either X or Y"
    if any(ind in desc_lower for ind in _ALGEBRAIC_INDICATORS):
        variants = _extract_variants_from_text(description)
        if variants:
            return TypeBodyHint(kind="algebraic", variants=variants)

    # Record: "paired with", "has a", etc.
    if any(ind in desc_lower for ind in _RECORD_INDICATORS):
        fields = _extract_fields_from_text(description)
        if fields:
            return TypeBodyHint(kind="record", fields=fields)

    # Refinement: "positive", "bounded", etc.
    if any(ind in desc_lower for ind in _REFINEMENT_INDICATORS):
        base, constraint = _extract_refinement_from_text(description)
        if base and constraint:
            return TypeBodyHint(kind="refinement", base_type=base, constraint=constraint)

    # Tier 3: Opaque fallback
    return TypeBodyHint(kind="opaque")


def _extract_variants_from_text(description: str) -> list[tuple[str, list[tuple[str, str]]]]:
    """Extract algebraic variants from text like 'either X or Y'."""
    desc_lower = description.lower()

    # Pattern: "either an X or a Y"
    m = re.search(r"either\s+(?:an?\s+)?(.+?)\s+or\s+(?:an?\s+)?(.+?)(?:\s*$|\.)", desc_lower)
    if m:
        variants: list[tuple[str, list[tuple[str, str]]]] = []
        for part in (m.group(1), m.group(2)):
            words = part.strip().split()
            if not words:
                continue
            # Last significant word becomes the variant name
            variant_name = _to_pascal_case(words[-1])
            # Preceding words become field hints
            fields: list[tuple[str, str]] = []
            if len(words) > 1:
                field_name = _to_snake_case(words[0])
                fields.append((field_name, "String"))
            variants.append((variant_name, fields))
        return variants

    # Pattern: "one of X, Y, or Z"
    m = re.search(r"one of\s+(.+?)(?:\s*$|\.)", desc_lower)
    if m:
        items = re.split(r",\s*(?:or\s+)?|\s+or\s+", m.group(1))
        variants = []
        for item in items:
            item = item.strip()
            if item:
                words = item.split()
                variant_name = _to_pascal_case(words[-1])
                fields = []
                if len(words) > 1:
                    field_name = _to_snake_case(words[0])
                    fields.append((field_name, "String"))
                variants.append((variant_name, fields))
        return variants

    return []


def _extract_fields_from_text(description: str) -> list[tuple[str, str]]:
    """Extract record fields from text like 'X paired with Y'."""
    desc_lower = description.lower()
    fields: list[tuple[str, str]] = []

    # Pattern: "a X paired with a Y"
    m = re.search(
        r"(?:an?\s+)?(\w+(?:\s+\w+)?)\s+paired with\s+(?:an?\s+)?(\w+(?:\s+\w+)?)", desc_lower
    )  # noqa: E501
    if m:
        fields.append((_to_snake_case(m.group(1).split()[-1]), "String"))
        fields.append((_to_snake_case(m.group(2).split()[-1]), "String"))
        return fields

    # Pattern: "has a X and a Y" / "contains X and Y"
    for indicator in ("has a", "contains", "consisting of", "with a", "composed of"):
        if indicator in desc_lower:
            after = desc_lower.split(indicator, 1)[1]
            parts = re.split(r"\s+and\s+(?:an?\s+)?|\s*,\s*(?:an?\s+)?", after)
            for part in parts:
                words = part.strip().split()
                if words:
                    field_name = _to_snake_case(words[-1])
                    if field_name and len(field_name) >= 2:
                        fields.append((field_name, "String"))
            if fields:
                return fields

    return []


def _extract_refinement_from_text(description: str) -> tuple[str | None, str | None]:
    """Extract refinement base type and constraint from description."""
    desc_lower = description.lower()

    # "positive number/integer"
    if "positive" in desc_lower:
        if "integer" in desc_lower or "number" in desc_lower:
            return "Integer", "self > 0"
        if "decimal" in desc_lower or "float" in desc_lower:
            return "Float", "self > 0.0"
        return "Integer", "self > 0"

    # "non-negative number/integer"
    if "non-negative" in desc_lower:
        if "integer" in desc_lower or "number" in desc_lower:
            return "Integer", "self >= 0"
        return "Integer", "self >= 0"

    # "bounded" / "within"
    if "bounded" in desc_lower or "within" in desc_lower:
        return "Integer", "self >= 0"

    # "at least N"
    m = re.search(r"at least (\d+)", desc_lower)
    if m:
        return "Integer", f"self >= {m.group(1)}"

    # "at most N"
    m = re.search(r"at most (\d+)", desc_lower)
    if m:
        return "Integer", f"self <= {m.group(1)}"

    # "greater than N"
    m = re.search(r"greater than (\d+)", desc_lower)
    if m:
        return "Integer", f"self > {m.group(1)}"

    # "less than N"
    m = re.search(r"less than (\d+)", desc_lower)
    if m:
        return "Integer", f"self < {m.group(1)}"

    return None, None


def _to_pascal_case(word: str) -> str:
    """Convert a word to PascalCase."""
    return word.capitalize()


def _to_snake_case(word: str) -> str:
    """Convert a word to snake_case."""
    return word.lower().replace(" ", "_")


# ── Import inference ─────────────────────────────────────────────


def infer_stdlib_imports(
    stdlib_matches: list[object],
) -> dict[str, dict[str | None, list[str]]]:
    """Group stdlib function matches by module -> verb -> names.

    Each StdlibMatch has .module, .function.verb, .function.name.
    Returns: {module: {verb_or_None: [name, ...]}}.
    """
    result: dict[str, dict[str | None, list[str]]] = {}
    seen: set[tuple[str, str]] = set()

    for match in stdlib_matches:
        mod = match.module.capitalize()
        fn = match.function
        key = (mod, fn.name)
        if key in seen:
            continue
        seen.add(key)

        if mod not in result:
            result[mod] = {}
        verb = fn.verb if fn.verb else None
        if verb not in result[mod]:
            result[mod][verb] = []
        result[mod][verb].append(fn.name)

    return result


# ── Constant inference ───────────────────────────────────────────


def infer_constants(
    constraints: list[object],
) -> list[tuple[str, str, str, str]]:
    """Extract named constants from constraint text.

    Looks for patterns like:
    - "maximum N attempts" -> MAX_ATTEMPTS as Integer = N
    - "timeout of N seconds" -> TIMEOUT_SECONDS as Integer = N
    - "limit to N" -> LIMIT as Integer = N

    Returns list of (name, type, value, doc) tuples.
    """
    results: list[tuple[str, str, str, str]] = []
    seen_names: set[str] = set()

    for c in constraints:
        text = c.text if hasattr(c, "text") and c.text else str(c)
        text_lower = text.lower()

        # "maximum N UNIT"
        m = re.search(r"maximum\s+(\d+)\s+(\w+)", text_lower)
        if m:
            value = m.group(1)
            unit = m.group(2).rstrip("s")  # strip trailing s
            name = f"MAX_{unit.upper()}"
            if name not in seen_names:
                seen_names.add(name)
                results.append((name, "Integer", value, f"Maximum {unit} (from constraint)"))

        # "timeout of N seconds/minutes"
        m = re.search(r"timeout\s+(?:of\s+)?(\d+)\s+(\w+)", text_lower)
        if m:
            value = m.group(1)
            unit = m.group(2).rstrip("s")
            name = f"TIMEOUT_{unit.upper()}"
            if name not in seen_names:
                seen_names.add(name)
                results.append((name, "Integer", value, f"Timeout in {unit}s (from constraint)"))

        # "limit to N" / "limit of N"
        m = re.search(r"limit\s+(?:to|of)\s+(\d+)", text_lower)
        if m:
            value = m.group(1)
            name = "LIMIT"
            if name not in seen_names:
                seen_names.add(name)
                results.append((name, "Integer", value, "Limit (from constraint)"))

        # "at most N UNIT"
        m = re.search(r"at most\s+(\d+)\s+(\w+)", text_lower)
        if m:
            value = m.group(1)
            unit = m.group(2).rstrip("s")
            name = f"MAX_{unit.upper()}"
            if name not in seen_names:
                seen_names.add(name)
                results.append((name, "Integer", value, f"Maximum {unit} (from constraint)"))

    return results


# ── Comptime inference ───────────────────────────────────────────

_COMPTIME_INDICATORS = frozenset(
    {
        "at compile time",
        "compile-time",
        "static",
        "precomputed",
        "built-in",
    }
)


def infer_comptime(
    constraints: list[object],
) -> list[tuple[str, str, str, str]]:
    """Extract comptime hints from constraints.

    Returns list of (name, type, expression, doc) tuples.
    Only generates comptime when constraints explicitly mention compile-time.
    """
    results: list[tuple[str, str, str, str]] = []

    for c in constraints:
        text = c.text if hasattr(c, "text") and c.text else str(c)
        text_lower = text.lower()

        if not any(ind in text_lower for ind in _COMPTIME_INDICATORS):
            continue

        # "precomputed table of X" / "static table of X"
        m = re.search(
            r"(?:precomputed|static|compile-time|built-in)\s+(?:table|map|list|set)\s+of\s+(\w+)",
            text_lower,
        )  # noqa: E501
        if m:
            subject = m.group(1)
            name = f"{subject.upper()}_TABLE"
            results.append(
                (
                    name,
                    "Table<String, String>",
                    "Table.empty()",
                    f"Compile-time {subject} table (from constraint)",
                )
            )
            continue

        # "X computed at compile time" / "X is precomputed"
        m = re.search(
            r"(\w+)\s+(?:computed at compile time|is precomputed|is static|is built-in)", text_lower
        )  # noqa: E501
        if m:
            subject = m.group(1)
            name = subject.upper()
            results.append(
                (
                    name,
                    "String",
                    '""',
                    f"Compile-time {subject} (from constraint)",
                )
            )

    return results
