"""Natural language intent analysis for Prove prose blocks.

Maps English action words to Prove verb keywords and extracts
semantic tokens from prose and function bodies.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from prove.ast_nodes import FunctionDef

# Each entry: (regex pattern, prove_verb_keyword)
# Patterns match word stems — checked against individual lowercased words.
_PROSE_STEMS: list[tuple[str, str]] = [
    (r"transform|convert|comput|calculat|process|produc", "transforms"),
    (r"validat|check|verif|ensur|guard", "validates"),
    (r"\bread|fetch|load|retriev|queri", "reads"),
    (r"creat|make|build|construct|generat", "creates"),
    (r"match|compar|classif|select", "matches"),
    (r"output|write|print|send|emit|log|display", "outputs"),
    (r"input|receiv|accept|pars|tak", "inputs"),
    (r"listen|watch|monitor|wait", "listens"),
    (r"detach|fire|spawn|fork|background", "detached"),
    (r"attach|await|join|child|worker", "attached"),
    (r"stream|block|poll|loop", "streams"),
]


def implied_verbs(text: str) -> set[str]:
    """Return Prove verb keywords implied by action words in prose text."""
    words = re.findall(r"[a-z]+", text.lower())
    result: set[str] = set()
    for word in words:
        for pattern, verb in _PROSE_STEMS:
            if re.search(pattern, word):
                result.add(verb)
                break
    return result


def body_tokens(fd: FunctionDef) -> set[str]:
    """Return param names + called function names from the from-body.

    Walks the AST recursively, collecting:
    - Parameter names from the function signature
    - Names of functions called directly (IdentifierExpr as func in CallExpr)
    """
    from prove.ast_nodes import CallExpr, IdentifierExpr

    names: set[str] = {p.name for p in fd.params}

    def _collect(node: object) -> None:
        if node is None:
            return
        if isinstance(node, (list, tuple)):
            for item in node:
                _collect(item)
            return
        if isinstance(node, CallExpr):
            if isinstance(node.func, IdentifierExpr):
                names.add(node.func.name)
        if hasattr(node, "__dataclass_fields__"):
            for val in vars(node).values():
                _collect(val)

    for stmt in fd.body:
        _collect(stmt)
    return names


def prose_overlaps(prose: str, tokens: set[str]) -> bool:
    """True if any word in prose matches a body token (case-insensitive, with stemming).

    Checks both direct matches and 4-character prefix stems, so "hashing"
    matches "hash" and vice versa.
    """
    prose_words = {w.lower() for w in re.findall(r"[a-zA-Z_][a-zA-Z0-9_]*", prose)}
    lower_tokens = {t.lower() for t in tokens}
    if prose_words & lower_tokens:
        return True
    for pw in prose_words:
        if len(pw) >= 4:
            for t in lower_tokens:
                if t.startswith(pw) or pw.startswith(t[:4]):
                    return True
    return False
