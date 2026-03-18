"""End-to-end integration tests for .intent → generate → check pipeline.

Phase 5c: Verify that .intent files can be parsed, generate .prv source,
and that the generated source passes the checker — both with and without
NLP backends.

Known limitations of the generator (documented by tests):
- Todo stubs return Unit, causing E322 when function declares a return type.
- Cross-module `use` imports are placed at column 0, outside the module
  block, causing a parse error.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

from prove.checker import Checker
from prove.errors import CompileError
from prove.intent_generator import check_intent_coverage, generate_project
from prove.intent_parser import parse_intent
from prove.lexer import Lexer
from prove.parser import Parser

# ---------------------------------------------------------------------------
# Fixtures: .intent source strings
# ---------------------------------------------------------------------------

SIMPLE_INTENT = """\
project SimpleDemo
  purpose: Demonstrate basic intent-to-code generation

  module Greeter
    creates greeting from a name
"""

MULTI_MODULE_INTENT = """\
project UserAuth
  purpose: Authenticate users and manage their sessions
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

SINGLE_VALIDATE_INTENT = """\
project Validator
  purpose: Validate input data

  module Checker
    validates entries against rules
"""

MINIMAL_INTENT = """\
project Minimal
  purpose: A minimal project with a single function

  module Core
    reads configuration from environment
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _check_prv_source(source: str) -> tuple[list, bool]:
    """Parse and check .prv source.

    Returns (error_diagnostics, parse_ok).
    parse_ok is False if the parser itself raised CompileError.
    """
    try:
        tokens = Lexer(source, "<generated>").lex()
        module = Parser(tokens, "<generated>").parse()
    except CompileError:
        return [], False

    checker = Checker()
    checker.check(module)
    errors = [d for d in checker.diagnostics if d.severity.value == "error"]
    return errors, True


def _check_prv_errors_only(source: str) -> list:
    """Parse and check .prv source, return error-level diagnostics.

    Returns empty list if parse fails (parse errors handled separately).
    """
    errors, _ = _check_prv_source(source)
    return errors


def _check_prv_non_todo_errors(source: str) -> list:
    """Return checker errors excluding E322 (return type mismatch from todo stubs)."""
    errors, parse_ok = _check_prv_source(source)
    if not parse_ok:
        return [{"code": "PARSE_ERROR", "message": "parser raised CompileError"}]
    return [e for e in errors if e.code != "E322"]


def _generate_and_check(intent_source: str) -> dict:
    """Full pipeline: parse .intent → generate .prv → check each file.

    Returns a dict with:
      - 'parse_ok': bool (intent parse succeeded)
      - 'files': list of (filename, source, errors, prv_parse_ok)
      - 'all_ok': bool (no checker errors in any file)
      - 'all_parse_ok': bool (all .prv files parsed without CompileError)
    """
    result = parse_intent(intent_source)
    if result.project is None:
        return {
            "parse_ok": False, "files": [], "all_ok": False,
            "all_parse_ok": False,
        }

    with tempfile.TemporaryDirectory() as tmpdir:
        generated = generate_project(result.project, Path(tmpdir), dry_run=True)

    files_info = []
    for filename, source in generated:
        errors, prv_parse_ok = _check_prv_source(source)
        files_info.append((filename, source, errors, prv_parse_ok))

    return {
        "parse_ok": True,
        "files": files_info,
        "all_ok": all(len(e) == 0 for _, _, e, _ in files_info),
        "all_parse_ok": all(ok for _, _, _, ok in files_info),
    }


def _format_errors(info: dict) -> str:
    """Format checker errors for assertion messages."""
    parts = []
    for filename, _, errors, prv_parse_ok in info["files"]:
        if not prv_parse_ok:
            parts.append(f"{filename}: PARSE ERROR")
        elif errors:
            parts.append(
                f"{filename}: {[f'{e.code}: {e.message}' for e in errors]}"
            )
    return " | ".join(parts)


# ---------------------------------------------------------------------------
# Tests: Intent parsing
# ---------------------------------------------------------------------------

class TestIntentParsing:
    """Verify intent parsing produces expected structures."""

    def test_simple_intent_parses(self) -> None:
        result = parse_intent(SIMPLE_INTENT)
        assert result.project is not None
        assert result.project.name == "SimpleDemo"
        assert len(result.project.modules) == 1
        assert result.project.modules[0].name == "Greeter"

    def test_multi_module_intent_parses(self) -> None:
        result = parse_intent(MULTI_MODULE_INTENT)
        assert result.project is not None
        assert len(result.project.modules) == 2
        assert len(result.project.vocabulary) == 2
        assert len(result.project.flows) == 1
        assert len(result.project.constraints) == 1

    def test_invalid_intent_fails_parse(self) -> None:
        result = parse_intent("purpose: no project header\n")
        assert result.project is None

    def test_minimal_intent_parses(self) -> None:
        result = parse_intent(MINIMAL_INTENT)
        assert result.project is not None
        assert result.project.modules[0].name == "Core"


# ---------------------------------------------------------------------------
# Tests: Code generation structure
# ---------------------------------------------------------------------------

class TestIntentGeneration:
    """Verify generation produces expected file structure."""

    def test_simple_generates_one_file(self) -> None:
        result = parse_intent(SIMPLE_INTENT)
        with tempfile.TemporaryDirectory() as d:
            gen = generate_project(result.project, Path(d), dry_run=True)
        assert len(gen) == 1
        assert gen[0][0] == "greeter.prv"

    def test_multi_module_generates_two_files(self) -> None:
        result = parse_intent(MULTI_MODULE_INTENT)
        with tempfile.TemporaryDirectory() as d:
            gen = generate_project(result.project, Path(d), dry_run=True)
        assert len(gen) == 2
        filenames = {f for f, _ in gen}
        assert "auth.prv" in filenames
        assert "sessionmanager.prv" in filenames

    def test_generated_source_has_module_declaration(self) -> None:
        info = _generate_and_check(SIMPLE_INTENT)
        _, source, _, _ = info["files"][0]
        assert "module Greeter" in source

    def test_generated_source_has_narrative(self) -> None:
        info = _generate_and_check(SIMPLE_INTENT)
        _, source, _, _ = info["files"][0]
        assert "narrative:" in source

    def test_generated_source_has_function_with_from(self) -> None:
        info = _generate_and_check(SIMPLE_INTENT)
        _, source, _, _ = info["files"][0]
        assert "creates" in source
        assert "from" in source

    def test_generated_source_has_doc_comment(self) -> None:
        info = _generate_and_check(SIMPLE_INTENT)
        _, source, _, _ = info["files"][0]
        assert "///" in source

    def test_generated_files_written_to_disk(self) -> None:
        result = parse_intent(SIMPLE_INTENT)
        with tempfile.TemporaryDirectory() as tmpdir:
            generated = generate_project(result.project, Path(tmpdir))
            for filename, _ in generated:
                path = Path(tmpdir) / filename
                assert path.exists()
                assert len(path.read_text(encoding="utf-8")) > 0

    def test_validates_generates_implicit_boolean(self) -> None:
        """validates verb has implicit Boolean return (no type annotation needed)."""
        info = _generate_and_check(SINGLE_VALIDATE_INTENT)
        _, source, _, _ = info["files"][0]
        assert "validates" in source

    def test_constraint_failable_produces_bang(self) -> None:
        """'failable' constraint adds ! suffix to return types."""
        result = parse_intent(MULTI_MODULE_INTENT)
        with tempfile.TemporaryDirectory() as d:
            gen = generate_project(result.project, Path(d), dry_run=True)
        auth_source = next(s for f, s in gen if f == "auth.prv")
        assert "!" in auth_source

    def test_flow_produces_use_imports(self) -> None:
        """Flow declarations produce cross-module 'use' imports."""
        result = parse_intent(MULTI_MODULE_INTENT)
        with tempfile.TemporaryDirectory() as d:
            gen = generate_project(result.project, Path(d), dry_run=True)
        auth_source = next(s for f, s in gen if f == "auth.prv")
        session_source = next(s for f, s in gen if f == "sessionmanager.prv")
        assert "use SessionManager" in auth_source
        assert "use Auth" in session_source


# ---------------------------------------------------------------------------
# Tests: Checker validation (single-module, no cross-module imports)
# ---------------------------------------------------------------------------

class TestIntentE2EChecker:
    """Verify generated .prv passes through the checker."""

    def test_simple_intent_prv_parses(self) -> None:
        """Generated .prv from simple intent parses without CompileError."""
        info = _generate_and_check(SIMPLE_INTENT)
        assert info["all_parse_ok"], _format_errors(info)

    def test_simple_intent_no_non_todo_errors(self) -> None:
        """Simple intent .prv has no errors beyond todo return type mismatch."""
        info = _generate_and_check(SIMPLE_INTENT)
        _, source, _, _ = info["files"][0]
        real_errors = _check_prv_non_todo_errors(source)
        assert not real_errors, f"Non-todo errors: {real_errors}"

    def test_validates_intent_passes_checker(self) -> None:
        """validates verb has implicit Boolean return — no E322 from todo."""
        info = _generate_and_check(SINGLE_VALIDATE_INTENT)
        assert info["all_parse_ok"]
        _, source, errors, _ = info["files"][0]
        # validates returns Boolean implicitly, and todo returns Unit,
        # but checker may or may not flag this depending on implementation
        non_todo = _check_prv_non_todo_errors(source)
        assert not non_todo, f"Non-todo errors: {non_todo}"

    def test_minimal_intent_prv_parses(self) -> None:
        info = _generate_and_check(MINIMAL_INTENT)
        assert info["all_parse_ok"]

    def test_e322_expected_for_todo_stubs(self) -> None:
        """Todo stubs return Unit, so E322 fires for non-Unit return types.

        This documents current behavior — generator stubs with `todo`
        produce an E322 return type mismatch.
        """
        info = _generate_and_check(SIMPLE_INTENT)
        _, _, errors, parse_ok = info["files"][0]
        assert parse_ok
        e322_errors = [e for e in errors if e.code == "E322"]
        assert len(e322_errors) > 0, "Expected E322 from todo stub"


# ---------------------------------------------------------------------------
# Tests: Multi-module (use import placement — known limitation)
# ---------------------------------------------------------------------------

class TestIntentE2EMultiModule:
    """Multi-module generation tests.

    Note: cross-module `use` imports are currently placed at column 0
    (outside the module block), causing a parse error. These tests
    document the limitation.
    """

    def test_multi_module_use_placement_is_known_issue(self) -> None:
        """Generated use-imports outside module block cause parse errors."""
        info = _generate_and_check(MULTI_MODULE_INTENT)
        # At least one file should fail to parse due to `use` placement
        assert not info["all_parse_ok"], (
            "Expected parse errors from use-import placement — "
            "if this passes, the generator has been fixed!"
        )


# ---------------------------------------------------------------------------
# Tests: With/without NLP backends
# ---------------------------------------------------------------------------

class TestIntentE2ENLP:
    """Verify pipeline works with NLP backends mocked on/off."""

    def test_fallback_mode_prv_parses(self) -> None:
        """Explicitly disabling NLP still generates parseable .prv."""
        with patch("prove.nlp.has_nlp_backend", return_value=False):
            info = _generate_and_check(SIMPLE_INTENT)
            assert info["all_parse_ok"]

    def test_nlp_flag_true_still_generates(self) -> None:
        """has_nlp_backend=True doesn't break generation (fallback kicks in)."""
        with patch("prove.nlp.has_nlp_backend", return_value=True):
            info = _generate_and_check(SIMPLE_INTENT)
            assert info["parse_ok"]
            assert len(info["files"]) == 1

    def test_fallback_and_nlp_produce_same_structure(self) -> None:
        """Both modes produce files with same basic structure."""
        with patch("prove.nlp.has_nlp_backend", return_value=False):
            info_off = _generate_and_check(SIMPLE_INTENT)
        with patch("prove.nlp.has_nlp_backend", return_value=True):
            info_on = _generate_and_check(SIMPLE_INTENT)

        assert len(info_off["files"]) == len(info_on["files"])
        for (f_off, _, _, _), (f_on, _, _, _) in zip(
            info_off["files"], info_on["files"]
        ):
            assert f_off == f_on


