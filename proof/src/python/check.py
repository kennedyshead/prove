"""Check a Prove project via the Python bootstrap cli.

This script is embedded as a comptime string in check.prv and executed via
PyRun_SimpleString.
"""

from __future__ import annotations
from typing import cast
import warnings

warnings.filterwarnings(
    "ignore", message="nltk.app.wordfreq not loaded", category=UserWarning
)
# pylint: disable=invalid-name

path: str = cast(str, globals().get("path", "."))
md: bool = cast(bool, globals().get("md", False))
strict: bool = cast(bool, globals().get("strict", False))
no_coherence: bool = cast(bool, globals().get("no_coherence", False))
no_challenges: bool = cast(bool, globals().get("no_challenges", False))
no_status: bool = cast(bool, globals().get("no_status", False))
no_intent: bool = cast(bool, globals().get("no_intent", False))
nlp_status: bool = cast(bool, globals().get("nlp_status", False))


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
