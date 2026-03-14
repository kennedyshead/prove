"""Tests for prove._nl_intent — prose verb mapping and body token extraction."""

from __future__ import annotations

from prove._nl_intent import (
    VERB_SYNONYMS,
    body_tokens,
    extract_nouns,
    implied_verbs,
    normalize_verb,
    prose_overlaps,
)
from prove.ast_nodes import FunctionDef
from prove.lexer import Lexer
from prove.parser import Parser


def _parse_fd(source: str) -> FunctionDef:
    """Parse a single-function source and return the FunctionDef."""
    tokens = Lexer(source, "<test>").lex()
    module = Parser(tokens, "<test>").parse()
    for decl in module.declarations:
        if isinstance(decl, FunctionDef):
            return decl
    raise AssertionError("no FunctionDef in source")


class TestImpliedVerbs:
    def test_validates(self) -> None:
        assert "validates" in implied_verbs("This module validates user credentials.")

    def test_transforms(self) -> None:
        assert "transforms" in implied_verbs("Converts plaintext passwords into hashes.")

    def test_reads(self) -> None:
        assert "reads" in implied_verbs("Fetches password hashes from the store.")

    def test_creates(self) -> None:
        assert "creates" in implied_verbs("Creates session tokens for authenticated users.")

    def test_outputs(self) -> None:
        assert "outputs" in implied_verbs("Sends the result to the client.")

    def test_multiple_verbs(self) -> None:
        text = "This module validates credentials and creates session tokens."
        verbs = implied_verbs(text)
        assert "validates" in verbs
        assert "creates" in verbs

    def test_empty_text(self) -> None:
        assert implied_verbs("") == set()

    def test_no_action_words(self) -> None:
        assert implied_verbs("A module for handling data.") == set()

    def test_checks_synonym(self) -> None:
        assert "validates" in implied_verbs("Checks that the input is valid.")

    def test_reads_synonym_query(self) -> None:
        assert "reads" in implied_verbs("Queries the database for records.")

    def test_case_insensitive(self) -> None:
        assert "validates" in implied_verbs("VALIDATES user input.")


class TestProseOverlaps:
    def test_direct_match(self) -> None:
        assert prose_overlaps("hashes the password", {"hash", "password"})

    def test_no_match(self) -> None:
        assert not prose_overlaps("subtracts b from a", {"add", "increment"})

    def test_stem_match(self) -> None:
        # "hashing" has prefix "hash" (4 chars) matching token "hash"
        assert prose_overlaps("performs hashing", {"hash"})

    def test_case_insensitive(self) -> None:
        assert prose_overlaps("Validates the Input", {"validates"})

    def test_empty_tokens(self) -> None:
        assert not prose_overlaps("some text here", set())

    def test_empty_prose(self) -> None:
        assert not prose_overlaps("", {"token"})

    def test_short_words_no_stem(self) -> None:
        # Words under 4 chars don't trigger stem matching
        assert not prose_overlaps("do it", {"does"})


class TestBodyTokens:
    def test_extracts_param_names(self) -> None:
        fd = _parse_fd(
            "transforms add(a Integer, b Integer) Integer\n"
            "from\n"
            "    a + b\n"
        )
        tokens = body_tokens(fd)
        assert "a" in tokens
        assert "b" in tokens

    def test_extracts_called_functions(self) -> None:
        fd = _parse_fd(
            "transforms double(n Integer) Integer\n"
            "from\n"
            "    add(n, n)\n"
        )
        tokens = body_tokens(fd)
        assert "n" in tokens
        assert "add" in tokens

    def test_empty_body(self) -> None:
        fd = _parse_fd(
            "transforms identity(x Integer) Integer\n"
            "from\n"
            "    x\n"
        )
        tokens = body_tokens(fd)
        # At minimum, param name is present
        assert "x" in tokens

    def test_no_params(self) -> None:
        fd = _parse_fd(
            "creates zero() Integer\n"
            "from\n"
            "    0\n"
        )
        tokens = body_tokens(fd)
        # No params, no calls — may be empty or contain literal-related names
        assert isinstance(tokens, set)


class TestNormalizeVerb:
    """Tests for normalize_verb() canonical lookup."""

    def test_canonical_verbs_return_themselves(self) -> None:
        for verb in VERB_SYNONYMS:
            assert normalize_verb(verb) == verb

    def test_singular_forms(self) -> None:
        assert normalize_verb("transform") == "transforms"
        assert normalize_verb("validate") == "validates"
        assert normalize_verb("read") == "reads"
        assert normalize_verb("create") == "creates"
        assert normalize_verb("match") == "matches"
        assert normalize_verb("output") == "outputs"
        assert normalize_verb("input") == "inputs"
        assert normalize_verb("listen") == "listens"
        assert normalize_verb("detach") == "detached"
        assert normalize_verb("attach") == "attached"
        assert normalize_verb("stream") == "streams"

    def test_common_synonyms(self) -> None:
        assert normalize_verb("convert") == "transforms"
        assert normalize_verb("check") == "validates"
        assert normalize_verb("fetch") == "reads"
        assert normalize_verb("build") == "creates"
        assert normalize_verb("compare") == "matches"
        assert normalize_verb("write") == "outputs"
        assert normalize_verb("receive") == "inputs"
        assert normalize_verb("monitor") == "listens"
        assert normalize_verb("spawn") == "detached"
        assert normalize_verb("await") == "attached"
        assert normalize_verb("poll") == "streams"

    def test_unrecognized_returns_none(self) -> None:
        assert normalize_verb("foobar") is None
        assert normalize_verb("") is None

    def test_case_insensitive(self) -> None:
        assert normalize_verb("TRANSFORM") == "transforms"
        assert normalize_verb("Convert") == "transforms"


class TestImpliedVerbsSynonyms:
    """Synonym-specific tests for implied_verbs()."""

    def test_singular_form_in_prose(self) -> None:
        assert "transforms" in implied_verbs("transform the data")

    def test_synonym_in_prose(self) -> None:
        assert "transforms" in implied_verbs("convert the input to output")
        assert "validates" in implied_verbs("check user credentials")
        assert "reads" in implied_verbs("fetch records from database")
        assert "creates" in implied_verbs("build a new session")

    def test_all_synonym_forms(self) -> None:
        """Every word in VERB_SYNONYMS should be recognized by implied_verbs."""
        for verb, synonyms in VERB_SYNONYMS.items():
            for syn in synonyms:
                result = implied_verbs(syn)
                assert verb in result, f"'{syn}' should imply '{verb}'"


class TestExtractNounsSynonyms:
    """Synonym-specific tests for extract_nouns()."""

    def test_filters_verb_synonyms(self) -> None:
        nouns = extract_nouns("convert the data into results")
        assert "convert" not in nouns
        assert "data" in nouns
        assert "results" in nouns

    def test_filters_singular_verb_forms(self) -> None:
        nouns = extract_nouns("transform credentials and validate them")
        assert "transform" not in nouns
        assert "validate" not in nouns
        assert "credentials" in nouns

    def test_preserves_domain_nouns(self) -> None:
        nouns = extract_nouns("hash the password using argon2")
        assert "password" in nouns
        assert "argon2" in nouns
