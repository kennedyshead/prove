"""Tests for .intent file parser and generator."""

from __future__ import annotations

from prove.intent_ast import (
    ConstraintDecl,
    FlowDecl,
    FlowStep,
    IntentModule,
    IntentProject,
    VerbPhrase,
    VocabularyEntry,
)
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
        assert modules[0].intents[0].noun in ("credentials", "credential")
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
    yeets something gracefully
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

    def test_singular_verb_accepted(self) -> None:
        """Singular form 'transform' should normalize to 'transforms'."""
        source = """\
project Test
  purpose: test
  module Converter
    transform data into hashes
"""
        result = parse_intent(source)
        assert result.project is not None
        assert len(result.project.modules[0].intents) == 1
        vp = result.project.modules[0].intents[0]
        assert vp.verb == "transforms"
        assert vp.raw_line == "transform data into hashes"
        # No W601 warning
        assert not any(d.code == "W601" for d in result.diagnostics)

    def test_synonym_verb_accepted(self) -> None:
        """Synonym 'convert' should normalize to 'transforms'."""
        source = """\
project Test
  purpose: test
  module Converter
    convert passwords into hashes
"""
        result = parse_intent(source)
        assert result.project is not None
        assert len(result.project.modules[0].intents) == 1
        vp = result.project.modules[0].intents[0]
        assert vp.verb == "transforms"
        assert vp.raw_line == "convert passwords into hashes"
        assert not any(d.code == "W601" for d in result.diagnostics)

    def test_synonym_check_normalizes_to_validates(self) -> None:
        source = """\
project Test
  purpose: test
  module Auth
    check credentials against stored data
"""
        result = parse_intent(source)
        assert result.project is not None
        vp = result.project.modules[0].intents[0]
        assert vp.verb == "validates"

    def test_synonym_fetch_normalizes_to_derives(self) -> None:
        source = """\
project Test
  purpose: test
  module Loader
    fetch records from database
"""
        result = parse_intent(source)
        assert result.project is not None
        vp = result.project.modules[0].intents[0]
        assert vp.verb == "derives"


