"""Shared parse entry point for the Prove compiler.

All compiler consumers that need to parse .prv source should use ``parse()``
from this module instead of calling Lexer + Parser directly.  Phase 2 of the
compiler plan swaps the backend to tree-sitter via CSTConverter.

Set PROVE_PARSER=legacy to use the old Lexer + Parser backend.
"""

from __future__ import annotations

import os

from prove.ast_nodes import Module


def _use_tree_sitter() -> bool:
    """Check if tree-sitter backend is available and not disabled."""
    if os.environ.get("PROVE_PARSER") == "legacy":
        return False
    try:
        import tree_sitter  # noqa: F401
        import tree_sitter_prove  # noqa: F401

        return True
    except (ImportError, ModuleNotFoundError):
        return False


_HAS_TREE_SITTER: bool | None = None


def parse(source: str, filename: str = "<stdin>") -> Module:
    """Parse Prove source into an AST Module."""
    global _HAS_TREE_SITTER
    if _HAS_TREE_SITTER is None:
        _HAS_TREE_SITTER = _use_tree_sitter()

    if not _HAS_TREE_SITTER:
        from prove.lexer import Lexer
        from prove.parser import Parser

        tokens = Lexer(source, filename).lex()
        return Parser(tokens, filename).parse()

    from prove.cst_converter import CSTConverter
    from prove.tree_sitter_setup import ts_parse

    tree = ts_parse(source)
    return CSTConverter(source, tree, filename).convert()
