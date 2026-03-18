"""PDAT-backed NLP data stores.

Loads verb synonyms and stdlib function indexes from pre-compiled PDAT
binary files.  Falls back to in-memory construction when the PDAT
files are missing (e.g. during development or if the package data
is incomplete).
"""

from __future__ import annotations

import importlib.resources
import re
from collections import defaultdict
from pathlib import Path

from prove.store_binary import read_pdat, write_pdat

# ── Module-level caches ──────────────────────────────────────────

_verb_map: dict[str, str] | None = None
_verb_groups: dict[str, list[str]] | None = None
_synonym_cache: dict[str, list[str]] | None = None
_similarity_matrix: dict[str, dict[str, float]] | None = None


# ── Data file resolution ─────────────────────────────────────────


def _data_path(filename: str) -> Path:
    """Return path to a file in the ``prove.data`` package."""
    ref = importlib.resources.files("prove.data").joinpath(filename)
    # resources.files() may return a Traversable; as_posix for Path compat
    return Path(str(ref))


# ── Verb synonym store ───────────────────────────────────────────


def load_verb_synonyms() -> dict[str, str]:
    """Load synonym → canonical verb map from PDAT.

    Returns a dict like ``{"transform": "transforms", ...}``.
    Falls back to the hardcoded ``_SYNONYM_TO_VERB`` if the PDAT is missing.
    """
    global _verb_map
    if _verb_map is not None:
        return _verb_map

    dat = _data_path("verb_synonyms.dat")
    if dat.is_file():
        data = read_pdat(dat)
        _verb_map = {variant: values[0] for variant, values in data["variants"]}
        return _verb_map

    # Fallback: build from the hardcoded dict
    from prove._nl_intent import VERB_SYNONYMS

    _verb_map = {syn: verb for verb, syns in VERB_SYNONYMS.items() for syn in syns}
    return _verb_map


def load_verb_groups() -> dict[str, list[str]]:
    """Load canonical verb → [synonyms] map.

    Reverse of :func:`load_verb_synonyms`.
    """
    global _verb_groups
    if _verb_groups is not None:
        return _verb_groups

    synonym_map = load_verb_synonyms()
    groups: dict[str, list[str]] = defaultdict(list)
    for syn, verb in synonym_map.items():
        groups[verb].append(syn)
    _verb_groups = dict(groups)
    return _verb_groups


# ── Synonym cache store ──────────────────────────────────────────


def load_synonym_cache() -> dict[str, list[str]]:
    """Load WordNet-expanded synonym cache from PDAT.

    Returns a dict like ``{"transform": ["convert", "change", ...], ...}``.
    Falls back to empty dict if the PDAT is missing.
    """
    global _synonym_cache
    if _synonym_cache is not None:
        return _synonym_cache

    dat = _data_path("synonym_cache.dat")
    if dat.is_file():
        data = read_pdat(dat)
        _synonym_cache = {
            variant: values[0].split("|") if values[0] else []
            for variant, values in data["variants"]
        }
        return _synonym_cache

    _synonym_cache = {}
    return _synonym_cache


def build_synonym_cache() -> Path:
    """Build ``synonym_cache.dat`` with WordNet-expanded synonyms.

    Requires NLTK with WordNet data.  Returns the path to the written file.
    Raises if WordNet is not available.
    """
    from nltk.corpus import wordnet  # type: ignore[import-untyped]

    # Probe that data is actually downloaded
    wordnet.synsets("test")

    from prove._nl_intent import VERB_SYNONYMS

    # Collect all words from VERB_SYNONYMS + common intent nouns
    seed_words: set[str] = set()
    for syns in VERB_SYNONYMS.values():
        seed_words.update(syns)
    seed_words.update(
        [
            "file",
            "text",
            "string",
            "number",
            "list",
            "array",
            "table",
            "path",
            "hash",
            "format",
            "parse",
            "error",
            "result",
            "option",
            "byte",
            "character",
            "pattern",
            "time",
            "random",
            "network",
            "log",
            "system",
            "math",
            "length",
            "split",
            "join",
            "sort",
            "filter",
            "map",
            "reduce",
            "count",
            "find",
            "search",
            "replace",
        ]
    )

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

    out = _data_path("synonym_cache.dat")
    write_pdat(out, "SynonymCache", ["String"], variants)
    return out


