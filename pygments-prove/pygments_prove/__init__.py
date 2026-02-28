"""Pygments lexer for the Prove programming language."""

from pygments.lexer import RegexLexer, bygroups, words
from pygments.token import (
    Comment,
    Keyword,
    Name,
    Number,
    Operator,
    Punctuation,
    String,
    Text,
)


class ProveLexer(RegexLexer):
    """Pygments lexer for the Prove programming language."""

    name = "Prove"
    aliases = ["prove"]
    filenames = ["*.prv", "*.prove"]
    mimetypes = ["text/x-prove"]

    tokens = {
        "root": [
            # Whitespace
            (r"\s+", Text),
            # Doc comments
            (r"///.*$", Comment.Doc),
            # Line comments
            (r"//.*$", Comment.Single),
            # Triple-quoted strings
            (r'"""[\s\S]*?"""', String),
            # Strings with escapes
            (r'"(?:[^"\\]|\\.)*"', String),
            # Hex numbers
            (r"0x[0-9a-fA-F][0-9a-fA-F_]*", Number.Hex),
            # Binary numbers
            (r"0b[01][01_]*", Number.Bin),
            # Octal numbers
            (r"0o[0-7][0-7_]*", Number.Oct),
            # Decimal floats
            (r"[0-9][0-9_]*\.[0-9][0-9_]*", Number.Float),
            # Integers
            (r"[0-9][0-9_]*", Number.Integer),
            # Contract/annotation keywords
            (
                words(
                    (
                        "ensures",
                        "requires",
                        "proof",
                        "invariant_network",
                        "know",
                        "assume",
                        "believe",
                        "intent",
                        "narrative",
                        "temporal",
                        "why_not",
                        "chosen",
                        "near_miss",
                        "satisfies",
                    ),
                    prefix=r"\b",
                    suffix=r"\b",
                ),
                Keyword.Namespace,
            ),
            # Core keywords
            (
                words(
                    (
                        "module",
                        "type",
                        "with",
                        "use",
                        "transforms",
                        "inputs",
                        "outputs",
                        "validates",
                        "main",
                        "from",
                        "if",
                        "else",
                        "match",
                        "where",
                        "comptime",
                        "is",
                    ),
                    prefix=r"\b",
                    suffix=r"\b",
                ),
                Keyword,
            ),
            # Boolean constants
            (r"\b(true|false)\b", Keyword.Constant),
            # Built-in types
            (
                words(
                    (
                        "Integer",
                        "Decimal",
                        "Float",
                        "Boolean",
                        "String",
                        "Byte",
                        "Character",
                        "List",
                        "Option",
                        "Result",
                        "Unit",
                        "NonEmpty",
                        "Map",
                        "Any",
                        "Never",
                    ),
                    prefix=r"\b",
                    suffix=r"\b",
                ),
                Keyword.Type,
            ),
            # User-defined types (PascalCase)
            (r"[A-Z][A-Za-z0-9_]*", Name.Class),
            # Pipe operator
            (r"\|>", Operator),
            # Fat arrow
            (r"=>", Operator),
            # Multi-char operators
            (r"==|!=|<=|>=|&&|\|\||\.\.|\->", Operator),
            # Single-char operators
            (r"[+\-*/%=<>!&|^~]", Operator),
            # Dot operator
            (r"\.", Operator),
            # Proof obligation names (word followed by colon)
            (r"[a-z_][a-z0-9_]+(?=\s*:)", Name.Attribute),
            # Identifiers
            (r"[a-z_][a-z0-9_]*", Name),
            # Punctuation
            (r"[(),;\[\]{}:]", Punctuation),
        ],
    }
