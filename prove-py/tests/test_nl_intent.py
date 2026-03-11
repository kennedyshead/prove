"""Tests for prove._nl_intent — prose verb mapping and body token extraction."""

from __future__ import annotations

from prove._nl_intent import implied_verbs, prose_overlaps


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
