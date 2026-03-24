"""Tree-sitter language loading and parsing for Prove."""

from __future__ import annotations

import tree_sitter

_parser: tree_sitter.Parser | None = None


def _get_language() -> tree_sitter.Language:
    """Get the tree-sitter-prove Language object."""
    import tree_sitter_prove as tsp

    return tree_sitter.Language(tsp.language())


def _get_parser() -> tree_sitter.Parser:
    """Get or create the cached tree-sitter parser."""
    global _parser
    if _parser is None:
        _parser = tree_sitter.Parser(_get_language())
    return _parser


def ts_parse(source: str, old_tree: tree_sitter.Tree | None = None) -> tree_sitter.Tree:
    """Parse Prove source code into a tree-sitter Tree.

    Args:
        source: Prove source code.
        old_tree: Optional previous tree for incremental parsing.

    Returns:
        A tree-sitter Tree.
    """
    parser = _get_parser()
    if old_tree is not None:
        return parser.parse(source.encode("utf-8"), old_tree=old_tree)
    return parser.parse(source.encode("utf-8"))
