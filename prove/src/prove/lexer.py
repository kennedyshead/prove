"""Lexer for the Prove programming language.

Produces a stream of tokens from source text, including Python-style
INDENT/DEDENT tokens and string interpolation support.
"""

from __future__ import annotations

from prove.errors import CompileError, Diagnostic, DiagnosticLabel, Severity
from prove.source import Span
from prove.tokens import (
    KEYWORDS,
    NEWLINE_SUPPRESSED_AFTER,
    Token,
    TokenKind,
)

# Token kinds that indicate a "value" just completed — used for regex vs division.
_VALUE_TOKENS = frozenset({
    TokenKind.IDENTIFIER,
    TokenKind.TYPE_IDENTIFIER,
    TokenKind.CONSTANT_IDENTIFIER,
    TokenKind.INTEGER_LIT,
    TokenKind.DECIMAL_LIT,
    TokenKind.STRING_LIT,
    TokenKind.TRIPLE_STRING_LIT,
    TokenKind.BOOLEAN_LIT,
    TokenKind.CHAR_LIT,
    TokenKind.REGEX_LIT,
    TokenKind.PATH_LIT,
    TokenKind.RPAREN,
    TokenKind.RBRACKET,
    TokenKind.BANG,
    TokenKind.INTERP_END,
})