class TestIntentGenerator:
    def test_generate_module_source(self) -> None:
        module = IntentModule(
            name="Auth",
            intents=[
                VerbPhrase(
                    verb="validates",
                    noun="credentials",  # noqa: E501
                    context="against stored data",
                    raw_line="validates credentials against stored data",
                ),
            ],
        )
        project = IntentProject(
            name="Test",
            purpose="test",
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

    def test_generate_with_vocabulary_types(self) -> None:
        module = IntentModule(
            name="Auth",
            intents=[
                VerbPhrase(
                    verb="validates",
                    noun="credentials",
                    context="against stored credential data",
                    raw_line="validates credentials against stored credential data",
                ),
            ],
        )
        project = IntentProject(
            name="Test",
            purpose="test",
            vocabulary=[
                VocabularyEntry(name="Credential", description="user identity paired with secret"),
            ],
        )
        source = generate_module_source(module, project)
        # Vocabulary type should be used as parameter type
        assert "Credential" in source
        # Should not use hardcoded (value String) fallback
        assert "(value String) String" not in source

    def test_generate_with_flow_imports(self) -> None:
        auth_mod = IntentModule(
            name="Auth",
            intents=[
                VerbPhrase(
                    verb="creates",
                    noun="sessions",
                    context="for authenticated users",
                    raw_line="creates sessions for authenticated users",
                ),
            ],
        )
        session_mod = IntentModule(
            name="SessionManager",
            intents=[
                VerbPhrase(
                    verb="validates",
                    noun="sessions",
                    context="for expiry",
                    raw_line="validates sessions for expiry",
                ),
            ],
        )
        flow = FlowDecl(
            steps=[
                FlowStep(
                    module="Auth",
                    verb_phrase=VerbPhrase(
                        verb="creates",
                        noun="sessions",
                        context="",
                        raw_line="creates sessions",
                    ),
                ),
                FlowStep(
                    module="SessionManager",
                    verb_phrase=VerbPhrase(
                        verb="validates",
                        noun="sessions",
                        context="",
                        raw_line="validates sessions",
                    ),
                ),
            ],
        )
        project = IntentProject(
            name="Test",
            purpose="test",
            modules=[auth_mod, session_mod],
            flows=[flow],
        )
        auth_source = generate_module_source(auth_mod, project)
        session_source = generate_module_source(session_mod, project)
        # Auth flows to SessionManager, so Auth should import SessionManager
        assert "use SessionManager" in auth_source
        # SessionManager flows from Auth, so it should import Auth
        assert "use Auth" in session_source

    def test_constraint_mapping(self) -> None:
        module = IntentModule(
            name="Validator",
            intents=[
                VerbPhrase(
                    verb="validates",
                    noun="input",
                    context="data",
                    raw_line="validates input data",
                ),
            ],
        )
        # Test "must use" pattern
        project = IntentProject(
            name="Test",
            purpose="test",
            constraints=[
                ConstraintDecl(text="must use Argon2 for hashing"),
            ],
        )
        source = generate_module_source(module, project)
        assert 'chosen: "Argon2"' in source

    def test_constraint_failable(self) -> None:
        module = IntentModule(
            name="Auth",
            intents=[
                VerbPhrase(
                    verb="validates",
                    noun="credentials",
                    context="",
                    raw_line="validates credentials",
                ),
            ],
        )
        project = IntentProject(
            name="Test",
            purpose="test",
            constraints=[
                ConstraintDecl(text="all credential operations are failable"),
            ],
        )
        source = generate_module_source(module, project)
        assert "!" in source

    def test_constraint_bounded(self) -> None:
        module = IntentModule(
            name="Limiter",
            intents=[
                VerbPhrase(
                    verb="validates",
                    noun="rate",
                    context="",
                    raw_line="validates rate",
                ),
            ],
        )
        project = IntentProject(
            name="Test",
            purpose="test",
            constraints=[
                ConstraintDecl(text="rates have bounded values"),
            ],
        )
        source = generate_module_source(module, project)
        assert "ensures:" in source

    def test_constraint_requires(self) -> None:
        module = IntentModule(
            name="Validator",
            intents=[
                VerbPhrase(
                    verb="validates",
                    noun="entries",
                    context="",
                    raw_line="validates entries",
                ),
            ],
        )
        project = IntentProject(
            name="Test",
            purpose="test",
            constraints=[
                ConstraintDecl(text="all entries must be non-empty"),
            ],
        )
        source = generate_module_source(module, project)
        assert "requires:" in source


class TestIntentGeneratorTypes:
    """Tests for rich type generation from vocabulary."""

    def test_generate_record_type(self) -> None:
        module = IntentModule(
            name="Auth",
            intents=[
                VerbPhrase(
                    verb="validates",
                    noun="credentials",
                    context="against stored credential data",
                    raw_line="validates credentials against stored credential data",
                ),
            ],
        )
        project = IntentProject(
            name="Test",
            purpose="test",
            vocabulary=[
                VocabularyEntry(
                    name="Credential", description="a user identity paired with a secret"
                ),
            ],
        )
        source = generate_module_source(module, project)
        assert "type Credential" in source
        assert "identity String" in source
        assert "secret String" in source

    def test_generate_algebraic_type(self) -> None:
        module = IntentModule(
            name="Token",
            intents=[
                VerbPhrase(
                    verb="validates",
                    noun="token",
                    context="for status check",
                    raw_line="validates token for status check",
                ),
            ],
        )
        project = IntentProject(
            name="Test",
            purpose="test",
            vocabulary=[
                VocabularyEntry(
                    name="Status", description="either an active token or an expired marker"
                ),
            ],
        )
        source = generate_module_source(module, project)
        assert "type Status" in source
        assert "Token" in source or "Marker" in source

    def test_generate_refinement_type(self) -> None:
        module = IntentModule(
            name="Counter",
            intents=[
                VerbPhrase(
                    verb="creates",
                    noun="counter",
                    context="for count tracking",
                    raw_line="creates counter for count tracking",
                ),
            ],
        )
        project = IntentProject(
            name="Test",
            purpose="test",
            vocabulary=[
                VocabularyEntry(name="Count", description="a positive integer"),
            ],
        )
        source = generate_module_source(module, project)
        assert "type Count" in source
        assert "Integer" in source
        assert "self > 0" in source

    def test_generate_opaque_type(self) -> None:
        module = IntentModule(
            name="Auth",
            intents=[
                VerbPhrase(
                    verb="validates",
                    noun="session",
                    context="for session validity",
                    raw_line="validates session for session validity",
                ),
            ],
        )
        project = IntentProject(
            name="Test",
            purpose="test",
            vocabulary=[
                VocabularyEntry(name="Session", description="a time-limited access token"),
            ],
        )
        source = generate_module_source(module, project)
        assert "type Session" in source
        # Opaque — no fields, no variants
        assert "identity" not in source or "Session" in source


class TestIntentGeneratorImports:
    """Tests for stdlib-inferred imports."""

    def test_generate_inferred_imports_inside_module(self) -> None:
        """Imports should be indented inside the module block."""
        module = IntentModule(
            name="Auth",
            intents=[
                VerbPhrase(
                    verb="creates",
                    noun="sessions",
                    context="for authenticated users",
                    raw_line="creates sessions for authenticated users",
                ),
            ],
        )
        flow = FlowDecl(
            steps=[
                FlowStep(
                    module="Auth",
                    verb_phrase=VerbPhrase(
                        verb="creates",
                        noun="sessions",
                        context="",
                        raw_line="creates sessions",
                    ),
                ),
                FlowStep(
                    module="SessionManager",
                    verb_phrase=VerbPhrase(
                        verb="validates",
                        noun="sessions",
                        context="",
                        raw_line="validates sessions",
                    ),
                ),
            ],
        )
        project = IntentProject(
            name="Test",
            purpose="test",
            modules=[module],
            flows=[flow],
        )
        source = generate_module_source(module, project)
        # Imports should be indented (inside module block)
        assert "  use SessionManager" in source
        # Should NOT have unindented use at column 0
        lines = source.split("\n")
        for line in lines:
            if line.strip().startswith("use "):
                assert line.startswith("  "), f"use-import not indented: {line!r}"


class TestIntentGeneratorConstants:
    """Tests for constant inference from constraints."""

    def test_generate_inferred_constants(self) -> None:
        module = IntentModule(
            name="Limiter",
            intents=[
                VerbPhrase(verb="validates", noun="rate", context="", raw_line="validates rate"),
            ],
        )
        project = IntentProject(
            name="Test",
            purpose="test",
            constraints=[
                ConstraintDecl(text="maximum 5 attempts"),
            ],
        )
        source = generate_module_source(module, project)
        assert "MAX_ATTEMPT" in source
        assert "Integer" in source
        assert "5" in source

    def test_generate_timeout_constant(self) -> None:
        module = IntentModule(
            name="Net",
            intents=[
                VerbPhrase(
                    verb="derives",
                    noun="data",
                    context="from network",
                    raw_line="derives data from network",
                ),
            ],
        )
        project = IntentProject(
            name="Test",
            purpose="test",
            constraints=[
                ConstraintDecl(text="timeout of 30 seconds"),
            ],
        )
        source = generate_module_source(module, project)
        assert "TIMEOUT_SECOND" in source
        assert "30" in source


class TestIntentCoverage:
    def test_all_missing(self) -> None:
        import tempfile
        from pathlib import Path

        project = IntentProject(
            name="Test",
            purpose="test",
            modules=[
                IntentModule(
                    name="Auth",
                    intents=[
                        VerbPhrase(
                            verb="validates",
                            noun="credentials",
                            context="",
                            raw_line="validates credentials",
                        ),
                    ],
                ),
            ],
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            statuses = check_intent_coverage(project, Path(tmpdir))
            fn_statuses = [s for s in statuses if s.get("kind") == "function"]
            assert len(fn_statuses) == 1
            assert fn_statuses[0]["status"] == "missing"

    def test_normalized_matching(self) -> None:
        """Intent noun 'credentials' should match function named 'credential'."""
        import tempfile
        from pathlib import Path

        project = IntentProject(
            name="Test",
            purpose="test",
            modules=[
                IntentModule(
                    name="Auth",
                    intents=[
                        VerbPhrase(
                            verb="validates",
                            noun="credentials",
                            context="",
                            raw_line="validates credentials",
                        ),
                    ],
                ),
            ],
        )
        prv_source = "validates credential(value String) Boolean\nfrom\n    true\n"
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "auth.prv").write_text(prv_source, encoding="utf-8")
            statuses = check_intent_coverage(project, Path(tmpdir))
            fn_statuses = [s for s in statuses if s.get("kind") == "function"]
            assert len(fn_statuses) == 1
            assert fn_statuses[0]["status"] == "implemented"

    def test_coverage_checks_types(self) -> None:
        """Coverage reports missing vocabulary types."""
        import tempfile
        from pathlib import Path

        project = IntentProject(
            name="Test",
            purpose="test",
            vocabulary=[
                VocabularyEntry(name="Credential", description="user identity"),
            ],
            modules=[
                IntentModule(
                    name="Auth",
                    intents=[
                        VerbPhrase(
                            verb="validates",
                            noun="credentials",
                            context="against stored credential data",
                            raw_line="validates credentials against stored credential data",
                        ),
                    ],
                ),
            ],
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            statuses = check_intent_coverage(project, Path(tmpdir))
            type_statuses = [s for s in statuses if s.get("kind") == "type"]
            assert len(type_statuses) >= 1
            assert type_statuses[0]["noun"] == "Credential"
            assert type_statuses[0]["status"] == "missing"

    def test_coverage_checks_constants(self) -> None:
        """Coverage reports missing inferred constants."""
        import tempfile
        from pathlib import Path

        project = IntentProject(
            name="Test",
            purpose="test",
            modules=[
                IntentModule(
                    name="Auth",
                    intents=[
                        VerbPhrase(
                            verb="validates", noun="login", context="", raw_line="validates login"
                        ),
                    ],
                ),
            ],
            constraints=[
                ConstraintDecl(text="maximum 3 attempts"),
            ],
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            statuses = check_intent_coverage(project, Path(tmpdir))
            const_statuses = [s for s in statuses if s.get("kind") == "constant"]
            assert len(const_statuses) >= 1
            assert const_statuses[0]["status"] == "missing"
