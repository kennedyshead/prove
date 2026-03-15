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


# ── Reset (for testing) ──────────────────────────────────────────


def _reset() -> None:
    """Clear all cached store data.  For testing only."""
    global _verb_map, _verb_groups
    _verb_map = None
    _verb_groups = None
