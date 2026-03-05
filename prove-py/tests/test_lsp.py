"""Tests for the Prove LSP server."""

from __future__ import annotations

from lsprotocol import types as lsp

from prove.errors import Severity
from prove.lsp import (
    _SEVERITY_MAP,
    DocumentState,
    _analyze,
    _build_import_edit,
    _extract_undefined_name,
    _get_word_at,
    _is_e310,
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
            '  narrative: """Test module"""\n'
            "\n"
            "transforms add(a Integer, b Integer) Integer\n"
            "from\n"
            "    a + b\n"
        )
        ds = _analyze("file:///test.prv", source)
        assert ds.module is not None
        assert ds.symbols is not None
        assert len(ds.diagnostics) == 0

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

        source = 'module Main\n  InputOutput outputs console\nmain()\nfrom\n    console("hi")\n'
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
        assert any(s.module == "InputOutput" and s.verb == "outputs" for s in suggestions)

    def test_index_contains_file(self):
        index = build_import_index()
        assert "file" in index
        suggestions = index["file"]
        assert any(s.module == "InputOutput" and s.verb == "inputs" for s in suggestions)

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
        suggestion = ImportSuggestion(module="InputOutput", verb="outputs", name="console")
        edit = _build_import_edit(ds, suggestion)
        assert edit is not None
        assert "InputOutput outputs console" in edit.new_text
        # Should insert after the module line
        assert edit.range.start.line == 1

    def test_extend_existing_import(self):
        source = (
            "module Main\n"
            "  InputOutput outputs console\n"
            "outputs run() Unit\n"
            "from\n"
            '    console("hi")\n'
        )
        ds = self._make_ds(source)
        suggestion = ImportSuggestion(module="InputOutput", verb="outputs", name="file")
        edit = _build_import_edit(ds, suggestion)
        assert edit is not None
        assert edit.new_text == "  InputOutput outputs console file"
        # Should replace line 1 (the existing import line)
        assert edit.range.start.line == 1

    def test_already_imported_returns_none(self):
        source = (
            "module Main\n"
            "  InputOutput outputs console\n"
            "outputs run() Unit\n"
            "from\n"
            '    console("hi")\n'
        )
        ds = self._make_ds(source)
        suggestion = ImportSuggestion(module="InputOutput", verb="outputs", name="console")
        edit = _build_import_edit(ds, suggestion)
        assert edit is None

    def test_no_module_returns_none(self):
        ds = DocumentState()  # module is None
        suggestion = ImportSuggestion(module="InputOutput", verb="outputs", name="console")
        edit = _build_import_edit(ds, suggestion)
        assert edit is None

    def test_extend_existing_import_different_verb(self):
        source = (
            "module Main\n"
            "  InputOutput outputs console\n"
            "outputs run() Unit\n"
            "from\n"
            '    console("hi")\n'
        )
        ds = self._make_ds(source)
        suggestion = ImportSuggestion(module="InputOutput", verb="inputs", name="file")
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
        for fn in ("len", "map", "filter", "reduce", "to_string", "clamp"):
            assert fn in labels, f"builtin '{fn}' missing from completions"
        # println/print/readln are no longer builtins — they come from InputOutput
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
        assert any("console" in l for l in labels)

    def test_stdlib_functions_with_valid_file(self):
        _analyze(
            "<test://valid>",
            'module Main\n  narrative: """Test"""\n\nmain()\nfrom\n    console("hi")\n',
        )
        labels = _complete_labels("<test://valid>")
        assert any("console" in l for l in labels)

    def test_stdlib_completions_have_detail(self):
        """Stdlib items should show module name in label_details.description."""
        _analyze("<test://det>", "")
        result = _complete("<test://det>")
        console_items = [
            i for i in result.items if "console" in i.label and "InputOutput" in i.label
        ]
        assert len(console_items) >= 1
        item = console_items[0]
        assert item.label_details is not None
        assert item.label_details.description == "InputOutput"

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
        assert any("add" in l for l in labels)

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
        assert "InputOutput" in edit.new_text
        assert "file" in edit.new_text

    def test_stdlib_completion_no_duplicate_import(self):
        """If already imported, that specific verb is hidden but other verbs still show."""
        _analyze(
            "file:///noimport.prv",
            "module Main\n"
            '  narrative: """Test"""\n'
            "  InputOutput outputs console\n"
            "\n"
            "main()\nfrom\n"
            '    console("hi")\n',
        )
        result = _complete("file:///noimport.prv")
        # Find console with InputOutput prefix
        console_items = [
            i for i in result.items if "console" in i.label and "InputOutput" in i.label
        ]
        # outputs is imported (shows with verb detail), others show "Auto-import"
        assert len(console_items) == 3
        # Check that outputs has verb detail (not Auto-import)
        outputs_item = next(i for i in console_items if "outputs" in i.label)
        assert outputs_item.detail == "outputs"

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
        file_items = [i for i in result.items if "file" in i.label and "InputOutput" in i.label]

        assert len(file_items) >= 1
        item = file_items[0]
        assert item.additional_text_edits is not None, (
            "auto-import should work even when file has parse errors"
        )
        edit = item.additional_text_edits[0]
        assert "InputOutput" in edit.new_text
        assert "file" in edit.new_text
        # Should insert after narrative (line 2), not at end of file
        assert edit.range.start.line == 2

    def test_auto_import_after_existing_imports_with_errors(self):
        """Auto-import should go after existing imports, even with errors."""
        _analyze(
            "file:///afterimport.prv",
            "module Main\n"
            '  narrative: """Test"""\n'
            "  InputOutput outputs console\n"
            "\n"
            "outputs handle()\n"
            "from\n"
            "    match\n"
            "        Get => ok()\n",
        )
        result = _complete("file:///afterimport.prv")
        file_items = [i for i in result.items if "file" in i.label and "InputOutput" in i.label]

        assert len(file_items) >= 1
        item = file_items[0]
        assert item.additional_text_edits is not None
        edit = item.additional_text_edits[0]
        # Should insert after "InputOutput outputs console" (line 2), so at line 3
        assert edit.range.start.line == 3

    def test_channel_dispatch_shows_all_verbs(self):
        """file has inputs, outputs, validates — all should appear."""
        _analyze("<test://dispatch>", "")
        result = _complete("<test://dispatch>")
        file_items = [i for i in result.items if "file" in i.label and "InputOutput" in i.label]
        verbs_found = set()
        for item in file_items:
            if item.label_details and item.label_details.detail:
                verbs_found.add(item.label_details.detail.strip())
        for verb in ("inputs", "outputs", "validates"):
            assert verb in verbs_found, (
                f"verb '{verb}' missing from file completions; found {verbs_found}"
            )

    def test_stdlib_completions_detail_with_signature(self):
        """Stdlib completions should show 'Auto-import' in detail, signature in docs."""
        _analyze("<test://sig>", "")
        result = _complete("<test://sig>")
        console_items = [
            i for i in result.items if "console" in i.label and "InputOutput" in i.label
        ]
        assert len(console_items) >= 1
        item = console_items[0]
        # Detail should be "Auto-import"
        assert item.detail == "Auto-import"
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
        # Find local add (not from Table module)
        add_items = [
            i
            for i in result.items
            if "add" in i.label and "Main" not in i.label and "Table" not in i.label
        ]
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
        ds = DocumentState(source="module Main")
        params = lsp.CompletionParams(
            text_document=lsp.TextDocumentIdentifier("test:///test.prv"),
            position=lsp.Position(line=0, character=0),
        )
        result = completion(params)

        for item in result.items:
            if item.label == "InputOutput console":
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
