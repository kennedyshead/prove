"""Shared parse entry point for the Prove compiler.

All compiler consumers that need to parse .prv source should use ``parse()``
from this module instead of calling Lexer + Parser directly.  This provides
a single place to swap the parsing backend (e.g. tree-sitter in Phase 2).
"""

from __future__ import annotations

from prove.ast_nodes import Module
from prove.lexer import Lexer
from prove.parser import Parser


def parse(source: str, filename: str = "<stdin>") -> Module:
    """Parse Prove source into an AST Module."""
    tokens = Lexer(source, filename).lex()
    return Parser(tokens, filename).parse()
