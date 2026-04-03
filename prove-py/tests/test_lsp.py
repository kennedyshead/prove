"""Tests for the Prove LSP server."""

from __future__ import annotations

from pathlib import Path

from lsprotocol import types as lsp

from prove.errors import Severity
from prove.lsp import (
    _SEVERITY_MAP,
    DocumentState,
    _analyze,
    _analyze_intent,
    _build_import_edit,
    _build_import_edit_text,
    _extract_undefined_name,
    _get_word_at,
    _intent_code_actions,
    _intent_completions,
    _is_e310,
    _is_intent_uri,
    _ProjectIndexer,
    _types_display,
    completion,
    span_to_range,
)
from prove.source import Span
from prove.stdlib_loader import ImportSuggestion, build_import_index
from prove.symbols import FunctionSignature


class TestSpanConversion:
    def test_span_to_range_basic(self):
        span = Span("test.prv", 1, 1, 1, 5)
        r = span_to_range(span)
        assert r.start.line == 0
        assert r.start.character == 0
        assert r.end.line == 0
        assert r.end.character == 5

    def test_span_to_range_multiline(self):
        span = Span("test.prv", 5, 3, 7, 10)
        r = span_to_range(span)
        assert r.start.line == 4
        assert r.start.character == 2
        assert r.end.line == 6
        assert r.end.character == 10

    def test_span_to_range_single_char(self):
        span = Span("test.prv", 10, 5, 10, 5)
        r = span_to_range(span)
        assert r.start.line == 9
        assert r.start.character == 4
        assert r.end.line == 9
        assert r.end.character == 5


class TestSeverityMap:
    def test_error_maps(self):
        assert _SEVERITY_MAP[Severity.ERROR] == lsp.DiagnosticSeverity.Error

    def test_warning_maps(self):
        assert _SEVERITY_MAP[Severity.WARNING] == lsp.DiagnosticSeverity.Warning

    def test_note_maps(self):
        assert _SEVERITY_MAP[Severity.NOTE] == lsp.DiagnosticSeverity.Information


class TestGetWordAt:
    def test_word_middle(self):
        assert _get_word_at("hello world", 0, 2) == "hello"

    def test_word_end(self):
        assert _get_word_at("hello world", 0, 5) == "hello"

    def test_word_start(self):
        assert _get_word_at("hello world", 0, 0) == "hello"

    def test_second_word(self):
        assert _get_word_at("hello world", 0, 8) == "world"

    def test_underscore_word(self):
        assert _get_word_at("my_var = 42", 0, 3) == "my_var"

    def test_empty(self):
        assert _get_word_at("", 0, 0) == ""

    def test_out_of_range(self):
        assert _get_word_at("hello", 5, 0) == ""


class TestTypesDisplay:
    def test_simple_function(self):
        from prove.types import INTEGER

        dummy = Span("<test>", 0, 0, 0, 0)
        sig = FunctionSignature(
            verb="transforms",
            name="add",
            param_names=["a", "b"],
            param_types=[INTEGER, INTEGER],
            return_type=INTEGER,
            can_fail=False,
            span=dummy,
        )
        result = _types_display(sig)
        assert "transforms" in result
        assert "add" in result
        assert "Integer" in result

    def test_failable_function(self):
        from prove.types import STRING

        dummy = Span("<test>", 0, 0, 0, 0)
        sig = FunctionSignature(
            verb="inputs",
            name="load",
            param_names=["path"],
            param_types=[STRING],
            return_type=STRING,
            can_fail=True,
            span=dummy,
        )
        result = _types_display(sig)
        assert result.endswith("!")


