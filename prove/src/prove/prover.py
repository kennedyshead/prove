"""Structural proof verification for the Prove language.

Checks proof blocks for completeness and consistency:
- E390: ensures without proof block (error)
- E391: duplicate obligation names (error)
- E392: proof obligations < ensures count (error)
- E393: believe without ensures (error)
- W321: proof text doesn't reference function concepts
- W322: duplicate near-miss inputs
- W324: ensures without requires
"""

from __future__ import annotations

from prove.ast_nodes import FunctionDef, IntegerLit, NearMiss
from prove.errors import Diagnostic, DiagnosticLabel, Severity
from prove.source import Span


class ProofVerifier:
    """Verify structural proof obligations for functions."""

    def __init__(self) -> None:
        self.diagnostics: list[Diagnostic] = []

    def verify(self, fd: FunctionDef) -> None:
        """Run all proof checks on a function."""
        self._check_ensures_proof(fd)
        self._check_obligation_uniqueness(fd)
        self._check_obligation_coverage(fd)
        self._check_proof_references(fd)
        self._check_near_miss_duplicates(fd)
        self._check_believe_without_ensures(fd)
        self._check_ensures_without_requires(fd)

    def _error(self, code: str, message: str, span: Span) -> None:
        self.diagnostics.append(Diagnostic(
            severity=Severity.ERROR,
            code=code,
            message=message,
            labels=[DiagnosticLabel(span=span, message="")],
        ))

    def _warning(self, code: str, message: str, span: Span) -> None:
        self.diagnostics.append(Diagnostic(
            severity=Severity.WARNING,
            code=code,
            message=message,
            labels=[DiagnosticLabel(span=span, message="")],
        ))

    def _check_ensures_proof(self, fd: FunctionDef) -> None:
        """E390: ensures without proof block."""
        if fd.ensures and fd.proof is None:
            self._error(
                "E390",
                f"function '{fd.name}' has ensures but no proof block",
                fd.span,
            )

    def _check_obligation_uniqueness(self, fd: FunctionDef) -> None:
        """E391: duplicate obligation names."""
        if fd.proof is None:
            return
        seen: set[str] = set()
        for obl in fd.proof.obligations:
            if obl.name in seen:
                self._error(
                    "E391",
                    f"duplicate proof obligation name '{obl.name}'",
                    obl.span,
                )
            seen.add(obl.name)

    def _check_obligation_coverage(self, fd: FunctionDef) -> None:
        """E392: obligations must cover ensures count."""
        if fd.proof is None or not fd.ensures:
            return
        if len(fd.proof.obligations) < len(fd.ensures):
            self._error(
                "E392",
                f"proof has {len(fd.proof.obligations)} obligation(s) "
                f"but {len(fd.ensures)} ensures clause(s)",
                fd.proof.span,
            )

    def _check_proof_references(self, fd: FunctionDef) -> None:
        """W321: proof text should reference function concepts."""
        if fd.proof is None:
            return
        # Collect relevant names: function name, param names
        concepts = {fd.name}
        for p in fd.params:
            concepts.add(p.name)
        concepts.add("result")

        for obl in fd.proof.obligations:
            text_lower = obl.text.lower()
            if not any(c.lower() in text_lower for c in concepts):
                self._warning(
                    "W321",
                    f"proof obligation '{obl.name}' doesn't reference "
                    f"any function concepts ({', '.join(sorted(concepts))})",
                    obl.span,
                )

    def _check_near_miss_duplicates(self, fd: FunctionDef) -> None:
        """W322: duplicate near-miss inputs."""
        seen: list[NearMiss] = []
        for nm in fd.near_misses:
            for prev in seen:
                if self._exprs_equal(nm.input, prev.input):
                    self._warning(
                        "W322",
                        "duplicate near-miss input",
                        nm.span,
                    )
                    break
            seen.append(nm)

    def _check_believe_without_ensures(self, fd: FunctionDef) -> None:
        """E393: believe without ensures."""
        if fd.believe and not fd.ensures:
            self._error(
                "E393",
                f"function '{fd.name}' has believe but no ensures",
                fd.span,
            )

    def _check_ensures_without_requires(self, fd: FunctionDef) -> None:
        """W324: ensures without requires."""
        if fd.ensures and not fd.requires:
            self._warning(
                "W324",
                f"function '{fd.name}' has ensures but no requires",
                fd.span,
            )

    @staticmethod
    def _exprs_equal(a, b) -> bool:
        """Simple structural equality check for expressions."""
        if type(a) is not type(b):
            return False
        if isinstance(a, IntegerLit):
            return a.value == b.value
        return False
