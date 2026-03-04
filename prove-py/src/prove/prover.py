"""Structural verification for the Prove language.

Checks explain blocks for completeness and consistency:
- E391: duplicate entry names (error)
- E392: explain entries < ensures count (error)
- E393: believe without ensures (error)
- W321: explain text doesn't reference function concepts
- W322: duplicate near-miss inputs
- W323: ensures without explain (warning, replaces E390)
- W324: ensures without requires
- W325: explain without ensures (warning)

Note: E366 (recursive function missing terminates) and W326 (recursion depth)
are now handled by the Checker, which has access to the symbol table for
verb-aware function resolution.
"""

from __future__ import annotations

from prove.ast_nodes import FunctionDef, IntegerLit, NearMiss
from prove.errors import (
    DIAGNOSTIC_DOCS,
    Diagnostic,
    DiagnosticLabel,
    Severity,
)
from prove.source import Span


class ProofVerifier:
    """Verify structural obligations for functions."""

    def __init__(self) -> None:
        self.diagnostics: list[Diagnostic] = []

    def verify(self, fd: FunctionDef) -> None:
        """Run all explain verification checks on a function."""
        self._check_ensures_explain(fd)
        self._check_entry_uniqueness(fd)
        self._check_entry_coverage(fd)
        self._check_explain_references(fd)
        self._check_near_miss_duplicates(fd)
        self._check_believe_without_ensures(fd)
        self._check_ensures_without_requires(fd)
        self._check_explain_without_ensures(fd)

    def _error(self, code: str, message: str, span: Span) -> None:
        self.diagnostics.append(Diagnostic(
            severity=Severity.ERROR,
            code=code,
            message=message,
            labels=[DiagnosticLabel(span=span, message="")],
            doc_url=DIAGNOSTIC_DOCS.get(code),
        ))

    def _warning(self, code: str, message: str, span: Span) -> None:
        self.diagnostics.append(Diagnostic(
            severity=Severity.WARNING,
            code=code,
            message=message,
            labels=[DiagnosticLabel(span=span, message="")],
            doc_url=DIAGNOSTIC_DOCS.get(code),
        ))

    def _check_ensures_explain(self, fd: FunctionDef) -> None:
        """W323: ensures without explain block (warning, not error)."""
        if fd.trusted is not None:
            return  # trusted functions opt out of verification
        if fd.ensures and not fd.explain:
            self.diagnostics.append(Diagnostic(
                severity=Severity.WARNING,
                code="W323",
                message=(
                    f"Function '{fd.name}' has `ensures` but no `explain`. "
                    f"Document how each step satisfies the contract."
                ),
                labels=[DiagnosticLabel(span=fd.span, message="")],
                notes=[
                    "Add an `explain` block with entries describing how "
                    "the implementation satisfies each postcondition.",
                ],
                doc_url=DIAGNOSTIC_DOCS.get("W323"),
            ))

    def _check_entry_uniqueness(self, fd: FunctionDef) -> None:
        """E391: duplicate named entry names."""
        if fd.explain is None:
            return
        seen: set[str] = set()
        for entry in fd.explain.entries:
            if entry.name is None:
                continue  # prose entries have no name to clash
            if entry.name in seen:
                self._error(
                    "E391",
                    f"duplicate explain entry name '{entry.name}'",
                    entry.span,
                )
            seen.add(entry.name)

    def _check_entry_coverage(self, fd: FunctionDef) -> None:
        """E392: named entries must cover ensures count."""
        if fd.explain is None or not fd.ensures:
            return
        named = [e for e in fd.explain.entries if e.name is not None]
        if not named:
            return  # prose-only explain blocks don't need 1:1 coverage
        if len(named) < len(fd.ensures):
            self._error(
                "E392",
                f"explain has {len(named)} named entry/entries "
                f"but {len(fd.ensures)} ensures clause(s)",
                fd.explain.span,
            )

    def _check_explain_references(self, fd: FunctionDef) -> None:
        """W321: explain text should reference function concepts."""
        if fd.explain is None:
            return
        # Collect relevant names: function name, param names
        concepts = {fd.name}
        for p in fd.params:
            concepts.add(p.name)
        concepts.add("result")

        for entry in fd.explain.entries:
            # Structured conditions reference params directly — skip text check
            if entry.condition is not None:
                continue
            # Prose entries are documentation — skip text check
            if entry.name is None:
                continue
            text_lower = entry.text.lower()
            if not any(c.lower() in text_lower for c in concepts):
                self.diagnostics.append(Diagnostic(
                    severity=Severity.WARNING,
                    code="W321",
                    message=(
                        f"explain entry '{entry.name}' doesn't reference "
                        f"any function concepts "
                        f"({', '.join(sorted(concepts))})"
                    ),
                    labels=[DiagnosticLabel(span=entry.span, message="")],
                    notes=[
                        "Mention at least one of the listed concepts "
                        "(parameter names, function name, or `result`) "
                        "so the explanation ties back to the code.",
                    ],
                    doc_url=DIAGNOSTIC_DOCS.get("W321"),
                ))

    def _check_near_miss_duplicates(self, fd: FunctionDef) -> None:
        """W322: duplicate near-miss inputs."""
        seen: list[NearMiss] = []
        for nm in fd.near_misses:
            for prev in seen:
                if self._exprs_equal(nm.input, prev.input):
                    self.diagnostics.append(Diagnostic(
                        severity=Severity.WARNING,
                        code="W322",
                        message=(
                            f"duplicate near-miss input "
                            f"(first defined at line "
                            f"{prev.span.start_line})"
                        ),
                        labels=[DiagnosticLabel(
                            span=nm.span, message="",
                        )],
                        notes=[
                            "Remove the duplicate or change "
                            "the input to test a different edge case.",
                        ],
                        doc_url=DIAGNOSTIC_DOCS.get("W322"),
                    ))
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
            self.diagnostics.append(Diagnostic(
                severity=Severity.WARNING,
                code="W324",
                message=(
                    f"function '{fd.name}' has ensures but no requires"
                ),
                labels=[DiagnosticLabel(span=fd.span, message="")],
                notes=[
                    "Add a `requires` clause to specify input "
                    "constraints. The compiler uses requires/ensures "
                    "pairs to reason about correctness.",
                ],
                doc_url=DIAGNOSTIC_DOCS.get("W324"),
            ))

    def _check_explain_without_ensures(self, fd: FunctionDef) -> None:
        """W325: explain without ensures."""
        if fd.trusted is not None:
            return  # trusted functions opt out of verification
        if fd.explain and not fd.ensures:
            self.diagnostics.append(Diagnostic(
                severity=Severity.WARNING,
                code="W325",
                message=(
                    f"function '{fd.name}' has explain but no ensures"
                ),
                labels=[DiagnosticLabel(span=fd.span, message="")],
                notes=[
                    "Add `ensures` clauses so the `explain` block has "
                    "contracts to document. Without postconditions, "
                    "the explanation is unverifiable.",
                ],
                doc_url=DIAGNOSTIC_DOCS.get("W325"),
            ))

    @staticmethod
    def _exprs_equal(a, b) -> bool:
        """Simple structural equality check for expressions."""
        if type(a) is not type(b):
            return False
        if isinstance(a, IntegerLit):
            return a.value == b.value
        return False