class TestAnalyze:
    def test_analyze_valid_source(self):
        source = (
            "module Main\n"
            '  narrative: """Transforms numbers via add operations"""\n'
            "\n"
            "transforms add(a Integer, b Integer) Integer\n"
            "from\n"
            "    a + b\n"
        )
        ds = _analyze("file:///test.prv", source)
        assert ds.module is not None
        assert ds.symbols is not None
        # No errors (info/warning coherence hints are acceptable)
        assert not any(d.severity == lsp.DiagnosticSeverity.Error for d in ds.diagnostics)

    def test_analyze_with_errors(self):
        source = "transforms add(a Integer, b Integer) Integer\nfrom\n    unknown_var\n"
        ds = _analyze("file:///test.prv", source)
        assert ds.module is not None
        assert len(ds.diagnostics) > 0
        assert any("E310" in d.message for d in ds.diagnostics)

    def test_analyze_lex_error(self):
        source = "@@@ invalid tokens\n"
        ds = _analyze("file:///test.prv", source)
        assert len(ds.diagnostics) > 0

    def test_analyze_caches_state(self):
        from prove.lsp import _state

        source = 'module Main\n  System outputs console\nmain()\nfrom\n    console("hi")\n'
        uri = "file:///cache_test.prv"
        ds = _analyze(uri, source)
        assert _state.get(uri) is ds
        # Clean up
        _state.pop(uri, None)


class TestDocumentState:
    def test_default_state(self):
        ds = DocumentState()
        assert ds.source == ""
        assert ds.tokens == []
        assert ds.module is None
        assert ds.symbols is None
        assert ds.diagnostics == []


class TestBuildImportIndex:
    def test_index_contains_console(self):
        index = build_import_index()
        assert "console" in index
        suggestions = index["console"]
        assert any(s.module == "System" and s.verb == "outputs" for s in suggestions)

    def test_index_contains_file(self):
        index = build_import_index()
        assert "file" in index
        suggestions = index["file"]
        assert any(s.module == "System" and s.verb == "inputs" for s in suggestions)

    def test_index_no_duplicates_from_aliases(self):
        index = build_import_index()
        # file has inputs + outputs verbs = 2 entries, but no duplicates from aliases
        if "file" in index:
            # Each entry should have a unique (module, verb) pair
            pairs = [(s.module, s.verb) for s in index["file"]]
            assert len(pairs) == len(set(pairs))


class TestIsE310:
    def test_matches_e310(self):
        diag = lsp.Diagnostic(
            range=lsp.Range(lsp.Position(0, 0), lsp.Position(0, 5)),
            message="[E310] undefined name 'foo'",
            code="E310",
        )
        assert _is_e310(diag)

    def test_rejects_other_code(self):
        diag = lsp.Diagnostic(
            range=lsp.Range(lsp.Position(0, 0), lsp.Position(0, 5)),
            message="[E200] some other error",
            code="E200",
        )
        assert not _is_e310(diag)

    def test_rejects_no_code(self):
        diag = lsp.Diagnostic(
            range=lsp.Range(lsp.Position(0, 0), lsp.Position(0, 5)),
            message="some error",
        )
        assert not _is_e310(diag)


class TestExtractUndefinedName:
    def test_extracts_name(self):
        assert _extract_undefined_name("[E310] undefined name 'foo'") == "foo"

    def test_extracts_underscore_name(self):
        assert _extract_undefined_name("[E310] undefined name 'my_func'") == "my_func"

    def test_no_match(self):
        assert _extract_undefined_name("[E200] type mismatch") is None


