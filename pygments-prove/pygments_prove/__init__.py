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
            # Raw strings (regex internals)
            (r'r"', String.Regex, "raw_string"),
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
            # PROVE-EXPORT-BEGIN: verbs
            # Intent verbs (function declaration keywords)
            (
                words(
                    (
                        "creates", "inputs", "matches", "outputs", "reads", "transforms", "validates",
                    ),
                    prefix=r"\b",
                    suffix=r"\b",
                ),
                Keyword.Declaration,
            ),
            # PROVE-EXPORT-END: verbs
            # PROVE-EXPORT-BEGIN: contract-keywords
            # Contract keywords
            (
                words(
                    (
                        "ensures", "explain", "requires", "terminates", "trusted", "when",
                    ),
                    prefix=r"\b",
                    suffix=r"\b",
                ),
                Keyword.Namespace,
            ),
            # PROVE-EXPORT-END: contract-keywords
            # PROVE-EXPORT-BEGIN: keywords
            # Core keywords
            (
                words(
                    (
                        "as",
                        "binary",
                        "comptime",
                        "domain",
                        "foreign",
                        "from",
                        "is",
                        "main",
                        "match",
                        "module",
                        "type",
                        "types",
                        "valid",
                        "where",
                    ),
                    prefix=r"\b",
                    suffix=r"\b",
                ),
                Keyword,
            ),
            # PROVE-EXPORT-END: keywords
            # PROVE-EXPORT-BEGIN: ai-keywords
            # AI-resistance and annotation keywords
            (
                words(
                    (
                        "assume",
                        "believe",
                        "chosen",
                        "intent",
                        "invariant_network",
                        "know",
                        "narrative",
                        "near_miss",
                        "satisfies",
                        "temporal",
                        "why_not",
                    ),
                    prefix=r"\b",
                    suffix=r"\b",
                ),
                Keyword.Namespace,
            ),
            # PROVE-EXPORT-END: ai-keywords
            # PROVE-EXPORT-BEGIN: literals
            # Boolean constants
            (r"\b(true|false)\b", Keyword.Constant),
            # PROVE-EXPORT-END: literals
            # PROVE-EXPORT-BEGIN: builtin-types
            # Built-in types
            (
                words(
                    (
                        "Boolean",
                        "Byte",
                        "Character",
                        "Decimal",
                        "Error",
                        "Float",
                        "Integer",
                        "List",
                        "Option",
                        "Result",
                        "String",
                        "Table",
                        "Unit",
                    ),
                    prefix=r"\b",
                    suffix=r"\b",
                ),
                Keyword.Type,
            ),
            # PROVE-EXPORT-END: builtin-types
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
            # Explain entry names (word followed by colon)
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
        # Raw string state — regex internals
        "raw_string": [
            (r'"', String.Regex, "#pop"),
            (r'\\[dDwWsStrnbBfv0\\.|(){}\[\]+*?^$/]', String.Escape),
            (r'\[\^?\]?([^\]\\]|\\.|\[:\w+:\])*\]', Punctuation),
            (r'[+*?]|\{[0-9]+(?:,[0-9]*)?\}', Operator),
            (r'\(\?[=!:]|\(', Punctuation),
            (r'\)', Punctuation),
            (r'[\^$]', Operator),
            (r'\|', Operator),
            (r'\.', Operator),
            (r'[^"\\.|()[\]{}+*?^$]+', String.Regex),
        ],
    }
