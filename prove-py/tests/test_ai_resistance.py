"""Tests for AI-resistance features: domain profiles, coherence, refutation challenges."""

from __future__ import annotations

from prove.checker import Checker
from prove.domains import get_domain_profile
from prove.errors import Diagnostic
from prove.lexer import Lexer
from prove.parser import Parser
from tests.helpers import check_warns


def _check_with_coherence(source: str) -> list[Diagnostic]:
    """Parse and check source with coherence enabled, return all diagnostics."""
    tokens = Lexer(source, "<test>").lex()
    module = Parser(tokens, "<test>").parse()
    checker = Checker()
    checker._coherence = True
    checker.check(module)
    return checker.diagnostics


class TestDomainProfiles:
    def test_get_finance_profile(self):
        p = get_domain_profile("finance")
        assert p is not None
        assert p.name == "finance"
        assert "Float" in p.preferred_types
        assert "ensures" in p.required_contracts

    def test_get_safety_profile(self):
        p = get_domain_profile("safety")
        assert p is not None
        assert "requires" in p.required_contracts

    def test_get_unknown_profile(self):
        p = get_domain_profile("aerospace")
        assert p is None

    def test_get_none_profile(self):
        p = get_domain_profile(None)
        assert p is None

    def test_unknown_domain_warns(self):
        check_warns(
            "module M\n"
            '  domain: "aerospace"\n'
            '  narrative: "Test module."\n'
            "\n"
            "transforms id(x Integer) Integer\n"
            "    from\n"
            "        x\n",
            "W340",
        )

    def test_finance_domain_float_warns(self):
        check_warns(
            "module M\n"
            '  domain: "finance"\n'
            '  narrative: "Financial module."\n'
            "\n"
            "transforms total(x Float) Float\n"
            "    from\n"
            "        x\n",
            "W340",
        )

    def test_finance_domain_requires_ensures(self):
        check_warns(
            "module M\n"
            '  domain: "finance"\n'
            '  narrative: "Financial module."\n'
            "\n"
            "transforms total(x Decimal) Decimal\n"
            "    from\n"
            "        x\n",
            "W341",
        )

    def test_finance_domain_requires_near_miss(self):
        check_warns(
            "module M\n"
            '  domain: "finance"\n'
            '  narrative: "Financial module."\n'
            "\n"
            "transforms total(x Decimal) Decimal\n"
            "    ensures total(1.0) == 1.0\n"
            "    from\n"
            "        x\n",
            "W342",
        )

    def test_general_domain_no_warnings(self):
        tokens = Lexer(
            "module M\n"
            '  domain: "general"\n'
            '  narrative: "Test module."\n'
            "\n"
            "transforms id(x Integer) Integer\n"
            "    from\n"
            "        x\n",
            "<test>",
        ).lex()
        module = Parser(tokens, "<test>").parse()
        checker = Checker()
        checker.check(module)
        domain_diags = [d for d in checker.diagnostics if d.code and d.code.startswith("W34")]
        assert not domain_diags

    def test_trusted_functions_skip_domain_check(self):
        tokens = Lexer(
            "module M\n"
            '  domain: "safety"\n'
            '  narrative: "Safety module."\n'
            "\n"
            "transforms id(x Integer) Integer\n"
            '    trusted "bypass"\n'
            "    from\n"
            "        x\n",
            "<test>",
        ).lex()
        module = Parser(tokens, "<test>").parse()
        checker = Checker()
        checker.check(module)
        domain_diags = [d for d in checker.diagnostics if d.code and d.code.startswith("W34")]
        assert not domain_diags


class TestCoherenceChecking:
    def test_coherence_detects_drift(self):
        diags = _check_with_coherence(
            "module M\n"
            '  narrative: "Users authenticate with credentials and receive tokens."\n'
            "\n"
            "transforms calculate_tax(x Integer) Integer\n"
            "    from\n"
            "        x\n"
        )
        coherence_diags = [d for d in diags if d.code == "I340"]
        assert len(coherence_diags) >= 1
        assert "calculate_tax" in coherence_diags[0].message

    def test_coherence_no_drift(self):
        diags = _check_with_coherence(
            "module M\n"
            '  narrative: "Users authenticate with credentials and receive tokens."\n'
            "\n"
            "transforms authenticate(x Integer) Integer\n"
            "    from\n"
            "        x\n"
        )
        coherence_diags = [d for d in diags if d.code == "I340"]
        assert not coherence_diags

    def test_coherence_not_checked_without_flag(self):
        tokens = Lexer(
            "module M\n"
            '  narrative: "Users authenticate."\n'
            "\n"
            "transforms calculate_tax(x Integer) Integer\n"
            "    from\n"
            "        x\n",
            "<test>",
        ).lex()
        module = Parser(tokens, "<test>").parse()
        checker = Checker()
        checker.check(module)
        coherence_diags = [d for d in checker.diagnostics if d.code == "I340"]
        assert not coherence_diags

    def test_coherence_no_narrative_skips(self):
        diags = _check_with_coherence(
            "module M\n\ntransforms foo(x Integer) Integer\n    from\n        x\n"
        )
        coherence_diags = [d for d in diags if d.code == "I340"]
        assert not coherence_diags


class TestRefutationChallenges:
    def test_mutator_generates_challenges(self):
        """Functions with ensures should produce mutations."""
        from prove.mutator import Mutator

        tokens = Lexer(
            "module M\n"
            '  narrative: "Math helpers."\n'
            "\n"
            "transforms double(n Integer) Integer\n"
            "    ensures double(2) == 4\n"
            "    from\n"
            "        n * 2\n",
            "<test>",
        ).lex()
        module = Parser(tokens, "<test>").parse()
        mutator = Mutator(module)
        result = mutator.generate_mutants(max_mutants=5)
        assert len(result.mutants) > 0, "Expected at least one mutant for function with ensures"