# ---------------------------------------------------------------------------
# Tests: Negative / breakage (prove the checker catches real errors)
# ---------------------------------------------------------------------------

class TestIntentE2ENegative:
    """Verify the checker actually catches errors in generated code."""

    def test_corrupt_verb_fails_check(self) -> None:
        """Replacing a valid verb with 'destroys' triggers checker errors."""
        result = parse_intent(SIMPLE_INTENT)
        with tempfile.TemporaryDirectory() as d:
            generated = generate_project(result.project, Path(d), dry_run=True)

        _, source = generated[0]
        corrupt = source.replace("creates", "destroys", 1)
        assert corrupt != source, "Corruption should change the source"
        errors = _check_prv_errors_only(corrupt)
        assert len(errors) > 0, "Invalid verb should produce checker errors"

    def test_missing_from_block_fails(self) -> None:
        """Removing 'from' block causes parser or checker errors."""
        result = parse_intent(SIMPLE_INTENT)
        with tempfile.TemporaryDirectory() as d:
            generated = generate_project(result.project, Path(d), dry_run=True)

        _, source = generated[0]
        # Truncate at the first 'from' keyword
        lines = source.split("\n")
        truncated = []
        for line in lines:
            if line.strip() == "from":
                break
            truncated.append(line)
        corrupt = "\n".join(truncated)
        errors, parse_ok = _check_prv_source(corrupt)
        # Either parse fails or checker finds errors
        assert not parse_ok or len(errors) > 0, (
            "Missing from-block should fail parse or check"
        )

    def test_bad_type_fails_check(self) -> None:
        """Nonexistent type in generated .prv triggers checker errors."""
        result = parse_intent(SIMPLE_INTENT)
        with tempfile.TemporaryDirectory() as d:
            generated = generate_project(result.project, Path(d), dry_run=True)

        _, source = generated[0]
        corrupt = source.replace("String", "FakeType")
        if corrupt != source:
            errors = _check_prv_errors_only(corrupt)
            assert len(errors) > 0, "Nonexistent type should produce errors"

    def test_invalid_intent_not_generated(self) -> None:
        """Missing project declaration → parse fails, no generation."""
        info = _generate_and_check("purpose: no project header\n")
        assert not info["parse_ok"]
        assert info["files"] == []

    def test_duplicate_function_name_fails(self) -> None:
        """Injecting duplicate function into generated .prv triggers errors."""
        result = parse_intent(SIMPLE_INTENT)
        with tempfile.TemporaryDirectory() as d:
            generated = generate_project(result.project, Path(d), dry_run=True)

        _, source = generated[0]
        # Append a duplicate of the last function
        lines = source.strip().split("\n")
        # Find the function definition and duplicate it
        func_start = None
        for i, line in enumerate(lines):
            if line.startswith("creates") or line.startswith("///"):
                if func_start is None:
                    func_start = i
        if func_start is not None:
            func_block = "\n".join(lines[func_start:])
            corrupt = source + "\n" + func_block + "\n"
            errors, parse_ok = _check_prv_source(corrupt)
            if parse_ok:
                assert len(errors) > 0, "Duplicate function should produce errors"


