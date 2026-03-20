"""Build NLP data stores from scratch (requires: pip install 'prove[nlp]').

This script is embedded as a comptime string in setup_nlp.prv and executed via
PyRun_SimpleString.
"""

from __future__ import annotations

if __name__ == "__main__":
    import importlib.util
    from pathlib import Path

    print("Building NLP data stores from scratch...")
    try:
        import nltk  # noqa: F401
        import spacy  # noqa: F401
    except ImportError:
        print("  NLP deps not installed. Run: pip install 'prove[nlp]'")
        raise SystemExit(1)

    import prove as _prove_pkg

    script = (
        Path(_prove_pkg.__file__).resolve().parent.parent.parent
        / "scripts"
        / "build_stores.py"
    )
    if script.exists():
        spec = importlib.util.spec_from_file_location("build_stores", script)
        if spec and spec.loader:
            build = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(build)
            build.build_verb_synonyms()
            build.build_synonym_cache()
            build.build_similarity_matrix()
            build.build_semantic_features()
            build.build_stdlib_index()
            print("  NLP stores built.")
    else:
        print("  build_stores.py not found.")
    raise SystemExit(0)