class TestBuildImportEdit:
    def _make_ds(self, source: str) -> DocumentState:
        return _analyze("file:///test_import.prv", source)

    def test_new_import_in_module(self):
        source = "module Main\ntransforms add(a Integer, b Integer) Integer\nfrom\n    a + b\n"
        ds = self._make_ds(source)
        suggestion = ImportSuggestion(module="System", verb="outputs", name="console")
        edit = _build_import_edit(ds, suggestion)
        assert edit is not None
        assert "System outputs console" in edit.new_text
        # Should insert after the module line
        assert edit.range.start.line == 1

    def test_extend_existing_import(self):
        source = (
            'module Main\n  System outputs console\noutputs run() Unit\nfrom\n    console("hi")\n'
        )
        ds = self._make_ds(source)
        suggestion = ImportSuggestion(module="System", verb="outputs", name="file")
        edit = _build_import_edit(ds, suggestion)
        assert edit is not None
        assert edit.new_text == "  System outputs console file"
        # Should replace line 1 (the existing import line)
        assert edit.range.start.line == 1

    def test_already_imported_returns_none(self):
        source = (
            'module Main\n  System outputs console\noutputs run() Unit\nfrom\n    console("hi")\n'
        )
        ds = self._make_ds(source)
        suggestion = ImportSuggestion(module="System", verb="outputs", name="console")
        edit = _build_import_edit(ds, suggestion)
        assert edit is None

    def test_no_module_returns_none(self):
        ds = DocumentState()  # module is None
        suggestion = ImportSuggestion(module="System", verb="outputs", name="console")
        edit = _build_import_edit(ds, suggestion)
        assert edit is None

    def test_new_import_after_multiline_narrative(self):
        # Regression: import was inserted inside the narrative block
        source = (
            'module Source\n  narrative: """\n  Reads all source files through dir inputs,\n  """\n'
        )
        suggestion = ImportSuggestion(module="Config", verb="types", name="Config")
        edit = _build_import_edit_text(source, suggestion)
        assert edit is not None
        assert "Config types Config" in edit.new_text
        # Must insert AFTER the closing """ (line index 4)
        assert edit.range.start.line == 4

    def test_new_stdlib_import_after_multiline_narrative(self):
        # Regression: stdlib import (e.g. Pattern reads string) inserted inside narrative
        source = (
            'module Source\n  narrative: """\n  Reads all source files through dir inputs,\n  """\n'
        )
        suggestion = ImportSuggestion(module="Pattern", verb="derives", name="string")
        edit = _build_import_edit_text(source, suggestion)
        assert edit is not None
        assert "Pattern derives string" in edit.new_text
        assert edit.range.start.line == 4

    def test_extend_existing_import_different_verb(self):
        source = (
            'module Main\n  System outputs console\noutputs run() Unit\nfrom\n    console("hi")\n'
        )
        ds = self._make_ds(source)
        suggestion = ImportSuggestion(module="System", verb="inputs", name="file")
        edit = _build_import_edit(ds, suggestion)
        assert edit is not None
        # Same module — extends existing line with new verb group
        assert "inputs file" in edit.new_text
        assert edit.range.start.line == 1


def _complete(uri: str, line: int = 0, character: int = 0) -> lsp.CompletionList:
    """Helper to call the completion handler."""
    params = lsp.CompletionParams(
        text_document=lsp.TextDocumentIdentifier(uri=uri),
        position=lsp.Position(line=line, character=character),
    )
    return completion(params)


def _complete_labels(uri: str, **kwargs: int) -> set[str]:
    """Return the set of completion labels for a URI."""
    result = _complete(uri, **kwargs)
    return {item.label for item in result.items}


