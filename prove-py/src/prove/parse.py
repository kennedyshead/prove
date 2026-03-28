"""Shared parse entry point for the Prove compiler.

All compiler consumers that need to parse .prv source should use ``parse()``
from this module instead of calling Lexer + Parser directly.  Uses tree-sitter
via CSTConverter as the sole parser backend.
"""

from __future__ import annotations

from prove.ast_nodes import Module


def parse(source: str, filename: str = "<stdin>") -> Module:
    """Parse Prove source into an AST Module."""
    from prove.cst_converter import CSTConverter
    from prove.tree_sitter_setup import ts_parse

    tree = ts_parse(source)
    return CSTConverter(source, tree, filename).convert()
