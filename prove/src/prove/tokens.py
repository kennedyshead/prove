"""Token kinds and token representation for the Prove lexer."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from prove.source import Span


class TokenKind(Enum):
    # Verbs
    TRANSFORMS = auto()
    INPUTS = auto()
    OUTPUTS = auto()
    VALIDATES = auto()

    # Keywords
    MAIN = auto()
    FROM = auto()
    TYPE = auto()
    IS = auto()
    AS = auto()
    WITH = auto()
    USE = auto()
    WHERE = auto()
    MATCH = auto()
    IF = auto()
    ELSE = auto()
    COMPTIME = auto()
    VALID = auto()
    MODULE = auto()
    DOMAIN = auto()

    # Contracts
    ENSURES = auto()
    REQUIRES = auto()
    PROOF = auto()

    # AI-resistance
    WHY_NOT = auto()
    CHOSEN = auto()
    NEAR_MISS = auto()
    KNOW = auto()
    ASSUME = auto()
    BELIEVE = auto()
    INTENT = auto()
    NARRATIVE = auto()
    TEMPORAL = auto()
    SATISFIES = auto()
    INVARIANT_NETWORK = auto()

    # Literals
    INTEGER_LIT = auto()
    DECIMAL_LIT = auto()
    STRING_LIT = auto()
    BOOLEAN_LIT = auto()
    CHAR_LIT = auto()
    TRIPLE_STRING_LIT = auto()
    REGEX_LIT = auto()

    # String interpolation
    INTERP_START = auto()
    INTERP_END = auto()

    # Operators
    PLUS = auto()
    MINUS = auto()
    STAR = auto()
    SLASH = auto()
    PERCENT = auto()
    EQUAL = auto()
    NOT_EQUAL = auto()
    LESS = auto()
    GREATER = auto()
    LESS_EQUAL = auto()
    GREATER_EQUAL = auto()
    AND = auto()
    OR = auto()
    BANG = auto()
    PIPE_ARROW = auto()
    FAT_ARROW = auto()
    DOT_DOT = auto()
    DOT = auto()
    ASSIGN = auto()
    ARROW = auto()

    # Punctuation
    LPAREN = auto()
    RPAREN = auto()
    LBRACKET = auto()
    RBRACKET = auto()
    COMMA = auto()
    COLON = auto()
    PIPE = auto()

    # Whitespace
    NEWLINE = auto()
    INDENT = auto()
    DEDENT = auto()

    # Comments
    DOC_COMMENT = auto()

    # Identifiers
    IDENTIFIER = auto()
    TYPE_IDENTIFIER = auto()
    CONSTANT_IDENTIFIER = auto()

    # Special
    EOF = auto()


@dataclass(frozen=True)
class Token:
    kind: TokenKind
    value: str
    span: Span


KEYWORDS: dict[str, TokenKind] = {
    "transforms": TokenKind.TRANSFORMS,
    "inputs": TokenKind.INPUTS,
    "outputs": TokenKind.OUTPUTS,
    "validates": TokenKind.VALIDATES,
    "main": TokenKind.MAIN,
    "from": TokenKind.FROM,
    "type": TokenKind.TYPE,
    "is": TokenKind.IS,
    "as": TokenKind.AS,
    "with": TokenKind.WITH,
    "use": TokenKind.USE,
    "where": TokenKind.WHERE,
    "match": TokenKind.MATCH,
    "if": TokenKind.IF,
    "else": TokenKind.ELSE,
    "comptime": TokenKind.COMPTIME,
    "valid": TokenKind.VALID,
    "module": TokenKind.MODULE,
    "domain": TokenKind.DOMAIN,
    "ensures": TokenKind.ENSURES,
    "requires": TokenKind.REQUIRES,
    "proof": TokenKind.PROOF,
    "why_not": TokenKind.WHY_NOT,
    "chosen": TokenKind.CHOSEN,
    "near_miss": TokenKind.NEAR_MISS,
    "know": TokenKind.KNOW,
    "assume": TokenKind.ASSUME,
    "believe": TokenKind.BELIEVE,
    "intent": TokenKind.INTENT,
    "narrative": TokenKind.NARRATIVE,
    "temporal": TokenKind.TEMPORAL,
    "satisfies": TokenKind.SATISFIES,
    "invariant_network": TokenKind.INVARIANT_NETWORK,
    "true": TokenKind.BOOLEAN_LIT,
    "false": TokenKind.BOOLEAN_LIT,
}

NEWLINE_SUPPRESSED_AFTER: frozenset[TokenKind] = frozenset({
    TokenKind.COMMA,
    TokenKind.PLUS,
    TokenKind.MINUS,
    TokenKind.STAR,
    TokenKind.SLASH,
    TokenKind.PERCENT,
    TokenKind.EQUAL,
    TokenKind.NOT_EQUAL,
    TokenKind.LESS,
    TokenKind.GREATER,
    TokenKind.LESS_EQUAL,
    TokenKind.GREATER_EQUAL,
    TokenKind.AND,
    TokenKind.OR,
    TokenKind.PIPE_ARROW,
    TokenKind.FAT_ARROW,
    TokenKind.ARROW,
    TokenKind.COLON,
    TokenKind.PIPE,
    TokenKind.LPAREN,
    TokenKind.LBRACKET,
    TokenKind.ASSIGN,
    TokenKind.DOT,
    TokenKind.DOT_DOT,
})
