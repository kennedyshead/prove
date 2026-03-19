"""Check a Prove project via the Python bootstrap cli.

This script is embedded as a comptime string in check.prv and executed via
PyRun_SimpleString.
"""

from __future__ import annotations

# pylint: disable=invalid-name

path: str = ""
md: bool = False  # Also check ```prove blocks in .md files.
strict: bool = False  # Treat warnings as errors.
no_coherence: bool = False  # Skip vocabulary consistency check.
no_challenges: bool = False  # Skip refutation challenges.in
no_status: bool = False  # Skip module completeness report.
no_intent: bool = False  # Skip intent coverage check.
nlp_status: bool = False  # Report NLP backend and store availability.


if __name__ == "__main__":
    from prove._check_runner import run_check

    raise SystemExit(
        run_check(
            path,
            md=md,
            strict=strict,
            no_coherence=no_coherence,
            no_challenges=no_challenges,
            no_status=no_status,
            no_intent=no_intent,
            nlp_status=nlp_status,
        )
    )