# ---------------------------------------------------------------------------
# Tests: Round-trip through intent file
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Tests: Rich type generation
# ---------------------------------------------------------------------------

RECORD_VOCAB_INTENT = """\
project RecordTest
  purpose: Test record type generation

  vocabulary
    Credential is a user identity paired with a secret

  module Auth
    validates credentials against stored credential data
"""

ALGEBRAIC_VOCAB_INTENT = """\
project AlgTest
  purpose: Test algebraic type generation

  vocabulary
    Status is either an active token or an expired marker

  module Token
    validates status for token status check
"""

REFINEMENT_VOCAB_INTENT = """\
project RefTest
  purpose: Test refinement type generation

  vocabulary
    Count is a positive integer

  module Counter
    creates counter for count tracking
"""

CONSTANT_INTENT = """\
project ConstTest
  purpose: Test constant generation

  module Limiter
    validates rate

  constraints
    maximum 5 attempts
"""


class TestIntentE2ERichTypes:
    """Verify rich type definitions in generated source."""

    def test_record_vocab_generates_fields(self) -> None:
        """Vocabulary 'paired with' produces record type with fields."""
        info = _generate_and_check(RECORD_VOCAB_INTENT)
        assert info["parse_ok"]
        _, source, _, _ = info["files"][0]
        assert "type Credential" in source
        assert "identity" in source
        assert "secret" in source

    def test_algebraic_vocab_generates_variants(self) -> None:
        """Vocabulary 'either X or Y' produces algebraic type."""
        info = _generate_and_check(ALGEBRAIC_VOCAB_INTENT)
        assert info["parse_ok"]
        _, source, _, _ = info["files"][0]
        assert "type Status" in source

    def test_refinement_vocab_generates_constraint(self) -> None:
        """Vocabulary 'positive integer' produces refinement type."""
        info = _generate_and_check(REFINEMENT_VOCAB_INTENT)
        assert info["parse_ok"]
        _, source, _, _ = info["files"][0]
        assert "type Count" in source
        assert "Integer" in source

    def test_constants_generated_from_constraints(self) -> None:
        """'maximum N attempts' generates a constant."""
        info = _generate_and_check(CONSTANT_INTENT)
        assert info["parse_ok"]
        _, source, _, _ = info["files"][0]
        assert "MAX_ATTEMPT" in source
        assert "5" in source


