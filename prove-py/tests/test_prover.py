"""Tests for the proof verification module."""

from prove.ast_nodes import FunctionDef, IntegerLit, ProofBlock, ProofObligation
from prove.prover import ProofVerifier
from prove.source import Span
from tests.helpers import check, check_fails, check_warns

_DUMMY = Span("<test>", 1, 1, 1, 1)


def _make_fd(**kwargs) -> FunctionDef:
    """Create a minimal FunctionDef for testing."""
    defaults = dict(
        verb="transforms", name="f", params=[], return_type=None,
        can_fail=False, ensures=[], requires=[], proof=None,
        explain=[], terminates=None, trusted=None, binary=False,
        why_not=[], chosen=None, near_misses=[], know=[], assume=[],
        believe=[], intent=None, satisfies=[], body=[], doc_comment=None,
        span=_DUMMY,
    )
    defaults.update(kwargs)
    return FunctionDef(**defaults)


class TestProofVerification:
    """Test proof verification errors and warnings."""

    def test_ensures_without_explain_error(self):
        check_fails(
            "transforms add(a Integer, b Integer) Integer\n"
            "    ensures result == a + b\n"
            "    from\n"
            "        a + b\n",
            "E390",
        )

    def test_ensures_with_explain_no_e390(self):
        check(
            "transforms add(a Integer, b Integer) Integer\n"
            "    ensures result == a + b\n"
            "    explain\n"
            "        sum a and b\n"
            "    from\n"
            "        a + b\n"
        )

    def test_duplicate_obligation_error_direct(self):
        """Test duplicate obligation detection using ProofVerifier directly."""
        obl1 = ProofObligation(name="same", text="first", condition=None, span=_DUMMY)
        obl2 = ProofObligation(name="same", text="second", condition=None, span=_DUMMY)
        proof = ProofBlock(obligations=[obl1, obl2], span=_DUMMY)
        fd = _make_fd(
            ensures=[IntegerLit(value="1", span=_DUMMY)],
            explain=["some step"],
            proof=proof,
        )
        verifier = ProofVerifier()
        verifier.verify(fd)
        codes = [d.code for d in verifier.diagnostics]
        assert "E391" in codes

    def test_obligation_coverage_error_direct(self):
        """Test obligation coverage using ProofVerifier directly."""
        obl = ProofObligation(name="one", text="covers result", condition=None, span=_DUMMY)
        proof = ProofBlock(obligations=[obl], span=_DUMMY)
        fd = _make_fd(
            ensures=[
                IntegerLit(value="1", span=_DUMMY),
                IntegerLit(value="2", span=_DUMMY),
            ],
            explain=["step one", "step two"],
            proof=proof,
        )
        verifier = ProofVerifier()
        verifier.verify(fd)
        codes = [d.code for d in verifier.diagnostics]
        assert "E392" in codes

    def test_proof_text_no_references_warning_direct(self):
        """Test proof text reference checking using ProofVerifier directly."""
        obl = ProofObligation(name="vague", text="xyz qrs tuv", condition=None, span=_DUMMY)
        proof = ProofBlock(obligations=[obl], span=_DUMMY)
        fd = _make_fd(
            name="compute",
            ensures=[IntegerLit(value="1", span=_DUMMY)],
            explain=["some step"],
            proof=proof,
        )
        verifier = ProofVerifier()
        verifier.verify(fd)
        codes = [d.code for d in verifier.diagnostics]
        assert "W321" in codes

    def test_believe_without_ensures_error(self):
        check_fails(
            "transforms abs_val(n Integer) Integer\n"
            "    believe: result >= 0\n"
            "    from\n"
            "        match n >= 0\n"
            "            true => n\n"
            "            false => 0 - n\n",
            "E393",
        )

    def test_believe_with_ensures_no_e393(self):
        """E393 should not fire when ensures is present."""
        from prove.checker import Checker
        from prove.lexer import Lexer
        from prove.parser import Parser

        source = (
            "transforms abs_val(n Integer) Integer\n"
            "    ensures result >= 0\n"
            "    believe: result >= 0\n"
            "    explain\n"
            "        negate if negative\n"
            "    from\n"
            "        match n >= 0\n"
            "            true => n\n"
            "            false => 0 - n\n"
        )
        tokens = Lexer(source, "test.prv").lex()
        module = Parser(tokens, "test.prv").parse()
        checker = Checker()
        checker.check(module)
        e393 = [d for d in checker.diagnostics if d.code == "E393"]
        assert not e393, "should not error E393 when ensures is present"


    def test_ensures_without_requires_warning(self):
        check_warns(
            "transforms add(a Integer, b Integer) Integer\n"
            "    ensures result == a + b\n"
            "    explain\n"
            "        sum a and b\n"
            "    from\n"
            "        a + b\n",
            "W324",
        )

    def test_ensures_with_requires_no_w324(self):
        check(
            "transforms safe_div(a Integer, b Integer) Integer\n"
            "    requires b != 0\n"
            "    ensures result == a / b\n"
            "    explain\n"
            "        divide a by b\n"
            "    from\n"
            "        a / b\n"
        )


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