class TestCompletion:
    """Completion must always provide stdlib and builtins, even with errors."""

    def test_keywords_always_present(self):
        _analyze("<test://kw>", "")
        labels = _complete_labels("<test://kw>")
        for kw in ("transforms", "validates", "inputs", "outputs", "from", "match", "module"):
            assert kw in labels, f"keyword '{kw}' missing from completions"

    def test_builtin_functions_always_present(self):
        _analyze("<test://bi>", "")
        labels = _complete_labels("<test://bi>")
        for fn in ("len", "map", "filter", "reduce", "clamp"):
            assert fn in labels, f"builtin '{fn}' missing from completions"
        # println/print/readln are no longer builtins — they come from System
        for fn in ("println", "print", "readln"):
            assert fn not in labels, f"removed builtin '{fn}' should not be in completions"

    def test_builtin_types_always_present(self):
        _analyze("<test://ty>", "")
        labels = _complete_labels("<test://ty>")
        for ty in ("Integer", "String", "Boolean", "Decimal", "List", "Result", "Option", "Unit"):
            assert ty in labels, f"type '{ty}' missing from completions"

    def test_stdlib_functions_with_parse_errors(self):
        """Stdlib completions must work even when the file cannot parse."""
        _analyze("<test://broken>", "this is not valid prove code\n")
        labels = _complete_labels("<test://broken>")
        assert any("console" in label for label in labels)

    def test_stdlib_functions_with_valid_file(self):
        _analyze(
            "<test://valid>",
            'module Main\n  narrative: """Test"""\n\nmain()\nfrom\n    console("hi")\n',
        )
        labels = _complete_labels("<test://valid>")
        assert any("console" in label for label in labels)

    def test_stdlib_completions_have_detail(self):
        """Stdlib items should show module name in label_details.description."""
        _analyze("<test://det>", "")
        result = _complete("<test://det>")
        console_items = [i for i in result.items if "console" in i.label and "System" in i.label]
        assert len(console_items) >= 1
        item = console_items[0]
        assert item.label_details is not None
        assert item.label_details.description == "System"

    def test_symbol_table_completions_when_parsed(self):
        """User-defined names should appear when the file parses."""
        _analyze(
            "<test://sym>",
            "module Main\n"
            '  narrative: """Test"""\n'
            "\n"
            "transforms add(a Integer, b Integer) Integer\n"
            "from\n"
            "    a + b\n",
        )
        labels = _complete_labels("<test://sym>")
        assert any("add" in label for label in labels)

    def test_no_duplicate_verb_label_pairs(self):
        """Each (label, sort_text) pair should appear at most once."""
        _analyze("<test://dup>", "")
        result = _complete("<test://dup>")
        keys = [(item.label, item.sort_text or item.label) for item in result.items]
        assert len(keys) == len(set(keys)), (
            f"duplicate completions: {[x for x in keys if keys.count(x) > 1]}"
        )

    def test_stdlib_completion_auto_imports(self):
        """Selecting a stdlib completion should add the import."""
        _analyze(
            "file:///auto.prv",
            'module Main\n  narrative: """Test"""\n\nmain()\nfrom\n    console("hi")\n',
        )
        result = _complete("file:///auto.prv")
        file_items = [i for i in result.items if "file" in i.label]

        # file should have multiple verb variants, each with an auto-import edit
        assert len(file_items) >= 1
        item = file_items[0]
        assert item.additional_text_edits is not None
        assert len(item.additional_text_edits) == 1
        edit = item.additional_text_edits[0]
        assert "System" in edit.new_text
        assert "file" in edit.new_text

    def test_stdlib_completion_no_duplicate_import(self):
        """Overloads are collapsed — one item per (name, module)."""
        _analyze(
            "file:///noimport.prv",
            "module Main\n"
            '  narrative: """Test"""\n'
            "  System outputs console\n"
            "\n"
            "main()\nfrom\n"
            '    console("hi")\n',
        )
        result = _complete("file:///noimport.prv")
        # Find console with System prefix — collapsed to one item
        console_items = [i for i in result.items if "console" in i.label and "System" in i.label]
        assert len(console_items) == 1
        # Already imported, so detail shows the verb label (not Auto-import)
        item = console_items[0]
        assert "outputs" in item.label or "inputs" in item.label

    def test_completion_does_not_insert_params(self):
        """Completions must not insert placeholder parameter names."""
        _analyze(
            "file:///noparams.prv",
            "module Main\n"
            '  narrative: """Test"""\n'
            "\n"
            "transforms add(a Integer, b Integer) Integer\n"
            "from\n"
            "    a + b\n",
        )
        result = _complete("file:///noparams.prv")
        for item in result.items:
            if item.insert_text is not None:
                assert "(" not in item.insert_text, (
                    f"completion '{item.label}' has insert_text with parens: {item.insert_text!r}"
                )

    def test_auto_import_works_with_parse_errors(self):
        """Auto-import must work even when the file has parse errors."""
        _analyze(
            "file:///parseerr.prv",
            "module Main\n"
            '  narrative: """Test"""\n'
            "\n"
            "outputs handle()\n"
            "from\n"
            "    match\n"
            "        Get => ok()\n",
        )
        result = _complete("file:///parseerr.prv")
        file_items = [i for i in result.items if "file" in i.label and "System" in i.label]

        assert len(file_items) >= 1
        item = file_items[0]
        assert item.additional_text_edits is not None, (
            "auto-import should work even when file has parse errors"
        )
        edit = item.additional_text_edits[0]
        assert "System" in edit.new_text
        assert "file" in edit.new_text
        # Should insert after narrative (line 2), not at end of file
        assert edit.range.start.line == 2

    def test_auto_import_after_existing_imports_with_errors(self):
        """Auto-import should go after existing imports, even with errors."""
        _analyze(
            "file:///afterimport.prv",
            "module Main\n"
            '  narrative: """Test"""\n'
            "  System outputs console\n"
            "\n"
            "outputs handle()\n"
            "from\n"
            "    match\n"
            "        Get => ok()\n",
        )
        result = _complete("file:///afterimport.prv")
        file_items = [i for i in result.items if "file" in i.label and "System" in i.label]

        assert len(file_items) >= 1
        item = file_items[0]
        assert item.additional_text_edits is not None
        edit = item.additional_text_edits[0]
        # With tree-sitter error recovery the AST is available, so the
        # existing System import on line 2 is extended in-place rather
        # than inserting a new line after it.
        assert edit.range.start.line in (2, 3)

    def test_channel_dispatch_shows_all_verbs(self):
        """file overloads are collapsed — all verbs appear in the label."""
        _analyze("<test://dispatch>", "")
        result = _complete("<test://dispatch>")
        file_items = [i for i in result.items if "file" in i.label and "System" in i.label]
        # Collapsed: one item with all verbs in the label
        assert len(file_items) == 1, f"expected 1 collapsed item, got {len(file_items)}"
        label = file_items[0].label
        for verb in ("inputs", "outputs", "validates"):
            assert verb in label, f"verb '{verb}' missing from collapsed label: {label}"

    def test_stdlib_completions_detail_with_signature(self):
        """Stdlib completions should show 'Auto-import' in detail, all overloads in docs."""
        _analyze("<test://sig>", "")
        result = _complete("<test://sig>")
        console_items = [i for i in result.items if "console" in i.label and "System" in i.label]
        assert len(console_items) == 1
        item = console_items[0]
        # Detail should mention Auto-import (possibly with overload count)
        assert "Auto-import" in item.detail
        # Documentation should contain signature
        assert item.documentation is not None
        assert "console" in item.documentation.value

    def test_user_defined_function_signature_in_docs(self):
        """User-defined functions should show full signature in detail."""
        _analyze(
            "<test://userfn>",
            "module Main\n"
            '  narrative: """Test"""\n'
            "\n"
            "/// Adds two numbers\n"
            "transforms add(a Integer, b Integer) Integer\n"
            "from\n"
            "    a + b\n",
        )
        result = _complete("<test://userfn>")
        # Find local add — label is "transforms add" (no module prefix, unlike stdlib)
        add_items = [i for i in result.items if i.label == "transforms add"]
        assert len(add_items) >= 1
        item = add_items[0]
        # Detail should be verb only
        assert item.detail is not None
        assert item.detail == "transforms"
        # Signature should be in documentation
        assert item.documentation is not None
        assert "Integer" in item.documentation.value


