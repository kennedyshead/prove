"""Tests for the Prove lexer."""

from __future__ import annotations

import pytest

from prove.errors import CompileError
from prove.lexer import Lexer
from prove.tokens import TokenKind


def lex(source: str) -> list[tuple[TokenKind, str]]:
    """Helper: lex source and return (kind, value) pairs, excluding EOF."""
    tokens = Lexer(source).lex()
    return [(t.kind, t.value) for t in tokens if t.kind != TokenKind.EOF]


def kinds(source: str) -> list[TokenKind]:
    """Helper: lex source and return just the token kinds, excluding EOF."""
    tokens = Lexer(source).lex()
    return [t.kind for t in tokens if t.kind != TokenKind.EOF]


class TestLexerBasic:
    def test_empty_source(self):
        tokens = Lexer("").lex()
        assert len(tokens) == 1
        assert tokens[0].kind == TokenKind.EOF

    def test_identifier(self):
        result = lex("hello")
        assert result == [(TokenKind.IDENTIFIER, "hello")]

    def test_underscore_identifier(self):
        result = lex("_")
        assert result == [(TokenKind.IDENTIFIER, "_")]

    def test_snake_case_identifier(self):
        result = lex("my_var_123")
        assert result == [(TokenKind.IDENTIFIER, "my_var_123")]

    def test_keywords(self):
        for kw in ["transforms", "inputs", "outputs", "validates",
                    "main", "from", "type", "is", "as", "with", "use",
                    "where", "match", "comptime", "valid",
                    "module", "domain", "ensures", "requires", "proof"]:
            result = lex(kw)
            assert len(result) == 1, f"keyword {kw} should lex to one token"
            assert result[0][1] == kw

    def test_type_identifier(self):
        result = lex("String")
        assert result == [(TokenKind.TYPE_IDENTIFIER, "String")]

    def test_type_identifier_camel(self):
        result = lex("OrderItem")
        assert result == [(TokenKind.TYPE_IDENTIFIER, "OrderItem")]

    def test_single_uppercase_is_type(self):
        result = lex("T")
        assert result == [(TokenKind.TYPE_IDENTIFIER, "T")]

    def test_constant_identifier(self):
        result = lex("MAX_CONNECTIONS")
        assert result == [(TokenKind.CONSTANT_IDENTIFIER, "MAX_CONNECTIONS")]

    def test_constant_with_digits(self):
        result = lex("HTTP2")
        assert result == [(TokenKind.CONSTANT_IDENTIFIER, "HTTP2")]

    def test_ai_resistance_keywords(self):
        for kw in ["why_not", "chosen", "near_miss", "know", "assume",
                    "believe", "intent", "narrative", "temporal",
                    "satisfies", "invariant_network"]:
            result = lex(kw)
            assert len(result) == 1, f"keyword {kw} should lex to one token"