# ── Similarity matrix store ─────────────────────────────────────


def load_similarity_matrix(
    project_dir: Path | None = None,
) -> dict[str, dict[str, float]]:
    """Load pre-computed pairwise similarity scores from PDAT.

    Returns nested dict ``{"fn1": {"fn2": 0.847, ...}, ...}``.
    Falls back to empty dict if the PDAT is missing.
    """
    global _similarity_matrix
    if _similarity_matrix is not None:
        return _similarity_matrix

    dat: Path | None = None
    if project_dir is not None:
        candidate = project_dir / ".prove" / "similarity_matrix.dat"
        if candidate.is_file():
            dat = candidate

    if dat is None:
        _similarity_matrix = {}
        return _similarity_matrix

    data = read_pdat(dat)
    matrix: dict[str, dict[str, float]] = {}
    for variant, values in data["variants"]:
        parts = variant.split("|", 1)
        if len(parts) != 2:
            continue
        fn1, fn2 = parts
        try:
            score = float(values[0])
        except (ValueError, IndexError):
            continue
        matrix.setdefault(fn1, {})[fn2] = score
        matrix.setdefault(fn2, {})[fn1] = score
    _similarity_matrix = matrix
    return _similarity_matrix


def build_similarity_matrix(project_dir: Path | None = None) -> Path:
    """Build and write ``similarity_matrix.dat`` in project's ``.prove/`` dir.

    Uses ``text_similarity()`` from ``nlp.py`` for each pair of stdlib
    functions.  Returns the path to the written file.
    """
    from prove.stdlib_loader import _STDLIB_MODULES, load_stdlib

    keys: list[str] = []
    descs: list[str] = []
    for module_key in sorted(_STDLIB_MODULES):
        sigs = load_stdlib(module_key)
        for fn in sigs:
            key = f"{module_key}.{fn.name}"
            desc = fn.doc_comment or fn.name
            keys.append(key)
            descs.append(desc)

    # Compute Jaccard similarity directly on normalized word sets.
    # This avoids O(n^2) spaCy Doc creations via text_similarity(),
    # which is prohibitively slow for ~315 stdlib functions (~49K pairs)
    # and falls back to Jaccard anyway since en_core_web_sm has no vectors.
    from prove._nl_intent import _normalize_noun_fallback

    word_sets = [
        {_normalize_noun_fallback(w) for w in re.findall(r"[a-z]+", d.lower()) if len(w) >= 3}
        for d in descs
    ]

    variants: list[tuple[str, list[str]]] = []
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            if not word_sets[i] or not word_sets[j]:
                continue
            intersection = word_sets[i] & word_sets[j]
            union = word_sets[i] | word_sets[j]
            score = len(intersection) / len(union)
            if score > 0.1:
                pair_key = f"{keys[i]}|{keys[j]}"
                variants.append((pair_key, [f"{score:.3f}"]))

    if project_dir is None:
        project_dir = Path.cwd()

    prove_dir = project_dir / ".prove"
    prove_dir.mkdir(exist_ok=True)

    out = prove_dir / "similarity_matrix.dat"
    write_pdat(out, "SimilarityMatrix", ["String"], variants)
    return out


# ── Semantic features store ─────────────────────────────────────


def build_semantic_features(project_dir: Path | None = None) -> Path:
    """Build ``semantic_features.dat`` with lemmatized keywords per function.

    Returns the path to the written file.
    """
    from prove.stdlib_loader import _STDLIB_MODULES, load_stdlib

    variants: list[tuple[str, list[str]]] = []
    for module_key in sorted(_STDLIB_MODULES):
        sigs = load_stdlib(module_key)
        for fn in sigs:
            key = f"{module_key}.{fn.name}"
            verb = fn.verb or ""
            # Extract keywords from name and doc
            text = f"{fn.name} {fn.doc_comment or ''}"
            words = re.findall(r"[a-z]{3,}", text.lower())
            # Try lemmatization when available
            try:
                from prove.nlp import lemmatize

                lemmas = sorted({lemmatize(w) for w in words})
            except Exception:
                lemmas = sorted(set(words))
            keywords = " ".join(lemmas)
            variants.append((key, [module_key, verb, keywords]))

    if project_dir is None:
        project_dir = Path.cwd()

    prove_dir = project_dir / ".prove"
    prove_dir.mkdir(exist_ok=True)

    out = prove_dir / "semantic_features.dat"
    write_pdat(out, "SemanticFeatures", ["String", "String", "String"], variants)
    return out


