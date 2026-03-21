"""Format a Prove project via the Python bootstrap cli.

This script is embedded as a comptime string in format.prv and executed via
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
status: bool = cast(bool, globals().get("status", False))
stdin: bool = cast(bool, globals().get("stdin", False))
md: bool = cast(bool, globals().get("md", False))

if __name__ == "__main__":
    from prove._format_runner import run_format

    raise SystemExit(run_format(path, status=status, use_stdin=stdin, md=md))