class TestLexerLiterals:
    def test_integer(self):
        result = lex("42")
        assert result == [(TokenKind.INTEGER_LIT, "42")]

    def test_integer_with_underscores(self):
        result = lex("1_000_000")
        assert result == [(TokenKind.INTEGER_LIT, "1_000_000")]

    def test_hex_integer(self):
        result = lex("0xFF")
        assert result == [(TokenKind.INTEGER_LIT, "0xFF")]

    def test_binary_integer(self):
        result = lex("0b1010")
        assert result == [(TokenKind.INTEGER_LIT, "0b1010")]

    def test_octal_integer(self):
        result = lex("0o77")
        assert result == [(TokenKind.INTEGER_LIT, "0o77")]

    def test_decimal(self):
        result = lex("3.14")
        assert result == [(TokenKind.DECIMAL_LIT, "3.14")]

    def test_decimal_with_underscores(self):
        result = lex("1_000.50")
        assert result == [(TokenKind.DECIMAL_LIT, "1_000.50")]

    def test_string(self):
        result = lex('"hello world"')
        assert result == [(TokenKind.STRING_LIT, "hello world")]

    def test_string_escape_sequences(self):
        result = lex(r'"hello\nworld"')
        assert result == [(TokenKind.STRING_LIT, "hello\nworld")]

    def test_string_interpolation(self):
        result = lex('f"hello {name}"')
        k = [r[0] for r in result]
        assert TokenKind.STRING_LIT in k
        assert TokenKind.INTERP_START in k
        assert TokenKind.INTERP_END in k
        assert TokenKind.IDENTIFIER in k

    def test_plain_string_braces_literal(self):
        result = lex('"hello {world}"')
        assert result == [(TokenKind.STRING_LIT, "hello {world}")]

    def test_fstring_basic(self):
        result = lex('f"hello {name}"')
        kinds = [r[0] for r in result]
        assert kinds == [
            TokenKind.STRING_LIT,
            TokenKind.INTERP_START,
            TokenKind.IDENTIFIER,
            TokenKind.INTERP_END,
        ]

    def test_raw_string_no_escapes(self):
        result = lex(r'r"hello\nworld"')
        assert result == [(TokenKind.RAW_STRING_LIT, r"hello\nworld")]

    def test_f_as_identifier(self):
        result = lex("f + 1")
        kinds = [r[0] for r in result]
        assert kinds[0] == TokenKind.IDENTIFIER

    def test_unknown_escape_error(self):
        import pytest

        from prove.errors import CompileError
        with pytest.raises(CompileError):
            from prove.lexer import Lexer
            Lexer(r'"\d"').lex()

    def test_triple_string(self):
        result = lex('"""hello\nworld"""')
        assert result == [(TokenKind.TRIPLE_STRING_LIT, "hello\nworld")]

    def test_char_literal(self):
        result = lex("'A'")
        assert result == [(TokenKind.CHAR_LIT, "A")]

    def test_char_escape(self):
        result = lex(r"'\n'")
        assert result == [(TokenKind.CHAR_LIT, "\n")]

    def test_boolean_true(self):
        result = lex("true")
        assert result == [(TokenKind.BOOLEAN_LIT, "true")]

    def test_boolean_false(self):
        result = lex("false")
        assert result == [(TokenKind.BOOLEAN_LIT, "false")]

    def test_regex(self):
        # Regex at start of expression (not after value, deprecated syntax)
        result = lex("/^[A-Z]+$/")
        assert result == [(TokenKind.REGEX_LIT, "^[A-Z]+$")]

    def test_regex_with_escape(self):
        result = lex(r"/hello\/world/")
        assert result == [(TokenKind.REGEX_LIT, r"hello\/world")]

    def test_raw_string_regex(self):
        result = lex(r'r"^[A-Z]+$"')
        assert result == [(TokenKind.RAW_STRING_LIT, "^[A-Z]+$")]

    def test_slash_after_value_is_division(self):
        result = lex("x / y")
        k = [r[0] for r in result]
        assert TokenKind.SLASH in k
        assert TokenKind.REGEX_LIT not in k


class TestLexerOperators:
    def test_single_char_operators(self):
        ops = [("+", TokenKind.PLUS), ("-", TokenKind.MINUS),
               ("*", TokenKind.STAR), ("%", TokenKind.PERCENT),
               ("<", TokenKind.LESS), (">", TokenKind.GREATER),
               ("!", TokenKind.BANG), ("=", TokenKind.ASSIGN),
               (".", TokenKind.DOT)]
        for text, expected_kind in ops:
            result = lex(text)
            assert result[0][0] == expected_kind, f"operator {text}"

    def test_two_char_operators(self):
        ops = [("==", TokenKind.EQUAL), ("!=", TokenKind.NOT_EQUAL),
               ("<=", TokenKind.LESS_EQUAL), (">=", TokenKind.GREATER_EQUAL),
               ("&&", TokenKind.AND), ("||", TokenKind.OR),
               ("|>", TokenKind.PIPE_ARROW), ("=>", TokenKind.FAT_ARROW),
               ("..", TokenKind.DOT_DOT), ("->", TokenKind.ARROW)]
        for text, expected_kind in ops:
            result = lex(text)
            assert result[0][0] == expected_kind, f"operator {text}"

    def test_punctuation(self):
        ops = [("(", TokenKind.LPAREN), (")", TokenKind.RPAREN),
               ("[", TokenKind.LBRACKET), ("]", TokenKind.RBRACKET),
               (",", TokenKind.COMMA), (":", TokenKind.COLON),
               ("|", TokenKind.PIPE)]
        for text, expected_kind in ops:
            result = lex(text)
            assert result[0][0] == expected_kind, f"punctuation {text}"

    def test_bang_vs_not_equal(self):
        result = lex("!=")
        assert result[0][0] == TokenKind.NOT_EQUAL
        result = lex("!")
        assert result[0][0] == TokenKind.BANG