def load_semantic_features(
    project_dir: Path | None = None,
) -> dict[str, dict]:
    """Load semantic features per stdlib function from PDAT.

    Returns ``{"text.length": {"module": "text", "verb": "reads",
    "keywords": "length string ..."}, ...}``.
    Falls back to empty dict if the PDAT is missing.
    """
    dat: Path | None = None
    if project_dir is not None:
        candidate = project_dir / ".prove" / "semantic_features.dat"
        if candidate.is_file():
            dat = candidate

    if dat is None:
        return {}

    data = read_pdat(dat)
    result: dict[str, dict] = {}
    for key, cols in data["variants"]:
        result[key] = {
            "module": cols[0],
            "verb": cols[1],
            "keywords": cols[2],
        }
    return result


# ── Stdlib index store ───────────────────────────────────────────


def build_stdlib_index(project_dir: Path | None = None) -> Path:
    """Generate ``stdlib_index.dat`` in the project's ``.prove/`` dir.

    Loads all stdlib modules and writes a PDAT with one row per function:
    variant = ``module.function_name``, columns = [module, verb, doc].

    Returns the path to the written file.
    """
    from prove.stdlib_loader import _STDLIB_MODULES, load_stdlib

    variants: list[tuple[str, list[str]]] = []
    for module_key in sorted(_STDLIB_MODULES):
        sigs = load_stdlib(module_key)
        for fn in sigs:
            key = f"{module_key}.{fn.name}"
            verb = fn.verb or ""
            doc = fn.doc_comment or ""
            variants.append((key, [module_key, verb, doc]))

    if project_dir is None:
        project_dir = Path.cwd()

    prove_dir = project_dir / ".prove"
    prove_dir.mkdir(exist_ok=True)

    out = prove_dir / "stdlib_index.dat"
    write_pdat(out, "StdlibIndex", ["String", "String", "String"], variants)
    return out


def load_stdlib_index(
    project_dir: Path | None = None,
) -> dict[str, list[dict]]:
    """Load stdlib docstring index from PDAT.

    Returns a word → [{module, name, verb, doc}] mapping suitable for
    ``implied_functions()`` in ``_nl_intent.py``.

    Falls back to building the index in memory from ``load_stdlib()``.
    """
    variants: list[tuple[str, list[str]]] | None = None

    # Try PDAT file first
    if project_dir is not None:
        dat = project_dir / ".prove" / "stdlib_index.dat"
        if dat.is_file():
            data = read_pdat(dat)
            variants = data["variants"]

    if variants is None:
        # Fallback: build from stdlib loader
        from prove.stdlib_loader import _STDLIB_MODULES, load_stdlib

        variants = []
        for module_key in sorted(_STDLIB_MODULES):
            sigs = load_stdlib(module_key)
            for fn in sigs:
                key = f"{module_key}.{fn.name}"
                verb = fn.verb or ""
                doc = fn.doc_comment or ""
                variants.append((key, [module_key, verb, doc]))

    # Build word→[entry] index
    index: dict[str, list[dict]] = defaultdict(list)
    for key, cols in variants:
        module = cols[0]
        verb = cols[1]
        doc = cols[2]
        # key is "module.name"
        name = key.split(".", 1)[1] if "." in key else key
        entry = {"module": module, "name": name, "verb": verb, "doc": doc}
        # Index by each 3+ letter word in doc + name
        words = set(re.findall(r"[a-z]{3,}", f"{name} {doc}".lower()))
        for word in words:
            index[word].append(entry)

    return dict(index)


# ── LSP ML store ─────────────────────────────────────────────────


_lsp_bigrams: dict[str, list[tuple[str, int]]] | None = None
_lsp_completions: dict[tuple[str, str], list[str]] | None = None
_lsp_docstrings: dict[str, list[dict]] | None = None
_lsp_from_blocks: dict[tuple[str, str], list[str]] | None = None