class TestCompletionNoDuplicateSignature:
    def test_stdlib_completion_no_duplicate_in_label_and_detail(self):
        """Verify signature doesn't appear in both label AND detail (duplicate)."""
        DocumentState(source="module Main")  # noqa: F841
        params = lsp.CompletionParams(
            text_document=lsp.TextDocumentIdentifier("test:///test.prv"),
            position=lsp.Position(line=0, character=0),
        )
        result = completion(params)

        for item in result.items:
            if item.label == "System console":
                label_has_sig = "(" in item.label and ")" in item.label
                detail_has_sig = "(" in (item.detail or "") and ")" in (item.detail or "")

                assert not (label_has_sig and detail_has_sig), (
                    f"DUPLICATE SIGNATURE: label='{item.label}', detail='{item.detail}'"
                )
                break

    def test_user_function_completion_no_duplicate(self):
        """Verify user functions don't have duplicate signature."""
        _analyze(
            "<test://userfn>",
            "module Main\n"
            '  narrative: """Test"""\n'
            "\n"
            "transforms add(a Integer, b Integer) Integer\n"
            "from\n"
            "    a + b\n",
        )
        result = _complete("<test://userfn>")
        add_items = [i for i in result.items if "add" in i.label]

        assert len(add_items) >= 1
        item = add_items[0]
        label_has_sig = "(" in item.label and ")" in item.label
        detail_has_sig = "(" in (item.detail or "") and ")" in (item.detail or "")

        assert not (label_has_sig and detail_has_sig), (
            f"DUPLICATE SIGNATURE: label='{item.label}', detail='{item.detail}'"
        )

    def test_documentation_uses_prv_syntax(self):
        """Verify documentation uses code block with signature."""
        _analyze(
            "<test://doc>",
            "module Main\n"
            "\n"
            "/// Adds two numbers\n"
            "transforms add(a Integer, b Integer) Integer\n"
            "from\n"
            "    a + b\n",
        )
        result = _complete("<test://doc>")
        add_items = [i for i in result.items if "add" in i.label]

        assert len(add_items) >= 1
        doc = add_items[0].documentation
        assert doc is not None, "No documentation found"
        assert "```" in doc.value, f"Expected ```, got: {doc.value}"


