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


def prove_home() -> Path:
    """Return the user-level Prove home directory (``~/.prove/``)."""
    return Path.home() / ".prove"


def _data_path(filename: str) -> Path:
    """Return path for a Prove data file inside ``~/.prove/``."""
    return prove_home() / filename


# ── Store download / bootstrap ───────────────────────────────────

_stores_ensured: bool = False


def download_stores() -> bool:
    """Download and install ML stores to ``~/.prove/``.

    Returns True on success, False if the download fails (e.g. offline).
    Raises no exceptions — all errors are caught and reported to stderr.
    """
    import json
    import shutil
    import sys
    import tarfile
    import tempfile
    import urllib.request

    home = prove_home()
    home.mkdir(parents=True, exist_ok=True)
    (home / "cache").mkdir(exist_ok=True)

    print("prove: downloading ML stores to ~/.prove/ ...", file=sys.stderr)

    api_url = "https://code.botwork.se/api/v1/repos/Botwork/prove/releases/latest"
    try:
        req = urllib.request.Request(api_url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            release = json.loads(resp.read().decode())

        asset_url = next(
            (
                a["browser_download_url"]
                for a in release.get("assets", [])
                if a.get("name") == "lsp-ml-stores.tar.gz"
            ),
            None,
        )
        if not asset_url:
            print("prove: no lsp-ml-stores.tar.gz in latest release", file=sys.stderr)
            return False

        with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        urllib.request.urlretrieve(asset_url, tmp_path)

        with tempfile.TemporaryDirectory() as extract_tmp:
            extract_path = Path(extract_tmp)
            with tarfile.open(tmp_path, "r:gz") as tar:
                tar.extractall(extract_path)

            extracted_lsp = extract_path / "lsp-ml-stores" / "lsp"
            if extracted_lsp.exists():
                lsp_dest = home / "lsp"
                if lsp_dest.exists():
                    shutil.rmtree(lsp_dest)
                shutil.copytree(str(extracted_lsp), str(lsp_dest))

            extracted_pdat = extract_path / "lsp-ml-stores" / "pdat"
            if extracted_pdat.exists():
                for dat_file in extracted_pdat.glob("*.dat"):
                    shutil.copy2(dat_file, home / dat_file.name)

        tmp_path.unlink(missing_ok=True)
        print("prove: stores installed.", file=sys.stderr)
        return True

    except Exception as exc:
        print(f"prove: store download failed: {exc}", file=sys.stderr)
        return False


def _ensure_stores() -> None:
    """Create ~/.prove/ and download stores on first use if absent."""
    global _stores_ensured
    if _stores_ensured:
        return
    _stores_ensured = True

    if not (prove_home() / "verb_synonyms.dat").exists():
        download_stores()


# ── Verb synonym store ───────────────────────────────────────────


def load_verb_synonyms() -> dict[str, str]:
    """Load synonym → canonical verb map from ``~/.prove/verb_synonyms.dat``.

    Returns a dict like ``{"transform": "transforms", ...}``.
    Downloads the store on first use if ``~/.prove/`` is absent.
    """
    global _verb_map
    if _verb_map is not None:
        return _verb_map

    _ensure_stores()
    dat = _data_path("verb_synonyms.dat")
    if dat.is_file():
        data = read_pdat(dat)
        _verb_map = {variant: values[0] for variant, values in data["variants"]}
    else:
        # Fallback to hardcoded synonyms when PDAT is missing
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
    """Load WordNet-expanded synonym cache from ``~/.prove/synonym_cache.dat``."""
    global _synonym_cache
    if _synonym_cache is not None:
        return _synonym_cache

    _ensure_stores()
    dat = _data_path("synonym_cache.dat")
    if dat.is_file():
        data = read_pdat(dat)
        _synonym_cache = {
            variant: values[0].split("|") if values[0] else []
            for variant, values in data["variants"]
        }
    else:
        _synonym_cache = {}
    return _synonym_cache


def build_verb_synonyms_spacy(out_path: Path | None = None) -> Path:
    """Expand VERB_SYNONYMS with spaCy word vectors and write ``verb_synonyms.dat``.

    Uses ``en_core_web_lg`` (or ``en_core_web_md``) word vectors to find
    additional synonyms for each canonical Prove verb beyond the hardcoded list.
    Falls back gracefully to the hardcoded list if no model with vectors is found.
    Returns the path to the written file.

    Requires spaCy and a model with vectors (``python -m spacy download en_core_web_lg``).
    """
    import numpy as np
    import spacy

    from prove._nl_intent import VERB_SYNONYMS

    # Try models in order of preference (larger = better vectors)
    nlp = None
    for model_name in ("en_core_web_lg", "en_core_web_md"):
        try:
            candidate = spacy.load(model_name)
            if candidate.vocab.vectors.shape[0] > 0:
                nlp = candidate
                break
        except Exception:
            pass

    # Start with the hardcoded synonyms as the baseline
    expanded: dict[str, str] = {syn: verb for verb, syns in VERB_SYNONYMS.items() for syn in syns}

    if nlp is not None:
        vocab = nlp.vocab
        for canonical, seed_syns in VERB_SYNONYMS.items():
            seed_tokens = [vocab[s] for s in seed_syns if vocab[s].has_vector]
            if not seed_tokens:
                continue
            mean_vec = np.mean([t.vector for t in seed_tokens], axis=0).reshape(1, -1)
            keys, _, scores = vocab.vectors.most_similar(mean_vec, n=30)
            for key_id, score in zip(keys[0], scores[0]):
                if score < 0.65:
                    continue
                word = vocab.strings[key_id].lower()
                # Only single-word alphabetic tokens not already mapped
                if word.isalpha() and word not in expanded:
                    expanded[word] = canonical

    variants: list[tuple[str, list[str]]] = [
        (syn, [verb]) for syn, verb in sorted(expanded.items())
    ]
    if out_path is None:
        out_path = Path(str(importlib.resources.files("prove.data").joinpath("verb_synonyms.dat")))
    write_pdat(out_path, "VerbSynonyms", ["String"], variants)
    return out_path


def build_synonym_cache(out_path: Path | None = None) -> Path:
    """Build ``synonym_cache.dat`` with WordNet-expanded synonyms.

    Requires NLTK with WordNet data.  Returns the path to the written file.
    Raises if WordNet is not available.
    """
    from nltk.corpus import wordnet

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

    if out_path is None:
        out_path = Path(str(importlib.resources.files("prove.data").joinpath("synonym_cache.dat")))
    write_pdat(out_path, "SynonymCache", ["String"], variants)
    return out_path


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
_lsp_from_blocks: dict[tuple[str, str], list[str]] | None = None


def load_lsp_bigrams() -> dict[str, list[tuple[str, int]]]:
    """Load global bigram model from ``~/.prove/lsp/bigrams/current.prv``.

    Returns ``{prev1: [(next_token, count), ...]}``.
    """
    global _lsp_bigrams
    if _lsp_bigrams is not None:
        return _lsp_bigrams

    _ensure_stores()
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
    """Load global completion model from ``~/.prove/lsp/completions/current.prv``.

    Returns ``{(prev2, prev1): [top_tokens...]}``.
    """
    global _lsp_completions
    if _lsp_completions is not None:
        return _lsp_completions

    _ensure_stores()
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


def load_lsp_from_blocks() -> dict[tuple[str, str], list[str]]:
    """Load from-block n-gram model from ``~/.prove/lsp/from_blocks/current.prv``.

    Returns ``{(prev2, prev1): [top_tokens...]}``.
    """
    global _lsp_from_blocks
    if _lsp_from_blocks is not None:
        return _lsp_from_blocks

    _ensure_stores()
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
    global _lsp_bigrams, _lsp_completions, _lsp_from_blocks
    _verb_map = None
    _verb_groups = None
    _synonym_cache = None
    _similarity_matrix = None
    _lsp_bigrams = None
    _lsp_completions = None
    _lsp_from_blocks = None