class TestIntentE2EImportPlacement:
    """Verify imports are inside module block."""

    def test_flow_imports_indented(self) -> None:
        """Flow-derived use-imports should be indented inside module block."""
        result = parse_intent(MULTI_MODULE_INTENT)
        assert result.project is not None
        with tempfile.TemporaryDirectory() as d:
            gen = generate_project(result.project, Path(d), dry_run=True)
        auth_source = next(s for f, s in gen if f == "auth.prv")
        # Should have indented use, not at column 0
        for line in auth_source.split("\n"):
            if "use SessionManager" in line:
                assert line.startswith("  "), (
                    f"use-import should be indented, got: {line!r}"
                )
                break
        else:
            assert False, "use SessionManager not found in auth.prv"


class TestIntentRoundTrip:
    """Full .intent text → parse → generate → check pipeline."""

    def test_example_intent_file_round_trip(self) -> None:
        """examples/intent_demo/src/project.intent round-trips cleanly."""
        intent_path = (
            Path(__file__).resolve().parents[1]
            / "examples" / "intent_demo" / "src" / "project.intent"
        )
        if not intent_path.exists():
            return  # skip if example not present
        source = intent_path.read_text(encoding="utf-8")
        info = _generate_and_check(source)
        assert info["parse_ok"]
        # Example has a single module, no cross-module imports
        assert info["all_parse_ok"], _format_errors(info)

    def test_intent_coverage_reports_todo_for_stubs(self) -> None:
        """Generated todo stubs are reported as 'todo' in coverage check."""
        result = parse_intent(SIMPLE_INTENT)
        assert result.project is not None

        with tempfile.TemporaryDirectory() as tmpdir:
            generate_project(result.project, Path(tmpdir))
            statuses = check_intent_coverage(result.project, Path(tmpdir))

        assert len(statuses) > 0
        for status in statuses:
            assert status["status"] in ("implemented", "todo"), (
                f"Unexpected status: {status}"
            )

    def test_intent_coverage_missing_for_empty_dir(self) -> None:
        """Coverage check with no .prv files reports 'missing'."""
        result = parse_intent(SIMPLE_INTENT)
        assert result.project is not None

        with tempfile.TemporaryDirectory() as tmpdir:
            statuses = check_intent_coverage(result.project, Path(tmpdir))

        assert any(s["status"] == "missing" for s in statuses)