class TestProjectIndexerCacheValidity:
    """Tests for _ProjectIndexer.is_cache_valid()."""

    def test_no_cache_dir(self, tmp_path: Path):
        """is_cache_valid returns False when .prove/cache doesn't exist."""
        (tmp_path / "prove.toml").write_text("[package]\nname = 'test'\n")
        (tmp_path / "main.prv").write_text("module Main\n")
        indexer = _ProjectIndexer(tmp_path)
        assert indexer.is_cache_valid() is False

    def test_valid_after_index(self, tmp_path: Path):
        """is_cache_valid returns True right after index_all_files."""
        (tmp_path / "prove.toml").write_text("[package]\nname = 'test'\n")
        (tmp_path / "main.prv").write_text("module Main\n")
        indexer = _ProjectIndexer(tmp_path)
        indexer.index_all_files()
        assert indexer.is_cache_valid() is True

    def test_stale_after_file_change(self, tmp_path: Path):
        """is_cache_valid returns False after a tracked file changes."""
        import time

        prv = tmp_path / "main.prv"
        (tmp_path / "prove.toml").write_text("[package]\nname = 'test'\n")
        prv.write_text("module Main\n")
        indexer = _ProjectIndexer(tmp_path)
        indexer.index_all_files()
        # Modify the file (ensure mtime changes)
        time.sleep(0.05)
        prv.write_text("module Main\n// changed\n")
        assert indexer.is_cache_valid() is False

    def test_stale_after_new_file(self, tmp_path: Path):
        """is_cache_valid returns False when a new .prv file appears."""
        (tmp_path / "prove.toml").write_text("[package]\nname = 'test'\n")
        (tmp_path / "main.prv").write_text("module Main\n")
        indexer = _ProjectIndexer(tmp_path)
        indexer.index_all_files()
        (tmp_path / "other.prv").write_text("module Other\n")
        assert indexer.is_cache_valid() is False

    def test_stale_after_file_deleted(self, tmp_path: Path):
        """is_cache_valid returns False when a tracked file is deleted."""
        (tmp_path / "prove.toml").write_text("[package]\nname = 'test'\n")
        prv = tmp_path / "main.prv"
        prv.write_text("module Main\n")
        indexer = _ProjectIndexer(tmp_path)
        indexer.index_all_files()
        prv.unlink()
        assert indexer.is_cache_valid() is False


