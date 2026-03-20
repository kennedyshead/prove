"""Generate function stubs from narrative or intent.

This script is embedded as a comptime string in generate.prv and executed via
PyRun_SimpleString.
"""

from __future__ import annotations

from typing import cast

# pylint: disable=invalid-name

path: str = cast(str, globals().get("path", ""))
update: bool = cast(bool, globals().get("update", False))
dry_run: bool = cast(bool, globals().get("dry_run", False))

if __name__ == "__main__":
    from pathlib import Path

    from prove.cli import _generate_from_intent, _generate_from_narrative

    target = Path(path)
    if target.suffix == ".intent":
        _generate_from_intent(target, dry_run)
    elif target.suffix == ".prv":
        _generate_from_narrative(target, update, dry_run)
    else:
        print("error: expected .prv or .intent file")
        raise SystemExit(1)
    raise SystemExit(0)
