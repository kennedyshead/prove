"""Tests for the proof verification module."""

from prove.ast_nodes import FunctionDef, IntegerLit, ProofBlock, ProofObligation
from prove.prover import ProofVerifier
from prove.source import Span
from tests.helpers import check, check_warns

_DUMMY = Span("<test>", 1, 1, 1, 1)


def _make_fd(**kwargs) -> FunctionDef:
    """Create a minimal FunctionDef for testing."""
    defaults = dict(
        verb="transforms", name="f", params=[], return_type=None,
        can_fail=False, ensures=[], requires=[], proof=None,
        why_not=[], chosen=None, near_misses=[], know=[], assume=[],
        believe=[], intent=None, satisfies=[], body=[], doc_comment=None,
        span=_DUMMY,
    )
    defaults.update(kwargs)
    return FunctionDef(**defaults)


class TestProofVerification:
    """Test proof verification errors and warnings."""

    def test_ensures_without_proof_warning(self):
        check_warns(
            "transforms add(a Integer, b Integer) Integer\n"
            "    ensures result == a + b\n"
            "    from\n"
            "        a + b\n",
            "W390",
        )

    def test_ensures_with_proof_no_warning(self):
        check(
            "transforms add(a Integer, b Integer) Integer\n"
            "    ensures result == a + b\n"
            "    proof\n"
            "        correctness: \"result is sum of a and b\"\n"
            "    from\n"
            "        a + b\n"
        )

    def test_duplicate_obligation_error_direct(self):
        """Test duplicate obligation detection using ProofVerifier directly."""
        obl1 = ProofObligation(name="same", text="first", span=_DUMMY)
        obl2 = ProofObligation(name="same", text="second", span=_DUMMY)
        proof = ProofBlock(obligations=[obl1, obl2], span=_DUMMY)
        fd = _make_fd(
            ensures=[IntegerLit(value="1", span=_DUMMY)],
            proof=proof,
        )
        verifier = ProofVerifier()
        verifier.verify(fd)
        codes = [d.code for d in verifier.diagnostics]
        assert "E391" in codes

    def test_obligation_coverage_warning_direct(self):
        """Test obligation coverage using ProofVerifier directly."""
        obl = ProofObligation(name="one", text="covers result", span=_DUMMY)
        proof = ProofBlock(obligations=[obl], span=_DUMMY)
        fd = _make_fd(
            ensures=[
                IntegerLit(value="1", span=_DUMMY),
                IntegerLit(value="2", span=_DUMMY),
            ],
            proof=proof,
        )
        verifier = ProofVerifier()
        verifier.verify(fd)
        codes = [d.code for d in verifier.diagnostics]
        assert "W320" in codes

    def test_proof_text_no_references_warning_direct(self):
        """Test proof text reference checking using ProofVerifier directly."""
        obl = ProofObligation(name="vague", text="xyz qrs tuv", span=_DUMMY)
        proof = ProofBlock(obligations=[obl], span=_DUMMY)
        fd = _make_fd(
            name="compute",
            ensures=[IntegerLit(value="1", span=_DUMMY)],
            proof=proof,
        )
        verifier = ProofVerifier()
        verifier.verify(fd)
        codes = [d.code for d in verifier.diagnostics]
        assert "W321" in codes

    def test_believe_without_ensures_warning(self):
        check_warns(
            "transforms abs_val(n Integer) Integer\n"
            "    believe: result >= 0\n"
            "    from\n"
            "        if n >= 0\n"
            "            n\n"
            "        else\n"
            "            0 - n\n",
            "W323",
        )

    def test_believe_with_ensures_no_w323(self):
        """W323 should not fire when ensures is present."""
        from prove.checker import Checker
        from prove.lexer import Lexer
        from prove.parser import Parser

        source = (
            "transforms abs_val(n Integer) Integer\n"
            "    ensures result >= 0\n"
            "    believe: result >= 0\n"
            "    from\n"
            "        if n >= 0\n"
            "            n\n"
            "        else\n"
            "            0 - n\n"
        )
        tokens = Lexer(source, "test.prv").lex()
        module = Parser(tokens, "test.prv").parse()
        checker = Checker()
        checker.check(module)
        w323 = [d for d in checker.diagnostics if d.code == "W323"]
        assert not w323, "should not warn W323 when ensures is present"


class TestAssumeAssertion:
    """Test that assume expressions emit runtime assertions."""

    def test_assume_emits_assertion(self):
        from prove.c_emitter import CEmitter
        from prove.checker import Checker
        from prove.lexer import Lexer
        from prove.parser import Parser

        source = (
            "transforms safe(x Integer) Integer\n"
            "    assume: x > 0\n"
            "    from\n"
            "        x\n"
        )
        tokens = Lexer(source, "<test>").lex()
        module = Parser(tokens, "<test>").parse()
        checker = Checker()
        symbols = checker.check(module)
        emitter = CEmitter(module, symbols)
        c_code = emitter.emit()
        assert "prove_panic" in c_code
        assert "assumption violated" in c_code
