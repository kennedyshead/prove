"""Re-download ML stores to ~/.prove/.

This script is embedded as a comptime string in setup.prv and executed via
PyRun_SimpleString.
"""

from __future__ import annotations

if __name__ == "__main__":
    from prove.nlp_store import download_stores

    ok = download_stores()
    if ok:
        print("Setup complete.")
    else:
        print("Setup failed — check your internet connection.")
        raise SystemExit(1)
    raise SystemExit(0)
