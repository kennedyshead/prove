"""Format a Prove project via the Python bootstrap cli.

This script is embedded as a comptime string in format.prv and executed via
PyRun_SimpleString.
"""

from __future__ import annotations

# pylint: disable=invalid-name

path: str = ""
status: bool = False
stdin: bool = False
md: bool = False

if __name__ == "__main__":
    from prove._format_runner import run_format

    raise SystemExit(run_format(path, status=status, use_stdin=stdin, md=md))
