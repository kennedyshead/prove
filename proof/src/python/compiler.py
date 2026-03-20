"""Convert between .prv lookup types and PDAT binary format.

This script is embedded as a comptime string in compiler.prv and executed via
PyRun_SimpleString.
"""

from __future__ import annotations

from typing import cast

# pylint: disable=invalid-name

file: str = cast(str, globals().get("file", ""))
mode: str = cast(str, globals().get("mode", ""))
output: str | None = cast(str, globals().get("output", None)) or None

if __name__ == "__main__":
    from prove.store_binary import pdat_to_prv, prv_to_pdat

    resolved_mode = mode
    if not resolved_mode:
        if file.endswith(".prv"):
            resolved_mode = "load"
        elif file.endswith(".dat") or file.endswith(".bin"):
            resolved_mode = "dump"
        else:
            print("Error: specify mode 'load' or 'dump', or use .prv/.dat extension.")
            raise SystemExit(1)

    if resolved_mode == "load":
        try:
            out = prv_to_pdat(file, output)
        except Exception as e:
            print(f"Error: {e}")
            raise SystemExit(1) from e
        print(f"Wrote {out}")
    else:
        try:
            source = pdat_to_prv(file, output)
        except Exception as e:
            print(f"Error: {e}")
            raise SystemExit(1) from e
        if output:
            print(f"Wrote {output}")
        else:
            print(source, end="")
    raise SystemExit(0)