class Lexer:
    """Tokenizes Prove source code."""

    def __init__(self, source: str, filename: str = "<stdin>") -> None:
        self.source = source
        self.filename = filename
        self.pos = 0
        self.line = 1
        self.col = 1
        self.indent_stack: list[int] = [0]
        self.bracket_depth = 0
        self.prev_token: Token | None = None
        self.tokens: list[Token] = []
        self.diagnostics: list[Diagnostic] = []
        self._at_line_start = True

    def lex(self) -> list[Token]:
        """Tokenize the entire source and return the token list."""
        while self.pos < len(self.source):
            if self._at_line_start and self.bracket_depth == 0:
                self._handle_indentation()
            self._at_line_start = False
            self._skip_spaces()
            if self.pos >= len(self.source):
                break
            ch = self.source[self.pos]
            if ch == '\n':
                self._handle_newline()
            elif ch == '/' and self._peek(1) == '/' and self._peek(2) == '/':
                self._lex_doc_comment()
            elif ch == '/' and self._peek(1) == '/':
                self._skip_line_comment()
            elif ch == '"' and self._peek(1) == '"' and self._peek(2) == '"':
                self._lex_triple_string()
            elif ch == '"':
                self._lex_string()
            elif ch == "'":
                self._lex_char()
            elif ch == '/' and self._should_start_regex():
                if self._is_path_literal():
                    self._lex_path()
                else:
                    self._lex_regex()
            elif ch.isdigit():
                self._lex_number()
            elif ch.isalpha() or ch == '_':
                self._lex_identifier()
            else:
                self._lex_operator_or_punct()

        # Emit remaining DEDENTs
        while len(self.indent_stack) > 1:
            self.indent_stack.pop()
            self._emit(TokenKind.DEDENT, "", self.line, self.col)

        self._emit(TokenKind.EOF, "", self.line, self.col)

        if self.diagnostics:
            raise CompileError(self.diagnostics)
        return self.tokens

    # ── Helpers ───────────────────────────────────────────────────

    def _peek(self, offset: int = 0) -> str:
        idx = self.pos + offset
        if idx < len(self.source):
            return self.source[idx]
        return '\0'

    def _advance(self) -> str:
        ch = self.source[self.pos]
        self.pos += 1
        if ch == '\n':
            self.line += 1
            self.col = 1
        else:
            self.col += 1
        return ch

    def _is_digit_or_underscore(self) -> bool:
        ch = self.source[self.pos]
        return ch.isdigit() or ch == '_'

    def _is_ident_char(self) -> bool:
        ch = self.source[self.pos]
        return ch.isalnum() or ch == '_'

    def _emit(self, kind: TokenKind, value: str, start_line: int, start_col: int) -> Token:
        end_col = self.col - 1 if self.col > 1 else 1
        span = Span(self.filename, start_line, start_col, self.line, end_col)
        tok = Token(kind, value, span)
        self.tokens.append(tok)
        self.prev_token = tok
        return tok

    def _error(self, message: str, line: int, col: int) -> None:
        span = Span(self.filename, line, col, line, col)
        self.diagnostics.append(
            Diagnostic(
                severity=Severity.ERROR,
                code="E100",
                message=message,
                labels=[DiagnosticLabel(span=span, message="")],
            )
        )

    def _skip_spaces(self) -> None:
        """Skip spaces and tabs (but not newlines)."""
        while self.pos < len(self.source) and self.source[self.pos] in (' ', '\t'):
            if self.source[self.pos] == '\t':
                self._error("tabs are not allowed; use spaces", self.line, self.col)
            self._advance()

    # ── Indentation ──────────────────────────────────────────────

    def _handle_indentation(self) -> None:
        """Process indentation at the start of a line."""
        indent = 0
        while self.pos < len(self.source) and self.source[self.pos] == ' ':
            indent += 1
            self.pos += 1
            self.col += 1

        if self.pos < len(self.source) and self.source[self.pos] == '\t':
            self._error("tabs are not allowed; use spaces", self.line, self.col)

        # Skip blank lines and comment-only lines
        if self.pos >= len(self.source) or self.source[self.pos] == '\n':
            return
        if (self.pos + 1 < len(self.source)
                and self.source[self.pos] == '/'
                and self.source[self.pos + 1] == '/'
                and (self.pos + 2 >= len(self.source) or self.source[self.pos + 2] != '/')):
            return

        current = self.indent_stack[-1]
        if indent > current:
            self.indent_stack.append(indent)
            self._emit(TokenKind.INDENT, "", self.line, 1)
        elif indent < current:
            while len(self.indent_stack) > 1 and self.indent_stack[-1] > indent:
                self.indent_stack.pop()
                self._emit(TokenKind.DEDENT, "", self.line, 1)
            if self.indent_stack[-1] != indent:
                expected = self.indent_stack[-1]
                self._error(
                    f"inconsistent indentation: expected {expected}"
                    f" spaces, got {indent}",
                    self.line, 1,
                )

    # ── Newlines ─────────────────────────────────────────────────

    def _handle_newline(self) -> None:
        start_line = self.line
        start_col = self.col
        self._advance()
        self._at_line_start = True

        if self.bracket_depth > 0:
            return
        if self.prev_token is not None and self.prev_token.kind in NEWLINE_SUPPRESSED_AFTER:
            return
        # Don't emit duplicate newlines
        if self.prev_token is not None and self.prev_token.kind == TokenKind.NEWLINE:
            return

        self._emit(TokenKind.NEWLINE, "\n", start_line, start_col)

    # ── Comments ─────────────────────────────────────────────────

    def _lex_doc_comment(self) -> None:
        start_line = self.line
        start_col = self.col
        # Skip ///
        self._advance()
        self._advance()
        self._advance()
        # Skip optional leading space
        if self.pos < len(self.source) and self.source[self.pos] == ' ':
            self._advance()
        text = []
        while self.pos < len(self.source) and self.source[self.pos] != '\n':
            text.append(self._advance())
        self._emit(TokenKind.DOC_COMMENT, ''.join(text), start_line, start_col)

    def _skip_line_comment(self) -> None:
        while self.pos < len(self.source) and self.source[self.pos] != '\n':
            self._advance()

    # ── Strings ──────────────────────────────────────────────────

    def _lex_triple_string(self) -> None:
        start_line = self.line
        start_col = self.col
        # Skip opening """
        self._advance()
        self._advance()
        self._advance()
        text = []
        while self.pos < len(self.source):
            if (self.source[self.pos] == '"'
                    and self._peek(1) == '"'
                    and self._peek(2) == '"'):
                self._advance()
                self._advance()
                self._advance()
                self._emit(TokenKind.TRIPLE_STRING_LIT, ''.join(text), start_line, start_col)
                return
            text.append(self._advance())
        self._error("unterminated triple-quoted string", start_line, start_col)

    def _lex_string(self) -> None:
        start_line = self.line
        start_col = self.col
        self._advance()  # skip opening "
        text = []
        has_interp = False

        while self.pos < len(self.source) and self.source[self.pos] != '"':
            if self.source[self.pos] == '\\':
                text.append(self._lex_escape_sequence())
            elif self.source[self.pos] == '{':
                # String interpolation
                has_interp = True
                if text:
                    self._emit(TokenKind.STRING_LIT, ''.join(text), start_line, start_col)
                    text = []
                self._advance()  # skip {
                self._emit(TokenKind.INTERP_START, "{", self.line, self.col - 1)
                # Lex tokens inside interpolation until matching }
                brace_depth = 1
                while self.pos < len(self.source) and brace_depth > 0:
                    self._skip_spaces()
                    if self.pos >= len(self.source):
                        break
                    if self.source[self.pos] == '}':
                        brace_depth -= 1
                        if brace_depth == 0:
                            self._advance()
                            self._emit(TokenKind.INTERP_END, "}", self.line, self.col - 1)
                            break
                    elif self.source[self.pos] == '{':
                        brace_depth += 1
                    # Lex one token inside interpolation
                    ch = self.source[self.pos]
                    if ch == '\n':
                        self._advance()
                    elif ch.isdigit():
                        self._lex_number()
                    elif ch.isalpha() or ch == '_':
                        self._lex_identifier()
                    elif ch == '"':
                        self._lex_string()
                    else:
                        self._lex_operator_or_punct()
                start_line = self.line
                start_col = self.col
            else:
                text.append(self._advance())

        if self.pos >= len(self.source):
            self._error("unterminated string literal", start_line, start_col)
            return

        self._advance()  # skip closing "

        if has_interp:
            if text:
                self._emit(TokenKind.STRING_LIT, ''.join(text), start_line, start_col)
        else:
            self._emit(TokenKind.STRING_LIT, ''.join(text), start_line, start_col)

    def _lex_escape_sequence(self) -> str:
        self._advance()  # skip backslash
        if self.pos >= len(self.source):
            self._error("unexpected end of escape sequence", self.line, self.col)
            return ""
        ch = self._advance()
        escape_map = {'n': '\n', 'r': '\r', 't': '\t', '\\': '\\', '"': '"',
                      '{': '{', '}': '}', '0': '\0'}
        if ch in escape_map:
            return escape_map[ch]
        self._error(f"unknown escape sequence: \\{ch}", self.line, self.col - 1)
        return ch

    def _lex_char(self) -> None:
        start_line = self.line
        start_col = self.col
        self._advance()  # skip opening '
        if self.pos >= len(self.source):
            self._error("unterminated character literal", start_line, start_col)
            return
        if self.source[self.pos] == '\\':
            ch = self._lex_escape_sequence()
        else:
            ch = self._advance()
        if self.pos < len(self.source) and self.source[self.pos] == "'":
            self._advance()
        else:
            self._error("unterminated character literal", start_line, start_col)
        self._emit(TokenKind.CHAR_LIT, ch, start_line, start_col)

    # ── Regex ────────────────────────────────────────────────────

    def _should_start_regex(self) -> bool:
        if self.prev_token is None:
            return True
        return self.prev_token.kind not in _VALUE_TOKENS

    def _lex_regex(self) -> None:
        start_line = self.line
        start_col = self.col
        self._advance()  # skip opening /
        text = []
        while self.pos < len(self.source) and self.source[self.pos] != '/':
            if self.source[self.pos] == '\\':
                text.append(self._advance())  # backslash
                if self.pos < len(self.source):
                    text.append(self._advance())  # escaped char
            elif self.source[self.pos] == '\n':
                self._error("unterminated regex literal", start_line, start_col)
                return
            else:
                text.append(self._advance())
        if self.pos >= len(self.source):
            self._error("unterminated regex literal", start_line, start_col)
            return
        self._advance()  # skip closing /
        self._emit(TokenKind.REGEX_LIT, ''.join(text), start_line, start_col)

    # ── Path literals ────────────────────────────────────────────

    def _is_path_literal(self) -> bool:
        """Lookahead to distinguish path literal from regex literal.

        A path literal starts with / followed by a letter or _, and
        continues through path-valid chars. Internal / must be followed
        by a letter/digit/_ (multi-segment path). If we reach a
        terminator without a closing / it's a path.
        """
        i = self.pos + 1
        if i >= len(self.source):
            return False
        ch = self.source[i]
        if not (ch.isalpha() or ch == '_'):
            return False
        i += 1
        while i < len(self.source):
            ch = self.source[i]
            if ch == '\\':
                # Backslash escape → this is a regex, not a path
                return False
            if ch == '/':
                # Internal slash: check if next char continues a path segment
                nxt = self.source[i + 1] if i + 1 < len(self.source) else '\0'
                if nxt.isalpha() or nxt.isdigit() or nxt == '_':
                    i += 1
                    continue
                else:
                    # Closing / → this is a regex, not a path
                    return False
            elif ch.isalnum() or ch in '-_.':
                i += 1
                continue
            else:
                # Hit a terminator (paren, comma, space, newline, etc.)
                return True
        return True

    def _lex_path(self) -> None:
        """Lex a path literal: /segment/segment/..."""
        start_line = self.line
        start_col = self.col
        text = [self._advance()]  # consume leading /
        while self.pos < len(self.source):
            ch = self.source[self.pos]
            if ch.isalnum() or ch in '-_./':
                text.append(self._advance())
            else:
                break
        self._emit(TokenKind.PATH_LIT, ''.join(text), start_line, start_col)

    # ── Numbers ──────────────────────────────────────────────────

    def _lex_number(self) -> None:
        start_line = self.line
        start_col = self.col
        text = []

        # Check for 0x, 0b, 0o prefixes
        if self.source[self.pos] == '0' and self.pos + 1 < len(self.source):
            next_ch = self.source[self.pos + 1]
            if next_ch in ('x', 'X'):
                text.append(self._advance())  # 0
                text.append(self._advance())  # x
                self._lex_hex_digits(text)
                self._emit(TokenKind.INTEGER_LIT, ''.join(text), start_line, start_col)
                return
            elif next_ch in ('b', 'B'):
                text.append(self._advance())  # 0
                text.append(self._advance())  # b
                self._lex_bin_digits(text)
                self._emit(TokenKind.INTEGER_LIT, ''.join(text), start_line, start_col)
                return
            elif next_ch in ('o', 'O'):
                text.append(self._advance())  # 0
                text.append(self._advance())  # o
                self._lex_oct_digits(text)
                self._emit(TokenKind.INTEGER_LIT, ''.join(text), start_line, start_col)
                return

        # Decimal digits
        while self.pos < len(self.source) and self._is_digit_or_underscore():
            text.append(self._advance())

        # Check for decimal point
        if (self.pos < len(self.source) and self.source[self.pos] == '.'
                and self.pos + 1 < len(self.source) and self.source[self.pos + 1].isdigit()):
            text.append(self._advance())  # .
            while self.pos < len(self.source) and self._is_digit_or_underscore():
                text.append(self._advance())
            self._emit(TokenKind.DECIMAL_LIT, ''.join(text), start_line, start_col)
        else:
            self._emit(TokenKind.INTEGER_LIT, ''.join(text), start_line, start_col)

    def _lex_hex_digits(self, text: list[str]) -> None:
        while self.pos < len(self.source) and (self.source[self.pos] in '0123456789abcdefABCDEF_'):
            text.append(self._advance())

    def _lex_bin_digits(self, text: list[str]) -> None:
        while self.pos < len(self.source) and self.source[self.pos] in '01_':
            text.append(self._advance())

    def _lex_oct_digits(self, text: list[str]) -> None:
        while self.pos < len(self.source) and self.source[self.pos] in '01234567_':
            text.append(self._advance())

    # ── Identifiers and Keywords ─────────────────────────────────

    def _lex_identifier(self) -> None:
        start_line = self.line
        start_col = self.col
        text = []
        while self.pos < len(self.source) and self._is_ident_char():
            text.append(self._advance())
        word = ''.join(text)

        # Check keywords first
        if word in KEYWORDS:
            self._emit(KEYWORDS[word], word, start_line, start_col)
            return

        # Classify identifier
        kind = self._classify_identifier(word)
        self._emit(kind, word, start_line, start_col)

    def _classify_identifier(self, word: str) -> TokenKind:
        if word == '_':
            return TokenKind.IDENTIFIER
        # All uppercase + underscores = CONSTANT (must have at least 2 chars)
        all_upper = all(c.isupper() or c == '_' or c.isdigit() for c in word)
        if len(word) >= 2 and all_upper and word[0].isupper():
            return TokenKind.CONSTANT_IDENTIFIER
        # Starts uppercase + has lowercase = TYPE
        if word[0].isupper() and any(c.islower() for c in word):
            return TokenKind.TYPE_IDENTIFIER
        # Single uppercase letter = TYPE
        if len(word) == 1 and word[0].isupper():
            return TokenKind.TYPE_IDENTIFIER
        return TokenKind.IDENTIFIER

    # ── Operators and Punctuation ────────────────────────────────

    def _lex_operator_or_punct(self) -> None:
        start_line = self.line
        start_col = self.col
        ch = self.source[self.pos]

        # Two-character operators
        if self.pos + 1 < len(self.source):
            two = self.source[self.pos:self.pos + 2]
            if two == '|>':
                self._advance()
                self._advance()
                self._emit(TokenKind.PIPE_ARROW, '|>', start_line, start_col)
                return
            if two == '=>':
                self._advance()
                self._advance()
                self._emit(TokenKind.FAT_ARROW, '=>', start_line, start_col)
                return
            if two == '->':
                self._advance()
                self._advance()
                self._emit(TokenKind.ARROW, '->', start_line, start_col)
                return
            if two == '==':
                self._advance()
                self._advance()
                self._emit(TokenKind.EQUAL, '==', start_line, start_col)
                return
            if two == '!=':
                self._advance()
                self._advance()
                self._emit(TokenKind.NOT_EQUAL, '!=', start_line, start_col)
                return
            if two == '<=':
                self._advance()
                self._advance()
                self._emit(TokenKind.LESS_EQUAL, '<=', start_line, start_col)
                return
            if two == '>=':
                self._advance()
                self._advance()
                self._emit(TokenKind.GREATER_EQUAL, '>=', start_line, start_col)
                return
            if two == '&&':
                self._advance()
                self._advance()
                self._emit(TokenKind.AND, '&&', start_line, start_col)
                return
            if two == '||':
                self._advance()
                self._advance()
                self._emit(TokenKind.OR, '||', start_line, start_col)
                return
            if two == '..':
                self._advance()
                self._advance()
                self._emit(TokenKind.DOT_DOT, '..', start_line, start_col)
                return

        # Single-character operators and punctuation
        self._advance()
        match ch:
            case '+':
                self._emit(TokenKind.PLUS, '+', start_line, start_col)
            case '-':
                self._emit(TokenKind.MINUS, '-', start_line, start_col)
            case '*':
                self._emit(TokenKind.STAR, '*', start_line, start_col)
            case '/':
                self._emit(TokenKind.SLASH, '/', start_line, start_col)
            case '%':
                self._emit(TokenKind.PERCENT, '%', start_line, start_col)
            case '<':
                self._emit(TokenKind.LESS, '<', start_line, start_col)
            case '>':
                self._emit(TokenKind.GREATER, '>', start_line, start_col)
            case '!':
                self._emit(TokenKind.BANG, '!', start_line, start_col)
            case '=':
                self._emit(TokenKind.ASSIGN, '=', start_line, start_col)
            case '.':
                self._emit(TokenKind.DOT, '.', start_line, start_col)
            case '(':
                self.bracket_depth += 1
                self._emit(TokenKind.LPAREN, '(', start_line, start_col)
            case ')':
                self.bracket_depth = max(0, self.bracket_depth - 1)
                self._emit(TokenKind.RPAREN, ')', start_line, start_col)
            case '[':
                self.bracket_depth += 1
                self._emit(TokenKind.LBRACKET, '[', start_line, start_col)
            case ']':
                self.bracket_depth = max(0, self.bracket_depth - 1)
                self._emit(TokenKind.RBRACKET, ']', start_line, start_col)
            case ',':
                self._emit(TokenKind.COMMA, ',', start_line, start_col)
            case ':':
                self._emit(TokenKind.COLON, ':', start_line, start_col)
            case '|':
                self._emit(TokenKind.PIPE, '|', start_line, start_col)
            case _:
                self._error(f"unexpected character: {ch!r}", start_line, start_col)
