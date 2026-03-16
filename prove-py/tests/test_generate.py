"""Tests for stub generation (_generate.py) and related _nl_intent additions."""

from __future__ import annotations

from prove._generate import generate_module, generate_stub_function
from prove._nl_intent import (
    FunctionStub,
    _extract_nouns_fallback,
    extract_nouns,
    implied_functions,
    pair_verbs_nouns,
)


class TestExtractNouns:
    def test_basic_extraction(self) -> None:
        nouns = _extract_nouns_fallback("validates user credentials against a stored database")
        assert "user" in nouns
        assert "credential" in nouns  # normalized from "credentials"
        assert "stor" in nouns  # normalized from "stored" (-ed)
        assert "database" in nouns

    def test_stops_excluded(self) -> None:
        nouns = _extract_nouns_fallback("the module is for all users")
        assert "the" not in nouns
        assert "module" not in nouns
        assert "for" not in nouns
        assert "user" in nouns  # normalized from "users"

    def test_verbs_excluded(self) -> None:
        nouns = _extract_nouns_fallback("validates and transforms passwords")
        assert "password" in nouns  # normalized from "passwords"
        # "validates" and "transforms" match verb stems
        assert "validates" not in nouns
        assert "transforms" not in nouns

    def test_short_words_excluded(self) -> None:
        nouns = _extract_nouns_fallback("id of an ip address")
        assert "id" not in nouns
        assert "ip" not in nouns
        assert "address" in nouns

    def test_preserves_order(self) -> None:
        nouns = extract_nouns("session tokens and password hashes")
        assert nouns.index("session") < nouns.index("token")  # normalized
        assert nouns.index("password") < nouns.index("hash")  # normalized


class TestPairVerbsNouns:
    def test_basic_pairing(self) -> None:
        stubs = pair_verbs_nouns({"validates"}, ["credential"])
        assert len(stubs) == 1
        assert stubs[0].verb == "validates"
        assert stubs[0].name == "credential"

    def test_multiple_verbs_nouns(self) -> None:
        stubs = pair_verbs_nouns({"validates", "creates"}, ["session", "token"])
        assert len(stubs) == 4  # 2 verbs * 2 nouns

    def test_sorted_by_confidence(self) -> None:
        stubs = pair_verbs_nouns({"validates"}, ["a", "b", "c"])
        confs = [s.confidence for s in stubs]
        assert confs == sorted(confs, reverse=True)

    def test_return_type_heuristic(self) -> None:
        stubs = pair_verbs_nouns({"validates"}, ["input"])
        assert stubs[0].return_type == "Boolean"

        stubs = pair_verbs_nouns({"outputs"}, ["result"])
        assert stubs[0].return_type == "Unit"


class TestGenerateModule:
    def test_basic_module(self) -> None:
        stubs = [
            FunctionStub(verb="validates", name="credential",
                         params=[("user", "String")], return_type="Boolean"),
        ]
        result = generate_module("Auth", "Validates user credentials.", stubs)
        assert "module Auth" in result
        assert 'narrative: """Validates user credentials."""' in result
        assert "validates credential(user String) Boolean" in result
        assert "todo" in result

    def test_low_confidence_as_comment(self) -> None:
        stubs = [
            FunctionStub(verb="outputs", name="audit", confidence=0.1),
        ]
        result = generate_module("Log", "Logs audit events.", stubs)
        assert "// Possible: outputs audit(...)" in result
        assert "from" not in result

    def test_domain_and_imports(self) -> None:
        stubs = [FunctionStub(verb="creates", name="session")]
        result = generate_module(
            "Auth", "Creates sessions.", stubs,
            domain="Security", imports=["Hash"]
        )
        assert "domain: Security" in result
        assert "use Hash" in result

    def test_unit_return_omitted(self) -> None:
        stubs = [
            FunctionStub(verb="outputs", name="data",
                         params=[("value", "String")], return_type="Unit"),
        ]
        result = generate_module("IO", "Outputs data.", stubs)
        assert "outputs data(value String)" in result
        assert "Unit" not in result


class TestGenerateStubFunction:
    def test_single_stub(self) -> None:
        stub = FunctionStub(
            verb="transforms", name="password",
            params=[("plaintext", "String")], return_type="String",
        )
        result = generate_stub_function(stub)
        assert "/// TODO: document password" in result
        assert "transforms password(plaintext String) String" in result
        assert "from" in result
        assert "  todo" in result


class TestImpliedFunctions:
    def test_no_index_returns_empty(self) -> None:
        assert implied_functions("hash a byte array") == []

    def test_basic_lookup(self) -> None:
        index = {
            "hash": [
                {"module": "Hash", "name": "sha256", "verb": "creates",
                 "doc": "Hash a byte array to SHA-256 digest"},
            ],
            "byte": [
                {"module": "Hash", "name": "sha256", "verb": "creates",
                 "doc": "Hash a byte array to SHA-256 digest"},
            ],
        }
        results = implied_functions("hash a byte array", index)
        assert len(results) == 1
        assert results[0]["module"] == "Hash"
        assert results[0]["name"] == "sha256"
        assert results[0]["score"] > 0

    def test_multiple_matches_sorted_by_score(self) -> None:
        index = {
            "hash": [
                {"module": "Hash", "name": "sha256", "verb": "creates",
                 "doc": "Hash a byte array to SHA-256 digest"},
                {"module": "Hash", "name": "sha512", "verb": "creates",
                 "doc": "Hash a byte array to SHA-512 digest"},
            ],
            "split": [
                {"module": "Text", "name": "split", "verb": "transforms",
                 "doc": "Split a string by a separator"},
            ],
        }
        results = implied_functions("hash data", index)
        scores = [r["score"] for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_empty_text(self) -> None:
        index = {"hash": [{"module": "H", "name": "x", "verb": "creates", "doc": "hash"}]}
        assert implied_functions("", index) == []