def load_lsp_bigrams() -> dict[str, list[tuple[str, int]]]:
    """Load global bigram model from prove.data.

    Returns ``{prev1: [(next_token, count), ...]}``.
    """
    global _lsp_bigrams
    if _lsp_bigrams is not None:
        return _lsp_bigrams

    _lsp_bigrams = {}
    bigram_path = _data_path("lsp/bigrams/current.prv")
    if not bigram_path.exists():
        return _lsp_bigrams

    try:
        for line in bigram_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line.startswith("r") or "|" not in line:
                continue
            parts = [p.strip() for p in line.split("|")[1:]]
            if len(parts) >= 3:
                prev1 = _strip_quotes(parts[0])
                next_tok = _strip_quotes(parts[1])
                try:
                    count = int(parts[2])
                except ValueError:
                    continue
                _lsp_bigrams.setdefault(prev1, []).append((next_tok, count))
    except Exception:
        pass

    return _lsp_bigrams


def load_lsp_completions() -> dict[tuple[str, str], list[str]]:
    """Load global completion model from prove.data.

    Returns ``{(prev2, prev1): [top_tokens...]}``.
    """
    global _lsp_completions
    if _lsp_completions is not None:
        return _lsp_completions

    _lsp_completions = {}
    comp_path = _data_path("lsp/completions/current.prv")
    if not comp_path.exists():
        return _lsp_completions

    try:
        for line in comp_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line.startswith("r") or "|" not in line:
                continue
            parts = [p.strip() for p in line.split("|")[1:]]
            if len(parts) >= 3:
                prev2 = _strip_quotes(parts[0])
                prev1 = _strip_quotes(parts[1])
                tokens_str = _strip_quotes(parts[2])
                tokens = [t for t in tokens_str.split("|") if t]
                _lsp_completions[(prev2, prev1)] = tokens
    except Exception:
        pass

    return _lsp_completions


def load_lsp_docstrings() -> dict[str, list[dict]]:
    """Load global docstring index from prove.data.

    Returns ``{keyword: [{module, name, verb, doc}, ...]}``.
    """
    global _lsp_docstrings
    if _lsp_docstrings is not None:
        return _lsp_docstrings

    _lsp_docstrings = defaultdict(list)
    doc_path = _data_path("lsp/docstrings/current.prv")
    if not doc_path.exists():
        return _lsp_docstrings

    try:
        for line in doc_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line.startswith("r") or "|" not in line:
                continue
            parts = [p.strip() for p in line.split("|")[1:]]
            if len(parts) >= 5:
                keyword = _strip_quotes(parts[0])
                entry = {
                    "module": _strip_quotes(parts[1]),
                    "name": _strip_quotes(parts[2]),
                    "verb": _strip_quotes(parts[3]),
                    "doc": _strip_quotes(parts[4]),
                }
                _lsp_docstrings[keyword].append(entry)
    except Exception:
        pass

    return _lsp_docstrings


def load_lsp_from_blocks() -> dict[tuple[str, str], list[str]]:
    """Load from-block n-gram model from prove.data.

    Returns ``{(prev2, prev1): [top_tokens...]}``.
    """
    global _lsp_from_blocks
    if _lsp_from_blocks is not None:
        return _lsp_from_blocks

    _lsp_from_blocks = {}
    fb_path = _data_path("lsp/from_blocks/current.prv")
    if not fb_path.exists():
        return _lsp_from_blocks

    try:
        for line in fb_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line.startswith("r") or "|" not in line:
                continue
            parts = [p.strip() for p in line.split("|")[1:]]
            if len(parts) >= 3:
                prev2 = _strip_quotes(parts[0])
                prev1 = _strip_quotes(parts[1])
                tokens_str = _strip_quotes(parts[2])
                tokens = [t for t in tokens_str.split("|") if t]
                _lsp_from_blocks[(prev2, prev1)] = tokens
    except Exception:
        pass

    return _lsp_from_blocks


def _strip_quotes(s: str) -> str:
    """Strip leading/trailing double-quotes from a Prove string literal."""
    if s.startswith('"') and s.endswith('"'):
        return s[1:-1]
    return s


# ── Reset (for testing) ──────────────────────────────────────────


def _reset() -> None:
    """Clear all cached store data.  For testing only."""
    global _verb_map, _verb_groups, _synonym_cache, _similarity_matrix
    global _lsp_bigrams, _lsp_completions, _lsp_docstrings, _lsp_from_blocks
    _verb_map = None
    _verb_groups = None
    _synonym_cache = None
    _similarity_matrix = None
    _lsp_bigrams = None
    _lsp_completions = None
    _lsp_docstrings = None
    _lsp_from_blocks = None