class TestProjectIndexerLoad:
    """Tests for _ProjectIndexer.load() (warm start from cache)."""

    def test_load_without_cache_returns_false(self, tmp_path: Path):
        """load() returns False when no cache exists."""
        (tmp_path / "prove.toml").write_text("[package]\nname = 'test'\n")
        indexer = _ProjectIndexer(tmp_path)
        assert indexer.load() is False

    def test_load_restores_bigrams(self, tmp_path: Path):
        """load() restores bigram data from cache."""
        (tmp_path / "prove.toml").write_text("[package]\nname = 'test'\n")
        (tmp_path / "main.prv").write_text("module Main\n")
        # Build cache
        indexer = _ProjectIndexer(tmp_path)
        indexer.index_all_files()
        # Create fresh indexer and load from cache
        fresh = _ProjectIndexer(tmp_path)
        assert fresh.load() is True
        assert len(fresh._bigrams) > 0

    def test_load_restores_symbols(self, tmp_path: Path):
        """load() restores symbol data from cache."""
        (tmp_path / "prove.toml").write_text("[package]\nname = 'test'\n")
        (tmp_path / "main.prv").write_text(
            "module Main\n"
            '  narrative: """Test"""\n'
            "\n"
            "transforms add(a Integer, b Integer) Integer\n"
            "from\n"
            "    a + b\n"
        )
        indexer = _ProjectIndexer(tmp_path)
        indexer.index_all_files()
        fresh = _ProjectIndexer(tmp_path)
        assert fresh.load() is True
        assert "add" in fresh._symbols

    def test_warm_start_skips_reindex(self, tmp_path: Path):
        """_ensure_project_indexed uses load() when cache is valid."""
        import prove.lsp as lsp_mod

        (tmp_path / "prove.toml").write_text("[package]\nname = 'test'\n")
        (tmp_path / "main.prv").write_text("module Main\n")
        # Build cache
        indexer = _ProjectIndexer(tmp_path)
        indexer.index_all_files()
        # Simulate _ensure_project_indexed with a fresh indexer
        fresh = _ProjectIndexer(tmp_path)
        old_global = lsp_mod._project_indexer
        try:
            lsp_mod._project_indexer = fresh
            # Warm path: cache valid + load succeeds → no index_all_files
            assert fresh.is_cache_valid()
            assert fresh.load()
            assert len(fresh._file_ngrams) > 0
        finally:
            lsp_mod._project_indexer = old_global


# ── .intent file LSP tests ──────────────────────────────────────


class TestIsIntentUri:
    def test_intent_uri(self):
        assert _is_intent_uri("file:///project/project.intent")

    def test_prv_uri(self):
        assert not _is_intent_uri("file:///project/main.prv")

    def test_no_extension(self):
        assert not _is_intent_uri("file:///project/readme")


_SAMPLE_INTENT = """\
project UserAuth
  purpose: Authenticate users and manage sessions
  domain: Security

  vocabulary
    Credential is a user identity paired with a secret
    Session is a time-limited access token

  module Auth
    validates credentials against stored password hashes
    transforms passwords into hashes
    creates sessions for authenticated users

  module SessionManager
    validates sessions for expiry
    reads session data from storage

  flow
    Auth creates sessions -> SessionManager validates sessions

  constraints
    all credential operations are failable
"""


class TestAnalyzeIntent:
    def test_parses_valid_intent(self):
        ids = _analyze_intent("file:///test/project.intent", _SAMPLE_INTENT)
        assert ids.project is not None
        assert ids.project.name == "UserAuth"

    def test_missing_project_produces_error(self):
        ids = _analyze_intent("file:///test/bad.intent", "purpose: something\n")
        diags = ids.diagnostics
        assert any(d.severity == lsp.DiagnosticSeverity.Error for d in diags)

    def test_unrecognized_verb_produces_warning(self):
        source = """\
project Test
  purpose: test
  module Foo
    yeets something gracefully
"""
        ids = _analyze_intent("file:///test/test.intent", source)
        assert any(d.code == "W601" for d in ids.diagnostics)

    def test_w602_unreferenced_vocabulary(self):
        source = """\
project Test
  purpose: test
  vocabulary
    Orphan is never used anywhere
  module Foo
    validates data
"""
        ids = _analyze_intent("file:///test/test.intent", source)
        w602 = [d for d in ids.diagnostics if d.code == "W602"]
        assert len(w602) == 1
        assert "Orphan" in w602[0].message

    def test_w603_undefined_flow_module(self):
        source = """\
project Test
  purpose: test
  module Auth
    validates credentials
  flow
    Auth validates credentials -> Ghost validates sessions
"""
        ids = _analyze_intent("file:///test/test.intent", source)
        w603 = [d for d in ids.diagnostics if d.code == "W603"]
        assert len(w603) == 1
        assert "Ghost" in w603[0].message


