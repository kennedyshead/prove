The codebase is quite clean — ruff finds zero unused imports/variables, and vulture at 80% confidence finds nothing.
   All dead code is at the function/method level.

  Phase 1: Confirmed Dead Functions — DONE (17 removed)

  - c_emitter.py: _module_reads_console()
  - formatter.py: _split_item_names()
  - parser.py: _type_expr_to_variant()
  - types.py: get_ownership_kind()
  - stdlib_loader.py: stdlib_pure_prv_path(), available_modules(), _reset_import_index()
  - nlp.py: synonyms() (+ tests in test_nlp.py)
  - nlp_store.py: load_lsp_docstrings() (+ _lsp_docstrings global)
  - export.py: _pygments_words()
  - _python_bundle.py: _find_stdlib_modules() (already removed before this pass)
  - prover.py: ProofVerifier._warning()
  - optimizer.py: RuntimeDeps.add_lib(), EscapeInfo.mark_noescape_call(),
    EscapeInfo.is_noescape_call(), EscapeInfo.get_escaping_vars(),
    EscapeInfo._noescape_calls field, Optimizer.is_elision_candidate()
  - symbols.py: Scope.lookup_local()

  Phase 2: Test-Only Code — DONE (2 removed + their tests)

  - Optimizer.get_elision_candidates() + TestCopyElision class in test_optimizer.py
  - SourceFile.span_text() + test_span_text_single_line in test_cli.py

  Phase 3: Dead Config/Fields — DONE (4 removed)

  - DiagnosticLabel.style field (errors.py)
  - StyleConfig class + ProveConfig.style field + TOML parsing (config.py)
  - Mutator._rng + seed param + import random (mutator.py, _check_runner.py, test_ai_resistance.py)
  - GeneratedStmt.stdlib_call field + usage sites (_body_gen.py)

  All verified: 1678 unit tests pass, 462 e2e tests pass, ruff clean.
