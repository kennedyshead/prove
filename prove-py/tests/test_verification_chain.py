"""Tests for verification chain propagation (W370/W371)."""

from __future__ import annotations

from tests.helpers import check, check_all, check_warns


class TestVerificationChainW370:
    """W370: public function calls verified function without ensures."""

    def test_unverified_calls_verified_warns(self):
        """Unverified public function calling verified function emits W370."""
        check_warns(
            "transforms helper(n Integer) Integer\n"
            "    ensures result >= 0\n"
            "    explain\n"
            "        check result\n"
            "    from\n"
            "        n\n"
            "\n"
            "transforms caller(n Integer) Integer\n"
            "    from\n"
            "        helper(n)\n",
            "W370",
        )

    def test_verified_calls_verified_no_warning(self):
        """Verified function calling verified function does NOT emit W370."""
        check(
            "transforms helper(n Integer) Integer\n"
            "    ensures result >= 0\n"
            "    explain\n"
            "        check result\n"
            "    from\n"
            "        n\n"
            "\n"
            "transforms caller(n Integer) Integer\n"
            "    ensures result >= 0\n"
            "    explain\n"
            "        propagate result\n"
            "    from\n"
            "        helper(n)\n"
        )

    def test_trusted_calls_verified_no_warning(self):
        """Trusted function calling verified function does NOT emit W370."""
        check(
            "transforms helper(n Integer) Integer\n"
            "    ensures result >= 0\n"
            "    explain\n"
            "        check result\n"
            "    from\n"
            "        n\n"
            "\n"
            "transforms caller(n Integer) Integer\n"
            '    trusted "externally verified"\n'
            "    from\n"
            "        helper(n)\n"
        )

    def test_unverified_calls_unverified_no_warning(self):
        """Unverified function calling only unverified functions: no W370."""
        check(
            "transforms helper(n Integer) Integer\n"
            "    from\n"
            "        n\n"
            "\n"
            "transforms caller(n Integer) Integer\n"
            "    from\n"
            "        helper(n)\n"
        )

    def test_io_verb_calls_verified_no_warning(self):
        """IO verb (inputs) calling verified function: no W370."""
        check(
            "transforms helper(n Integer) Integer\n"
            "    ensures result >= 0\n"
            "    explain\n"
            "        check result\n"
            "    from\n"
            "        n\n"
            "\n"
            "inputs fetch(n Integer) Integer\n"
            "    from\n"
            "        helper(n)\n"
        )

    def test_private_function_no_w370(self):
        """Private function (_prefix) calling verified: no W370 (needs --strict for W371)."""
        diags = check_all(
            "transforms helper(n Integer) Integer\n"
            "    ensures result >= 0\n"
            "    explain\n"
            "        check result\n"
            "    from\n"
            "        n\n"
            "\n"
            "transforms _internal(n Integer) Integer\n"
            "    from\n"
            "        helper(n)\n"
        )
        w370 = [d for d in diags if d.code == "W370"]
        assert not w370, "W370 should not fire for private functions"


class TestVerificationChainW371:
    """W371: strict mode — all functions checked."""

    def test_strict_private_warns_w371(self):
        """With strict mode, private function calling verified emits W371."""
        from prove.checker import Checker
        from prove.lexer import Lexer
        from prove.parser import Parser

        source = (
            "transforms helper(n Integer) Integer\n"
            "    ensures result >= 0\n"
            "    explain\n"
            "        check result\n"
            "    from\n"
            "        n\n"
            "\n"
            "transforms _internal(n Integer) Integer\n"
            "    from\n"
            "        helper(n)\n"
        )
        tokens = Lexer(source, "<test>").lex()
        module = Parser(tokens, "<test>").parse()
        checker = Checker()
        checker._strict = True
        checker.check(module)
        w371 = [d for d in checker.diagnostics if d.code == "W371"]
        assert w371, (
            f"Expected W371 but got: {[f'{d.code}: {d.message}' for d in checker.diagnostics]}"
        )


class TestVerificationStatus:
    """Test that verification status is correctly classified."""

    def test_ensures_marks_verified(self):
        """Function with ensures is classified as verified."""
        from prove.checker import Checker
        from prove.lexer import Lexer
        from prove.parser import Parser

        source = (
            "transforms f(n Integer) Integer\n"
            "    ensures result >= 0\n"
            "    explain\n"
            "        check result\n"
            "    from\n"
            "        n\n"
        )
        tokens = Lexer(source, "<test>").lex()
        module = Parser(tokens, "<test>").parse()
        checker = Checker()
        checker.check(module)
        assert checker._verification_status.get("f") == "verified"

    def test_trusted_marks_trusted(self):
        """Function with trusted is classified as trusted."""
        from prove.checker import Checker
        from prove.lexer import Lexer
        from prove.parser import Parser

        source = 'transforms f(n Integer) Integer\n    trusted "external"\n    from\n        n\n'
        tokens = Lexer(source, "<test>").lex()
        module = Parser(tokens, "<test>").parse()
        checker = Checker()
        checker.check(module)
        assert checker._verification_status.get("f") == "trusted"

    def test_no_contracts_marks_unverified(self):
        """Function without ensures or trusted is unverified."""
        from prove.checker import Checker
        from prove.lexer import Lexer
        from prove.parser import Parser

        source = "transforms f(n Integer) Integer\n    from\n        n\n"
        tokens = Lexer(source, "<test>").lex()
        module = Parser(tokens, "<test>").parse()
        checker = Checker()
        checker.check(module)
        assert checker._verification_status.get("f") == "unverified"
