"""Check a Prove project via the Python bootstrap cli.

This script is embedded as a comptime string in check.prv and executed via
PyRun_SimpleString. The caller (py_set_string/py_set_bool wrappers) must
inject the following variables into __main__ before running this script:

  path      (str)  — project directory
  debug     (bool) — enable debug build
  no_mutate (bool) — skip mutation testing
"""

from __future__ import annotations

from pathlib import Path

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
    from prove.config import load_config

    project_dir: Path = Path(path)
    config = load_config(project_dir / "prove.toml")

    result: int = run_check(
        path,
        md=md,
        strict=strict,
        no_coherence=no_coherence,
        no_challenges=no_challenges,
        no_status=no_status,
        no_intent=no_intent,
        nlp_status=nlp_status,
    )

    raise SystemExit(result)
