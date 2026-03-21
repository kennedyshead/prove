"""Run the lsp server for prove through python.

This script is embedded as a comptime string in lsp.prv and executed via
PyRun_SimpleString.
"""

from __future__ import annotations
import warnings

warnings.filterwarnings(
    "ignore", message="nltk.app.wordfreq not loaded", category=UserWarning
)
if __name__ == "__main__":
    from prove.lsp import main as lsp_main

    lsp_main()
    raise SystemExit(0)