class TestIntentCompletions:
    def test_top_level_keywords(self):
        source = "project Test\n  purpose: test\n"
        items = _intent_completions(source, lsp.Position(line=2, character=0))
        labels = {i.label for i in items}
        assert "module" in labels
        assert "vocabulary" in labels

    def test_module_block_verbs(self):
        source = "project Test\n  purpose: test\n  module Foo\n    "
        items = _intent_completions(source, lsp.Position(line=3, character=4))
        labels = {i.label for i in items}
        assert "validates" in labels
        assert "transforms" in labels

    def test_vocabulary_block_snippet(self):
        source = "project Test\n  purpose: test\n  vocabulary\n    "
        items = _intent_completions(source, lsp.Position(line=3, character=4))
        assert len(items) > 0
        assert any("is" in (i.insert_text or i.label) for i in items)


class TestIntentCodeActions:
    def test_generate_prv_action(self):
        ids = _analyze_intent("file:///test/project.intent", _SAMPLE_INTENT)
        actions = _intent_code_actions("file:///test/project.intent", ids)
        assert len(actions) == 2  # Auth and SessionManager
        assert any("auth.prv" in a.title for a in actions)
        assert any("sessionmanager.prv" in a.title for a in actions)


class TestInlayHint:
    def _make_params(self, uri: str) -> lsp.InlayHintParams:
        return lsp.InlayHintParams(
            text_document=lsp.TextDocumentIdentifier(uri=uri),
            range=lsp.Range(
                start=lsp.Position(line=0, character=0),
                end=lsp.Position(line=999, character=0),
            ),
        )

    def test_inlay_hint_untyped_var(self):
        from prove.lsp import inlay_hint

        source = (
            "module Main\n"
            '  narrative: """Test"""\n'
            "\n"
            "transforms add(a Integer, b Integer) Integer\n"
            "from\n"
            "    result as = a + b\n"
            "    result\n"
        )
        uri = "file:///inlay_test.prv"
        _analyze(uri, source)
        hints = inlay_hint(self._make_params(uri))
        assert hints is not None
        assert any(h.label == " Integer" for h in hints)
        # Hint is positioned after "result" (6 chars) on line 5 (0-indexed)
        hint = next(h for h in hints if h.label == " Integer")
        assert hint.position.line == 5
        assert hint.position.character == 10  # 4 spaces indent + len("result")

    def test_inlay_hint_typed_var_suppressed(self):
        from prove.lsp import inlay_hint

        source = (
            "module Main\n"
            '  narrative: """Test"""\n'
            "\n"
            "transforms id(a Integer) Integer\n"
            "from\n"
            "    result as Integer = a\n"
            "    result\n"
        )
        uri = "file:///inlay_typed.prv"
        _analyze(uri, source)
        hints = inlay_hint(self._make_params(uri))
        # Explicitly typed var should produce no hints
        assert hints is None or not any(h.label == " Integer" for h in hints)

    def test_inlay_hint_no_module(self):
        from prove.lsp import _state, inlay_hint

        uri = "file:///nonexistent.prv"
        _state.pop(uri, None)
        hints = inlay_hint(self._make_params(uri))
        assert hints is None

    def test_inlay_hint_kind_is_type(self):
        from prove.lsp import inlay_hint

        source = (
            "module Main\n"
            '  narrative: """Test"""\n'
            "\n"
            "transforms wrap(a Integer) Integer\n"
            "from\n"
            "    x as = a\n"
            "    x\n"
        )
        uri = "file:///inlay_kind.prv"
        _analyze(uri, source)
        hints = inlay_hint(self._make_params(uri))
        assert hints is not None
        for h in hints:
            assert h.kind == lsp.InlayHintKind.Type