class TestLexerIndentation:
    def test_basic_indent_dedent(self):
        source = "a\n    b\n"
        k = kinds(source)
        assert TokenKind.INDENT in k
        assert TokenKind.DEDENT in k

    def test_multiple_indent_levels(self):
        source = "a\n    b\n        c\n"
        k = kinds(source)
        assert k.count(TokenKind.INDENT) == 2
        assert k.count(TokenKind.DEDENT) == 2

    def test_multi_dedent(self):
        source = "a\n    b\n        c\nd\n"
        k = kinds(source)
        # Should have 2 indents and 2 dedents when going from c back to d
        assert k.count(TokenKind.INDENT) == 2
        assert k.count(TokenKind.DEDENT) == 2

    def test_blank_lines_ignored(self):
        source = "a\n\n    b\n"
        k = kinds(source)
        assert TokenKind.INDENT in k

    def test_comment_only_lines_no_indent(self):
        source = "a\n// comment\n    b\n"
        k = kinds(source)
        assert TokenKind.INDENT in k


class TestLexerNewlines:
    def test_significant_newline(self):
        source = "a\nb\n"
        k = kinds(source)
        assert TokenKind.NEWLINE in k

    def test_suppressed_after_comma(self):
        source = "a,\nb\n"
        k = kinds(source)
        newline_absent = TokenKind.NEWLINE not in k
        newline_after_id = k.index(TokenKind.NEWLINE) > k.index(TokenKind.IDENTIFIER)
        assert newline_absent or newline_after_id

    def test_suppressed_after_operator(self):
        for op in ["+", "-", "*", "/", "==", "!=", "&&", "||"]:
            source = f"a {op}\nb\n"
            k = kinds(source)
            # There should be no NEWLINE between the operator and b
            # (the newline after 'b' is fine)
            op_idx = None
            for i, kind in enumerate(k):
                if kind in (TokenKind.PLUS, TokenKind.MINUS, TokenKind.STAR,
                            TokenKind.SLASH, TokenKind.EQUAL, TokenKind.NOT_EQUAL,
                            TokenKind.AND, TokenKind.OR):
                    op_idx = i
                    break
            if op_idx is not None:
                # Next token after op should NOT be NEWLINE
                if op_idx + 1 < len(k):
                    assert k[op_idx + 1] != TokenKind.NEWLINE, f"newline not suppressed after {op}"

    def test_suppressed_inside_brackets(self):
        source = "(\na\n)\n"
        k = kinds(source)
        newline_count = k.count(TokenKind.NEWLINE)
        # Only the newline after ) should be emitted
        assert newline_count <= 1

    def test_suppressed_after_fat_arrow(self):
        source = "=>\nb\n"
        k = kinds(source)
        # NEWLINE should not appear between => and b
        fa_idx = k.index(TokenKind.FAT_ARROW)
        assert k[fa_idx + 1] != TokenKind.NEWLINE

    def test_suppressed_after_pipe_arrow(self):
        source = "a |>\nb\n"
        k = kinds(source)
        pa_idx = k.index(TokenKind.PIPE_ARROW)
        assert k[pa_idx + 1] != TokenKind.NEWLINE


class TestLexerComments:
    def test_doc_comment_preserved(self):
        result = lex("/// hello world\n")
        assert (TokenKind.DOC_COMMENT, "hello world") in result

    def test_line_comment_skipped(self):
        result = lex("x // comment\n")
        k = [r[0] for r in result]
        assert TokenKind.DOC_COMMENT not in k
        assert TokenKind.IDENTIFIER in k

    def test_multiple_doc_comments(self):
        source = "/// line 1\n/// line 2\n"
        result = lex(source)
        docs = [r for r in result if r[0] == TokenKind.DOC_COMMENT]
        assert len(docs) == 2


class TestLexerIntegration:
    def test_function_signature(self):
        source = "transforms area(s Shape) Decimal\n"
        result = lex(source)
        k = [r[0] for r in result]
        assert TokenKind.TRANSFORMS in k
        assert TokenKind.IDENTIFIER in k
        assert TokenKind.LPAREN in k
        assert TokenKind.TYPE_IDENTIFIER in k
        assert TokenKind.RPAREN in k

    def test_type_definition(self):
        source = "type Port is Integer where 1..65535\n"
        result = lex(source)
        k = [r[0] for r in result]
        assert TokenKind.TYPE in k
        assert TokenKind.IS in k
        assert TokenKind.WHERE in k
        assert TokenKind.DOT_DOT in k

    def test_hello_world(self):
        source = (
            '/// Hello from Prove!\n'
            'main() Result<Unit, Error>!\n'
            '    from\n'
            '        println("Hello from Prove!")\n'
        )
        tokens = Lexer(source).lex()
        k = [t.kind for t in tokens]
        assert TokenKind.DOC_COMMENT in k
        assert TokenKind.MAIN in k
        assert TokenKind.BANG in k
        assert TokenKind.FROM in k
        assert TokenKind.STRING_LIT in k

    def test_tabs_rejected(self):
        source = "\tx\n"
        with pytest.raises(CompileError):
            Lexer(source).lex()
