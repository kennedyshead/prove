"""Tests for .intent file parser and generator."""

from __future__ import annotations

from prove.intent_ast import IntentModule, IntentProject, VerbPhrase, VocabularyEntry
from prove.intent_generator import check_intent_coverage, generate_module_source
from prove.intent_parser import parse_intent


SAMPLE_INTENT = """\
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


class TestIntentParser:
    def test_parse_project_header(self) -> None:
        result = parse_intent(SAMPLE_INTENT)
        assert result.project is not None
        assert result.project.name == "UserAuth"
        assert result.project.purpose == "Authenticate users and manage their sessions"
        assert result.project.domain == "Security"

    def test_parse_vocabulary(self) -> None:
        result = parse_intent(SAMPLE_INTENT)
        assert result.project is not None
        vocab = result.project.vocabulary
        assert len(vocab) == 2
        assert vocab[0].name == "Credential"
        assert "user identity" in vocab[0].description
        assert vocab[1].name == "Session"

    def test_parse_modules(self) -> None:
        result = parse_intent(SAMPLE_INTENT)
        assert result.project is not None
        modules = result.project.modules
        assert len(modules) == 2
        assert modules[0].name == "Auth"
        assert len(modules[0].intents) == 3
        assert modules[0].intents[0].verb == "validates"
        assert modules[0].intents[0].noun == "credentials"
        assert modules[1].name == "SessionManager"
        assert len(modules[1].intents) == 2

    def test_parse_flow(self) -> None:
        result = parse_intent(SAMPLE_INTENT)
        assert result.project is not None
        flows = result.project.flows
        assert len(flows) == 1
        assert len(flows[0].steps) == 2
        assert flows[0].steps[0].module == "Auth"
        assert flows[0].steps[1].module == "SessionManager"

    def test_parse_constraints(self) -> None:
        result = parse_intent(SAMPLE_INTENT)
        assert result.project is not None
        constraints = result.project.constraints
        assert len(constraints) == 1
        assert "failable" in constraints[0].text

    def test_missing_project_is_error(self) -> None:
        result = parse_intent("purpose: something\n")
        assert result.project is None
        assert any(d.severity == "error" for d in result.diagnostics)

    def test_missing_purpose_is_error(self) -> None:
        result = parse_intent("project Foo\n")
        assert result.project is None
        assert any(d.severity == "error" for d in result.diagnostics)

    def test_unrecognized_verb_warns(self) -> None:
        source = """\
project Test
  purpose: test
  module Foo
    handles something gracefully
"""
        result = parse_intent(source)
        assert result.project is not None
        assert any(d.code == "W601" for d in result.diagnostics)
        assert len(result.project.modules[0].intents) == 0

    def test_comments_skipped(self) -> None:
        source = """\
project Test
  purpose: test
  // This is a comment
  module Foo
    validates input data
"""
        result = parse_intent(source)
        assert result.project is not None
        assert len(result.project.modules) == 1

    def test_minimal_intent(self) -> None:
        source = """\
project Minimal
  purpose: A minimal project
"""
        result = parse_intent(source)
        assert result.project is not None
        assert result.project.name == "Minimal"
        assert result.project.modules == []


class TestIntentGenerator:
    def test_generate_module_source(self) -> None:
        module = IntentModule(
            name="Auth",
            intents=[
                VerbPhrase(verb="validates", noun="credentials",
                           context="against stored data", raw_line="validates credentials against stored data"),
            ],
        )
        project = IntentProject(
            name="Test", purpose="test",
            vocabulary=[VocabularyEntry(name="Credential", description="user identity")],
        )
        source = generate_module_source(module, project)
        assert "module Auth" in source
        assert "narrative:" in source
        assert "validates" in source

    def test_generate_with_domain(self) -> None:
        module = IntentModule(name="Mod", intents=[])
        project = IntentProject(name="P", purpose="test", domain="Finance")
        source = generate_module_source(module, project)
        assert "domain: Finance" in source


class TestIntentCoverage:
    def test_all_missing(self) -> None:
        from pathlib import Path
        import tempfile

        project = IntentProject(
            name="Test",
            purpose="test",
            modules=[
                IntentModule(
                    name="Auth",
                    intents=[
                        VerbPhrase(verb="validates", noun="credentials",
                                   context="", raw_line="validates credentials"),
                    ],
                ),
            ],
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            statuses = check_intent_coverage(project, Path(tmpdir))
            assert len(statuses) == 1
            assert statuses[0]["status"] == "missing"
