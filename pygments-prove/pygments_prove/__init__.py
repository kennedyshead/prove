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
            # Doc comments (/// ...)
            (r"///.*$", Comment.Special),
            # Line comments (// ...)
            (r"//.*$", Comment.Single),
            # Triple-quoted strings
            (r'"""[\s\S]*?"""', String),
            # F-strings with interpolation
            (r'f"', String.Affix, "fstring"),
            # Raw strings (no escapes)
            (r'r"[^"]*"', String.Regex),
            # Regular strings with escape support
            (r'"', String, "string"),
            # Regex literals (deprecated /pattern/ form)
            (r"/[^\s/]([^/\n\\]|\\.)*?/", String.Regex),
            # Numbers
            (r"0x[0-9a-fA-F][0-9a-fA-F_]*", Number.Hex),
            (r"0b[01][01_]*", Number.Bin),
            (r"0o[0-7][0-7_]*", Number.Oct),
            (r"[0-9][0-9_]*\.[0-9][0-9_]*", Number.Float),
            (r"[0-9][0-9_]*", Number.Integer),
            # Fail marker (before operators)
            (r"!", Keyword.Pseudo),
            # Intent verbs (function declaration keywords)
            (
                words(
                    ("transforms", "inputs", "outputs", "validates"),
                    prefix=r"\b",
                    suffix=r"\b",
                ),
                Keyword.Declaration,
            ),
            # Contract keywords
            (
                words(
                    ("ensures", "requires", "proof"),
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
                        "is",
                        "as",
                        "from",
                        "if",
                        "else",
                        "match",
                        "where",
                        "comptime",
                        "valid",
                        "main",
                        "types",
                    ),
                    prefix=r"\b",
                    suffix=r"\b",
                ),
                Keyword,
            ),
            # AI-resistance and annotation keywords
            (
                words(
                    (
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
            # Boolean constants
            (r"\b(true|false)\b", Keyword.Constant),
            # Built-in types (synced with tree-sitter highlights.scm)
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
            # Operators (multi-char before single-char)
            (r"\|>", Operator),
            (r"=>", Punctuation),
            (r"==|!=|<=|>=|&&|\|\||\.\.|\->", Operator),
            (r"[+\-*/%<>]", Operator),
            (r"=", Operator),
            (r"\.", Operator),
            # Constant identifiers (ALL_CAPS)
            (r"[A-Z][A-Z0-9_]+\b", Name.Constant),
            # User-defined types (PascalCase)
            (r"[A-Z][a-zA-Z0-9]*", Name.Class),
            # Proof obligation names (word followed by colon)
            (r"[a-z_][a-z0-9_]+(?=\s*:)", Name.Attribute),
            # Identifiers
            (r"[a-z_][a-z0-9_]*", Name),
            # Punctuation
            (r"[(),;\[\]{}:|]", Punctuation),
        ],
        # String state — handles escape sequences
        "string": [
            (r'\\[nrt\\"{}0]', String.Escape),
            (r'[^"\\]+', String),
            (r'"', String, "#pop"),
        ],
        # F-string state — handles escapes and interpolation
        "fstring": [
            (r'\\[nrt\\"{}0]', String.Escape),
            (r"\{", String.Interpol, "fstring_interp"),
            (r'[^"\\{]+', String.Affix),
            (r'"', String.Affix, "#pop"),
        ],
        # F-string interpolation — lex expression inside {…}
        "fstring_interp": [
            (r"\}", String.Interpol, "#pop"),
            (r"[^}]+", Name),
        ],
    }
