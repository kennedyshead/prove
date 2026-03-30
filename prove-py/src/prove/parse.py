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

    # Run lexical validation to catch unterminated literals (E101-E109).
    # Tree-sitter reports these as generic ERROR nodes; the Lexer gives
    # specific diagnostics.
    _check_lexical_errors(source, filename)

    tree = ts_parse(source)
    return CSTConverter(source, tree, filename).convert()


def _check_lexical_errors(source: str, filename: str) -> None:
    """Run the legacy Lexer for lexical-level diagnostics (E10x).

    Raises CompileError if any lexical errors are found.
    """
    from prove.lexer import Lexer

    lexer = Lexer(source, filename)
    lexer.lex()  # raises CompileError on E101-E109


def has_parse_errors(source: str) -> bool:
    """Return True if tree-sitter reports any parse errors for *source*."""
    from prove.tree_sitter_setup import ts_parse

    tree = ts_parse(source)

    def _has_error(node) -> bool:
        if node.type == "ERROR" or node.is_missing:
            return True
        for child in node.children:
            if _has_error(child):
                return True
        return False

    return _has_error(tree.root_node)
