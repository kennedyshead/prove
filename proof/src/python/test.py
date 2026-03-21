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

path: str = cast(str, globals().get("path", ""))
property_rounds: int = cast(int, globals().get("property_rounds", ""))

if __name__ == "__main__":
    from prove._test_runner import run_test

    raise SystemExit(run_test(path, property_rounds=property_rounds))
