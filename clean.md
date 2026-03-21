The codebase is quite clean — ruff finds zero unused imports/variables, and vulture at 80% confidence finds nothing.
   All dead code is at the function/method level.

  Phase 1: Confirmed Dead Functions (18 removals, safe)

  ┌───────────────────────┬──────────────────────────────────┬────────────────────────────────────────────────┐
  │         File          │              Symbol              │                    Why dead                    │
  ├───────────────────────┼──────────────────────────────────┼────────────────────────────────────────────────┤
  │ c_emitter.py:185      │ _module_reads_console()          │ Leftover from early console I/O detection      │
  ├───────────────────────┼──────────────────────────────────┼────────────────────────────────────────────────┤
  │ formatter.py:586      │ _split_item_names()              │ Superseded by inline logic                     │
  ├───────────────────────┼──────────────────────────────────┼────────────────────────────────────────────────┤
  │ parser.py:1081        │ _type_expr_to_variant()          │ Variant parsing uses _parse_variant() directly │
  ├───────────────────────┼──────────────────────────────────┼────────────────────────────────────────────────┤
  │ types.py:512          │ get_ownership_kind()             │ Ownership tracking never implemented           │
  ├───────────────────────┼──────────────────────────────────┼────────────────────────────────────────────────┤
  │ stdlib_loader.py:942  │ stdlib_pure_prv_path()           │ Never called                                   │
  ├───────────────────────┼──────────────────────────────────┼────────────────────────────────────────────────┤
  │ stdlib_loader.py:985  │ available_modules()              │ Never called                                   │
  ├───────────────────────┼──────────────────────────────────┼────────────────────────────────────────────────┤
  │ stdlib_loader.py:1203 │ _reset_import_index()            │ Test helper never wired up                     │
  ├───────────────────────┼──────────────────────────────────┼────────────────────────────────────────────────┤
  │ nlp.py:173            │ synonyms()                       │ WordNet lookup unused                          │
  ├───────────────────────┼──────────────────────────────────┼────────────────────────────────────────────────┤
  │ nlp_store.py:637      │ load_lsp_docstrings()            │ Planned for LSP, never wired                   │
  ├───────────────────────┼──────────────────────────────────┼────────────────────────────────────────────────┤
  │ export.py:294         │ _pygments_words()                │ Each section inlines its formatting            │
  ├───────────────────────┼──────────────────────────────────┼────────────────────────────────────────────────┤
  │ _python_bundle.py:193 │ _find_stdlib_modules()           │ Planned, never used                            │
  ├───────────────────────┼──────────────────────────────────┼────────────────────────────────────────────────┤
  │ prover.py:119         │ ProofVerifier._warning()         │ Never called                                   │
  ├───────────────────────┼──────────────────────────────────┼────────────────────────────────────────────────┤
  │ optimizer.py:93       │ RuntimeDeps.add_lib()            │ Only add_module() is used                      │
  ├───────────────────────┼──────────────────────────────────┼────────────────────────────────────────────────┤
  │ optimizer.py:122      │ EscapeInfo.mark_noescape_call()  │ Never called                                   │
  ├───────────────────────┼──────────────────────────────────┼────────────────────────────────────────────────┤
  │ optimizer.py:130      │ EscapeInfo.is_noescape_call()    │ Never called                                   │
  ├───────────────────────┼──────────────────────────────────┼────────────────────────────────────────────────┤
  │ optimizer.py:134      │ EscapeInfo.get_escaping_vars()   │ Never called                                   │
  ├───────────────────────┼──────────────────────────────────┼────────────────────────────────────────────────┤
  │ optimizer.py:178      │ Optimizer.is_elision_candidate() │ Never called                                   │
  ├───────────────────────┼──────────────────────────────────┼────────────────────────────────────────────────┤
  │ symbols.py:75         │ Scope.lookup_local()             │ Never called                                   │
  └───────────────────────┴──────────────────────────────────┴────────────────────────────────────────────────┘

  Phase 2: Test-Only Code (evaluate)

  - Optimizer.get_elision_candidates() — called only from test_optimizer.py
  - SourceFile.span_text() — called only from test_cli.py

  Keep if on roadmap, remove with their tests otherwise.

  Phase 3: Dead Config/Fields (evaluate)

  - DiagnosticLabel.style — field never read
  - StyleConfig / line_length — parsed from TOML but never consumed by formatter
  - mutator.py self._rng — assigned but never used
  - GeneratedStmt.stdlib_call — field never accessed

  Verification

  After all changes:
  cd prove-py && python -m pytest tests/ -v
  ruff check src/ tests/
  mypy src/
  python scripts/test_e2e.py

  Want me to proceed with Phase 1 (the safe removals)?
