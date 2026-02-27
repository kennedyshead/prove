"""Parser for the Prove programming language.

Transforms a token stream into an AST using a Pratt expression parser
for expressions and recursive descent for declarations.
"""

from __future__ import annotations

from prove.ast_nodes import (
    AlgebraicTypeDef,
    Assignment,
    BinaryExpr,
    BindingPattern,
    BooleanLit,
    CallExpr,
    CharLit,
    ComptimeExpr,
    ConstantDef,
    DecimalLit,
    Declaration,
    Expr,
    ExprStmt,
    FailPropExpr,
    FieldDef,
    FieldExpr,
    FunctionDef,
    GenericType,
    IdentifierExpr,
    IfExpr,
    ImportDecl,
    ImportItem,
    IndexExpr,
    IntegerLit,
    InvariantNetwork,
    LambdaExpr,
    ListLiteral,
    LiteralPattern,
    MainDef,
    MatchArm,
    MatchExpr,
    ModifiedType,
    Module,
    ModuleDecl,
    NearMiss,
    Param,
    Pattern,
    PipeExpr,
    ProofBlock,
    ProofObligation,
    RecordTypeDef,
    RefinementTypeDef,
    RegexLit,
    SimpleType,
    Stmt,
    StringInterp,
    StringLit,
    TripleStringLit,
    TypeBody,
    TypeDef,
    TypeExpr,
    TypeIdentifierExpr,
    TypeModifier,
    UnaryExpr,
    ValidExpr,
    VarDecl,
    Variant,
    VariantPattern,
    WildcardPattern,
)
from prove.errors import CompileError, Diagnostic, DiagnosticLabel, Severity
from prove.source import Span
from prove.tokens import Token, TokenKind

# ── Binding powers for Pratt parser ─────────────────────────────

# (left_bp, right_bp) for infix operators
_INFIX_BP: dict[TokenKind, tuple[int, int]] = {
    TokenKind.PIPE_ARROW: (1, 2),
    TokenKind.OR: (3, 4),
    TokenKind.AND: (5, 6),
    TokenKind.EQUAL: (7, 8),
    TokenKind.NOT_EQUAL: (7, 8),
    TokenKind.LESS: (7, 8),
    TokenKind.GREATER: (7, 8),
    TokenKind.LESS_EQUAL: (7, 8),
    TokenKind.GREATER_EQUAL: (7, 8),
    TokenKind.DOT_DOT: (9, 10),
    TokenKind.PLUS: (11, 12),
    TokenKind.MINUS: (11, 12),
    TokenKind.STAR: (13, 14),
    TokenKind.SLASH: (13, 14),
    TokenKind.PERCENT: (13, 14),
}

_PREFIX_BP = 15  # right bp for unary ! and -
_POSTFIX_BP = 17  # left bp for !, ., (), []

_VERBS = frozenset({
    TokenKind.TRANSFORMS, TokenKind.INPUTS,
    TokenKind.OUTPUTS, TokenKind.VALIDATES,
})

_OP_STRINGS: dict[TokenKind, str] = {
    TokenKind.PLUS: '+', TokenKind.MINUS: '-', TokenKind.STAR: '*',
    TokenKind.SLASH: '/', TokenKind.PERCENT: '%',
    TokenKind.EQUAL: '==', TokenKind.NOT_EQUAL: '!=',
    TokenKind.LESS: '<', TokenKind.GREATER: '>',
    TokenKind.LESS_EQUAL: '<=', TokenKind.GREATER_EQUAL: '>=',
    TokenKind.AND: '&&', TokenKind.OR: '||',
    TokenKind.DOT_DOT: '..', TokenKind.PIPE_ARROW: '|>',
}


class Parser:
    """Parses a list of tokens into a Prove AST."""

    def __init__(self, tokens: list[Token], filename: str = "<stdin>") -> None:
        self.tokens = tokens
        self.pos = 0
        self.filename = filename
        self.diagnostics: list[Diagnostic] = []

    # ── Token access ─────────────────────────────────────────────

    def _current(self) -> Token:
        if self.pos < len(self.tokens):
            return self.tokens[self.pos]
        return self.tokens[-1]  # EOF

    def _peek(self, offset: int = 0) -> Token:
        idx = self.pos + offset
        if idx < len(self.tokens):
            return self.tokens[idx]
        return self.tokens[-1]

    def _at(self, kind: TokenKind) -> bool:
        return self._current().kind == kind

    def _at_any(self, *kinds: TokenKind) -> bool:
        return self._current().kind in kinds

    def _advance(self) -> Token:
        tok = self._current()
        if self.pos < len(self.tokens) - 1:
            self.pos += 1
        return tok

    def _expect(self, kind: TokenKind) -> Token:
        if self._current().kind == kind:
            return self._advance()
        tok = self._current()
        self._error(f"expected {kind.name}, got {tok.kind.name} ({tok.value!r})", tok.span)
        return tok

    def _skip_newlines(self) -> None:
        while self._at(TokenKind.NEWLINE):
            self._advance()

    def _error(self, message: str, span: Span) -> None:
        self.diagnostics.append(
            Diagnostic(
                severity=Severity.ERROR,
                code="E200",
                message=message,
                labels=[DiagnosticLabel(span=span, message="")],
            )
        )

    def _span(self, start: Span, end: Span) -> Span:
        """Build a Span from a start span to an end span."""
        return Span(
            self.filename,
            start.start_line, start.start_col,
            end.end_line, end.end_col,
        )

    def _synchronize(self) -> None:
        """Skip tokens until we find a reasonable recovery point."""
        while not self._at(TokenKind.EOF):
            if self._at(TokenKind.NEWLINE) and not self._is_indented():
                self._advance()
                return
            if self._at(TokenKind.DEDENT):
                return
            self._advance()

    def _is_indented(self) -> bool:
        """Check if we're inside an indented block."""
        # Look ahead past the newline to see if next is INDENT or at top level
        idx = self.pos + 1
        while idx < len(self.tokens) and self.tokens[idx].kind == TokenKind.NEWLINE:
            idx += 1
        return idx < len(self.tokens) and self.tokens[idx].kind == TokenKind.INDENT

    # ── Top-level parsing ────────────────────────────────────────

    def parse(self) -> Module:
        """Parse the entire token stream into a Module."""
        declarations: list[Declaration] = []
        self._skip_newlines()

        while not self._at(TokenKind.EOF):
            try:
                decl = self._parse_declaration()
                if decl is not None:
                    declarations.append(decl)
            except _ParseError:
                self._synchronize()
            self._skip_newlines()

        end = self._current().span
        span = Span(
            self.filename, 1, 1, end.end_line, end.end_col,
        )
        if self.diagnostics:
            raise CompileError(self.diagnostics)
        return Module(declarations=declarations, span=span)

    def _parse_declaration(self) -> Declaration | None:
        """Parse a single top-level declaration."""
        self._skip_newlines()

        # Collect doc comments
        doc_lines: list[str] = []
        while self._at(TokenKind.DOC_COMMENT):
            doc_lines.append(self._advance().value)
            self._skip_newlines()
        doc_comment = '\n'.join(doc_lines) if doc_lines else None

        tok = self._current()

        if tok.kind in _VERBS:
            return self._parse_function_def(doc_comment)
        if tok.kind == TokenKind.MAIN:
            return self._parse_main_def(doc_comment)
        if tok.kind == TokenKind.TYPE:
            return self._parse_type_def()
        if tok.kind == TokenKind.WITH:
            return self._parse_import_decl()
        if tok.kind == TokenKind.MODULE:
            return self._parse_module_decl()
        if tok.kind == TokenKind.INVARIANT_NETWORK:
            return self._parse_invariant_network()
        if tok.kind == TokenKind.CONSTANT_IDENTIFIER:
            return self._parse_constant_def()

        if tok.kind == TokenKind.EOF:
            return None

        self._error(f"unexpected token at module level: {tok.kind.name} ({tok.value!r})", tok.span)
        raise _ParseError

    # ── Function definitions ─────────────────────────────────────

    def _parse_function_def(self, doc_comment: str | None) -> FunctionDef:
        start = self._current().span
        verb_tok = self._advance()
        verb = verb_tok.value

        name_tok = self._expect(TokenKind.IDENTIFIER)
        name = name_tok.value

        params = self._parse_param_list()

        return_type = self._try_parse_return_type()
        can_fail = False
        if self._at(TokenKind.BANG):
            can_fail = True
            self._advance()

        self._skip_newlines()

        # Parse annotations — may be inside an INDENT block
        ensures, requires, proof = [], [], None
        why_not, chosen, near_misses = [], None, []
        know, assume, believe = [], [], []
        intent = None
        satisfies: list[str] = []

        # Skip INDENT if annotations/from are indented under the function
        in_indent = False
        if self._at(TokenKind.INDENT):
            in_indent = True
            self._advance()

        while not self._at(TokenKind.FROM) and not self._at(TokenKind.EOF):
            if self._at(TokenKind.ENSURES):
                self._advance()
                ensures.append(self._parse_expression(0))
            elif self._at(TokenKind.REQUIRES):
                self._advance()
                requires.append(self._parse_expression(0))
            elif self._at(TokenKind.PROOF):
                proof = self._parse_proof_block()
            elif self._at(TokenKind.WHY_NOT):
                self._advance()
                self._expect(TokenKind.COLON)
                why_not.append(self._expect(TokenKind.STRING_LIT).value)
            elif self._at(TokenKind.CHOSEN):
                self._advance()
                self._expect(TokenKind.COLON)
                chosen = self._expect(TokenKind.STRING_LIT).value
            elif self._at(TokenKind.NEAR_MISS):
                self._advance()
                self._expect(TokenKind.COLON)
                nm_input = self._parse_expression(0)
                self._expect(TokenKind.FAT_ARROW)
                nm_expected = self._parse_expression(0)
                near_misses.append(NearMiss(nm_input, nm_expected, nm_input.span))
            elif self._at(TokenKind.KNOW):
                self._advance()
                self._expect(TokenKind.COLON)
                know.append(self._parse_expression(0))
            elif self._at(TokenKind.ASSUME):
                self._advance()
                self._expect(TokenKind.COLON)
                assume.append(self._parse_expression(0))
            elif self._at(TokenKind.BELIEVE):
                self._advance()
                self._expect(TokenKind.COLON)
                believe.append(self._parse_expression(0))
            elif self._at(TokenKind.INTENT):
                self._advance()
                self._expect(TokenKind.COLON)
                intent = self._expect(TokenKind.STRING_LIT).value
            elif self._at(TokenKind.SATISFIES):
                self._advance()
                satisfies.append(self._expect(TokenKind.TYPE_IDENTIFIER).value)
            else:
                break
            self._skip_newlines()

        self._expect(TokenKind.FROM)
        self._skip_newlines()
        body = self._parse_body()

        # If we entered an indent block for annotations/from, consume its DEDENT
        if in_indent and self._at(TokenKind.DEDENT):
            self._advance()

        end = self._current().span
        span = self._span(start, end)
        return FunctionDef(
            verb=verb, name=name, params=params,
            return_type=return_type, can_fail=can_fail,
            ensures=ensures, requires=requires, proof=proof,
            why_not=why_not, chosen=chosen, near_misses=near_misses,
            know=know, assume=assume, believe=believe,
            intent=intent, satisfies=satisfies,
            body=body, doc_comment=doc_comment, span=span,
        )

    def _parse_main_def(self, doc_comment: str | None) -> MainDef:
        start = self._current().span
        self._advance()  # 'main'
        self._expect(TokenKind.LPAREN)
        self._expect(TokenKind.RPAREN)

        return_type = self._try_parse_return_type()
        can_fail = False
        if self._at(TokenKind.BANG):
            can_fail = True
            self._advance()

        self._skip_newlines()
        in_indent = False
        if self._at(TokenKind.INDENT):
            in_indent = True
            self._advance()
        self._expect(TokenKind.FROM)
        self._skip_newlines()
        body = self._parse_body()

        if in_indent and self._at(TokenKind.DEDENT):
            self._advance()

        end = self._current().span
        span = self._span(start, end)
        return MainDef(
            return_type=return_type, can_fail=can_fail,
            body=body, doc_comment=doc_comment, span=span,
        )

    def _parse_param_list(self) -> list[Param]:
        self._expect(TokenKind.LPAREN)
        params: list[Param] = []
        while not self._at(TokenKind.RPAREN) and not self._at(TokenKind.EOF):
            if params:
                self._expect(TokenKind.COMMA)
            param = self._parse_param()
            params.append(param)
        self._expect(TokenKind.RPAREN)
        return params

    def _parse_param(self) -> Param:
        start = self._current().span
        name_tok = self._expect(TokenKind.IDENTIFIER)
        type_expr = self._parse_type_expr()
        constraint = None
        if self._at(TokenKind.WHERE):
            self._advance()
            constraint = self._parse_refinement_constraint()
        end = self._current().span
        return Param(name_tok.value, type_expr, constraint,
                     self._span(start, end))

    def _try_parse_return_type(self) -> TypeExpr | None:
        """Try to parse a return type. Returns None if next token isn't a type start."""
        if self._at(TokenKind.TYPE_IDENTIFIER):
            return self._parse_type_expr()
        return None

    # ── Proof blocks ─────────────────────────────────────────────

    def _parse_proof_block(self) -> ProofBlock:
        start = self._current().span
        self._advance()  # 'proof'
        self._skip_newlines()

        obligations: list[ProofObligation] = []
        if self._at(TokenKind.INDENT):
            self._advance()
            while not self._at(TokenKind.DEDENT) and not self._at(TokenKind.EOF):
                self._skip_newlines()
                if self._at(TokenKind.DEDENT) or self._at(TokenKind.EOF):
                    break
                obl = self._parse_proof_obligation()
                obligations.append(obl)
                self._skip_newlines()
            if self._at(TokenKind.DEDENT):
                self._advance()
        else:
            # Inline single obligation
            obl = self._parse_proof_obligation()
            obligations.append(obl)

        end = self._current().span
        return ProofBlock(obligations,
                          self._span(start, end))

    def _parse_proof_obligation(self) -> ProofObligation:
        start = self._current().span
        name_tok = self._expect(TokenKind.IDENTIFIER)
        self._expect(TokenKind.COLON)

        # Collect proof text until next obligation name or DEDENT
        text_parts: list[str] = []
        while not self._at(TokenKind.DEDENT) and not self._at(TokenKind.EOF):
            # Check if this is the start of a new obligation (identifier followed by colon)
            if (self._at(TokenKind.IDENTIFIER)
                    and self._peek(1).kind == TokenKind.COLON
                    and not self._peek(1).value == ':'):
                # Look ahead: if after the colon there's text (not a type), it's a new obligation
                break
            tok = self._advance()
            if tok.kind == TokenKind.NEWLINE:
                # Don't break on newlines inside proof text
                continue
            text_parts.append(tok.value)

        text = ' '.join(text_parts).strip()
        # Clean up multiple spaces
        while '  ' in text:
            text = text.replace('  ', ' ')
        end = self._current().span
        return ProofObligation(name_tok.value, text,
                               self._span(start, end))

    # ── Type definitions ─────────────────────────────────────────

    def _parse_type_def(self) -> TypeDef:
        start = self._current().span
        self._advance()  # 'type'
        name_tok = self._expect(TokenKind.TYPE_IDENTIFIER)
        name = name_tok.value

        type_params: list[str] = []
        if self._at(TokenKind.LESS):
            self._advance()
            while not self._at(TokenKind.GREATER) and not self._at(TokenKind.EOF):
                if type_params:
                    self._expect(TokenKind.COMMA)
                type_params.append(self._expect(TokenKind.TYPE_IDENTIFIER).value)
            self._expect(TokenKind.GREATER)

        self._expect(TokenKind.IS)
        self._skip_newlines()

        body = self._parse_type_body()

        end = self._current().span
        span = self._span(start, end)
        return TypeDef(name=name, type_params=type_params, body=body, span=span)

    def _parse_type_body(self) -> TypeBody:
        """Determine and parse the type body kind."""
        # Check for indented block (record or multiline algebraic)
        if self._at(TokenKind.INDENT):
            return self._parse_indented_type_body()

        # Inline: either refinement, algebraic, or single-variant algebraic
        return self._parse_inline_type_body()

    def _parse_indented_type_body(self) -> TypeBody:
        """Parse type body inside an indented block."""
        self._advance()  # INDENT
        self._skip_newlines()

        # Peek to determine: if first token is identifier (lowercase) followed by type,
        # it's a record. If CamelCase, it's algebraic.
        first = self._current()

        if first.kind == TokenKind.IDENTIFIER:
            # Record type
            fields: list[FieldDef] = []
            while not self._at(TokenKind.DEDENT) and not self._at(TokenKind.EOF):
                self._skip_newlines()
                if self._at(TokenKind.DEDENT) or self._at(TokenKind.EOF):
                    break
                field = self._parse_field_def()
                fields.append(field)
                self._skip_newlines()
            if self._at(TokenKind.DEDENT):
                self._advance()
            start = fields[0].span if fields else first.span
            end = fields[-1].span if fields else first.span
            return RecordTypeDef(fields, self._span(start, end))

        if first.kind == TokenKind.TYPE_IDENTIFIER:
            # Could be multiline algebraic or single variant
            return self._parse_multiline_algebraic()

        self._error(
            f"expected field or variant name in type body, got {first.kind.name}",
            first.span,
        )
        raise _ParseError

    def _parse_multiline_algebraic(self) -> AlgebraicTypeDef:
        """Parse multiline algebraic variants inside an indented block."""
        variants: list[Variant] = []

        while not self._at(TokenKind.DEDENT) and not self._at(TokenKind.EOF):
            self._skip_newlines()
            if self._at(TokenKind.DEDENT) or self._at(TokenKind.EOF):
                break
            # Skip leading | for multiline variants
            if self._at(TokenKind.PIPE):
                self._advance()
            variant = self._parse_variant()
            variants.append(variant)
            self._skip_newlines()

        if self._at(TokenKind.DEDENT):
            self._advance()

        start = variants[0].span if variants else self._current().span
        end = variants[-1].span if variants else self._current().span
        return AlgebraicTypeDef(variants, self._span(start, end))

    def _parse_inline_type_body(self) -> TypeBody:
        """Parse an inline type body (refinement or algebraic)."""
        if not self._at(TokenKind.TYPE_IDENTIFIER):
            tok = self._current()
            self._error(f"expected type body, got {tok.kind.name}", tok.span)
            raise _ParseError

        start = self._current().span

        # Detect refinement vs algebraic:
        # Refinement: TypeExpr 'where' expr  (e.g., Integer where >= 0)
        # Algebraic: Variant ['(' fields ')'] ['|' Variant ...]
        # Key difference: after a type name, if we see '(' with identifier+Type inside
        # that's variant fields. If we see ':[' that's a modified type for refinement.
        # If we see '<' that's generic type for refinement.
        # If we see 'where' directly, that's refinement.

        # Peek to see if this looks like a refinement base type followed by 'where'
        # or a modified/generic type followed by 'where'
        if self._is_refinement_type():
            type_expr = self._parse_type_expr()
            self._expect(TokenKind.WHERE)
            constraint = self._parse_refinement_constraint()
            end = self._current().span
            return RefinementTypeDef(type_expr, constraint,
                                    self._span(start, end))

        # Algebraic type: parse variants
        first_variant = self._parse_variant()
        variants = [first_variant]

        while self._at(TokenKind.PIPE):
            self._advance()
            self._skip_newlines()
            variant = self._parse_variant()
            variants.append(variant)

        # Check for multiline continuation
        self._skip_newlines()
        if self._at(TokenKind.INDENT):
            self._advance()
            while not self._at(TokenKind.DEDENT) and not self._at(TokenKind.EOF):
                self._skip_newlines()
                if self._at(TokenKind.DEDENT) or self._at(TokenKind.EOF):
                    break
                if self._at(TokenKind.PIPE):
                    self._advance()
                variant = self._parse_variant()
                variants.append(variant)
                self._skip_newlines()
            if self._at(TokenKind.DEDENT):
                self._advance()

        end = variants[-1].span
        return AlgebraicTypeDef(variants, self._span(start, end))

    def _is_refinement_type(self) -> bool:
        """Look ahead to determine if the current position starts a refinement type."""
        # Skip past the type name
        idx = self.pos + 1
        # Check for :[ (modified type) or < (generic type) or just 'where'
        while idx < len(self.tokens):
            tok = self.tokens[idx]
            if tok.kind == TokenKind.WHERE:
                return True
            if (tok.kind == TokenKind.COLON
                    and idx + 1 < len(self.tokens)
                    and self.tokens[idx + 1].kind == TokenKind.LBRACKET):
                # Modified type — skip past :[...]
                idx += 2  # skip : and [
                depth = 1
                while idx < len(self.tokens) and depth > 0:
                    if self.tokens[idx].kind == TokenKind.LBRACKET:
                        depth += 1
                    elif self.tokens[idx].kind == TokenKind.RBRACKET:
                        depth -= 1
                    idx += 1
                continue
            if tok.kind == TokenKind.LESS:
                # Generic type — skip past <...>
                idx += 1
                depth = 1
                while idx < len(self.tokens) and depth > 0:
                    if self.tokens[idx].kind == TokenKind.LESS:
                        depth += 1
                    elif self.tokens[idx].kind == TokenKind.GREATER:
                        depth -= 1
                    idx += 1
                continue
            # If we see ( or | or NEWLINE/EOF, it's algebraic
            if tok.kind in (TokenKind.LPAREN, TokenKind.PIPE, TokenKind.NEWLINE,
                            TokenKind.EOF, TokenKind.INDENT, TokenKind.DEDENT):
                return False
            idx += 1
        return False

    def _parse_refinement_constraint(self) -> Expr:
        """Parse a refinement constraint after 'where'.

        Handles shorthand like `>= 0` (implicit self) and `matches(...)` and `1..65535`.
        """
        _COMPARISON_OPS = {
            TokenKind.GREATER_EQUAL, TokenKind.LESS_EQUAL,
            TokenKind.GREATER, TokenKind.LESS,
            TokenKind.EQUAL, TokenKind.NOT_EQUAL,
        }
        if self._current().kind in _COMPARISON_OPS:
            # Shorthand: `>= 0` means `self >= 0`
            op_tok = self._advance()
            right = self._parse_expression(0)
            op_str = _OP_STRINGS.get(op_tok.kind, op_tok.value)
            return BinaryExpr(
                IdentifierExpr("self", op_tok.span), op_str, right,
                self._span(op_tok.span, right.span),
            )
        return self._parse_expression(0)

    def _type_expr_to_variant(self, te: TypeExpr) -> Variant:
        """Convert a parsed type expression back into a Variant node."""
        if isinstance(te, SimpleType):
            return Variant(te.name, [], te.span)
        if isinstance(te, GenericType):
            # This is actually a variant with fields like Variant(field Type)
            # But GenericType uses <>, not (). So this is a unit variant.
            return Variant(te.name, [], te.span)
        return Variant("unknown", [], te.span)

    def _parse_variant(self) -> Variant:
        """Parse a single algebraic variant."""
        start = self._current().span
        name_tok = self._expect(TokenKind.TYPE_IDENTIFIER)

        fields: list[FieldDef] = []
        if self._at(TokenKind.LPAREN):
            self._advance()
            while not self._at(TokenKind.RPAREN) and not self._at(TokenKind.EOF):
                if fields:
                    self._expect(TokenKind.COMMA)
                field = self._parse_field_def()
                fields.append(field)
            self._expect(TokenKind.RPAREN)

        end = self._current().span
        return Variant(name_tok.value, fields,
                       self._span(start, end))

    def _parse_field_def(self) -> FieldDef:
        """Parse a field definition: name Type [where expr]."""
        start = self._current().span
        name_tok = self._expect(TokenKind.IDENTIFIER)
        type_expr = self._parse_type_expr()
        constraint = None
        if self._at(TokenKind.WHERE):
            self._advance()
            constraint = self._parse_refinement_constraint()
        end = self._current().span
        return FieldDef(name_tok.value, type_expr, constraint,
                        self._span(start, end))

    # ── Type expressions ─────────────────────────────────────────

    def _parse_type_expr(self) -> TypeExpr:
        """Parse a type expression: SimpleType, GenericType<A, B>, or ModifiedType:[mods]."""
        start = self._current().span
        name_tok = self._expect(TokenKind.TYPE_IDENTIFIER)
        name = name_tok.value

        # Modified type: Type:[mods]
        if self._at(TokenKind.COLON) and self._peek(1).kind == TokenKind.LBRACKET:
            self._advance()  # :
            self._advance()  # [
            modifiers: list[TypeModifier] = []
            while not self._at(TokenKind.RBRACKET) and not self._at(TokenKind.EOF):
                mod = self._parse_type_modifier()
                modifiers.append(mod)
            self._expect(TokenKind.RBRACKET)
            end = self._current().span
            return ModifiedType(name, modifiers,
                                self._span(start, end))

        # Generic type: Type<A, B>
        if self._at(TokenKind.LESS):
            self._advance()
            args: list[TypeExpr] = []
            while not self._at(TokenKind.GREATER) and not self._at(TokenKind.EOF):
                if args:
                    self._expect(TokenKind.COMMA)
                args.append(self._parse_type_expr())
            self._expect(TokenKind.GREATER)
            end = self._current().span
            return GenericType(name, args,
                               self._span(start, end))

        return SimpleType(name, name_tok.span)

    def _parse_type_modifier(self) -> TypeModifier:
        """Parse a type modifier inside :[ ]."""
        start = self._current().span
        tok = self._current()

        # Named modifier: Name:value
        if tok.kind == TokenKind.TYPE_IDENTIFIER and self._peek(1).kind == TokenKind.COLON:
            mod_name = self._advance().value
            self._advance()  # :
            val_tok = self._advance()
            return TypeModifier(mod_name, val_tok.value, start)

        # Positional modifier
        val_tok = self._advance()
        return TypeModifier(None, val_tok.value, start)

    # ── Import declarations ──────────────────────────────────────

    def _parse_import_decl(self) -> ImportDecl:
        start = self._current().span
        self._advance()  # 'with'
        module_tok = self._expect(TokenKind.TYPE_IDENTIFIER)
        self._expect(TokenKind.USE)

        items: list[ImportItem] = []
        while True:
            item = self._parse_import_item()
            items.append(item)
            if not self._at(TokenKind.COMMA):
                break
            self._advance()

        end = self._current().span
        return ImportDecl(module_tok.value, items,
                          self._span(start, end))

    def _parse_import_item(self) -> ImportItem:
        start = self._current().span
        verb = None
        if self._current().kind in _VERBS:
            verb = self._advance().value
        name_tok = self._expect(TokenKind.IDENTIFIER)
        return ImportItem(verb, name_tok.value, start)

    # ── Module declarations ──────────────────────────────────────

    def _parse_module_decl(self) -> ModuleDecl:
        start = self._current().span
        self._advance()  # 'module'
        name_tok = self._expect(TokenKind.TYPE_IDENTIFIER)
        self._skip_newlines()

        narrative = None
        temporal = None
        body: list[Declaration] = []

        if self._at(TokenKind.INDENT):
            self._advance()
            while not self._at(TokenKind.DEDENT) and not self._at(TokenKind.EOF):
                self._skip_newlines()
                if self._at(TokenKind.DEDENT) or self._at(TokenKind.EOF):
                    break

                if self._at(TokenKind.NARRATIVE):
                    self._advance()
                    self._expect(TokenKind.COLON)
                    if self._at(TokenKind.TRIPLE_STRING_LIT):
                        narrative = self._advance().value
                    else:
                        narrative = self._expect(TokenKind.STRING_LIT).value
                elif self._at(TokenKind.TEMPORAL):
                    self._advance()
                    self._expect(TokenKind.COLON)
                    steps = [self._expect(TokenKind.IDENTIFIER).value]
                    while self._at(TokenKind.ARROW):
                        self._advance()
                        steps.append(self._expect(TokenKind.IDENTIFIER).value)
                    temporal = steps
                else:
                    # Parse nested declarations
                    doc_lines: list[str] = []
                    while self._at(TokenKind.DOC_COMMENT):
                        doc_lines.append(self._advance().value)
                        self._skip_newlines()
                    doc = '\n'.join(doc_lines) if doc_lines else None

                    if self._current().kind in _VERBS:
                        body.append(self._parse_function_def(doc))
                    elif self._at(TokenKind.MAIN):
                        body.append(self._parse_main_def(doc))
                    elif self._at(TokenKind.TYPE):
                        body.append(self._parse_type_def())
                    else:
                        tok = self._current()
                        self._error(
                            f"unexpected token in module body: {tok.kind.name}",
                            tok.span,
                        )
                        self._advance()

                self._skip_newlines()

            if self._at(TokenKind.DEDENT):
                self._advance()

        end = self._current().span
        return ModuleDecl(name_tok.value, narrative, temporal, body,
                          self._span(start, end))

    # ── Invariant network ────────────────────────────────────────

    def _parse_invariant_network(self) -> InvariantNetwork:
        start = self._current().span
        self._advance()  # 'invariant_network'
        name_tok = self._expect(TokenKind.TYPE_IDENTIFIER)
        self._skip_newlines()

        constraints: list[Expr] = []
        if self._at(TokenKind.INDENT):
            self._advance()
            while not self._at(TokenKind.DEDENT) and not self._at(TokenKind.EOF):
                self._skip_newlines()
                if self._at(TokenKind.DEDENT) or self._at(TokenKind.EOF):
                    break
                expr = self._parse_expression(0)
                constraints.append(expr)
                self._skip_newlines()
            if self._at(TokenKind.DEDENT):
                self._advance()

        end = self._current().span
        return InvariantNetwork(name_tok.value, constraints,
                                self._span(start, end))

    # ── Constant definitions ─────────────────────────────────────

    def _parse_constant_def(self) -> ConstantDef:
        start = self._current().span
        name_tok = self._advance()  # CONSTANT_IDENTIFIER

        type_expr = None
        if self._at(TokenKind.AS):
            self._advance()
            type_expr = self._parse_type_expr()

        self._expect(TokenKind.ASSIGN)

        if self._at(TokenKind.COMPTIME):
            value = self._parse_comptime_expr()
        else:
            value = self._parse_expression(0)

        end = self._current().span
        return ConstantDef(name_tok.value, type_expr, value,
                           self._span(start, end))

    def _parse_comptime_expr(self) -> ComptimeExpr:
        start = self._current().span
        self._advance()  # 'comptime'
        self._skip_newlines()

        stmts: list[Stmt] = []
        if self._at(TokenKind.INDENT):
            self._advance()
            while not self._at(TokenKind.DEDENT) and not self._at(TokenKind.EOF):
                self._skip_newlines()
                if self._at(TokenKind.DEDENT) or self._at(TokenKind.EOF):
                    break
                stmt = self._parse_statement()
                stmts.append(stmt)
                self._skip_newlines()
            if self._at(TokenKind.DEDENT):
                self._advance()
        else:
            stmt = self._parse_statement()
            stmts.append(stmt)

        end = self._current().span
        return ComptimeExpr(stmts, self._span(start, end))

    # ── Body parsing ─────────────────────────────────────────────

    def _parse_body(self) -> list[Stmt | MatchExpr]:
        """Parse a function body (indented block of statements and/or match arms)."""
        stmts: list[Stmt | MatchExpr] = []
        if not self._at(TokenKind.INDENT):
            # Single-line body
            stmt = self._parse_statement()
            stmts.append(stmt)
            return stmts

        self._advance()  # INDENT
        while not self._at(TokenKind.DEDENT) and not self._at(TokenKind.EOF):
            self._skip_newlines()
            if self._at(TokenKind.DEDENT) or self._at(TokenKind.EOF):
                break

            # Check for implicit match arms
            if self._looks_like_match_arm():
                arms = self._parse_implicit_match_arms()
                span = arms[0].span if arms else self._current().span
                stmts.append(MatchExpr(subject=None, arms=arms, span=span))
                continue

            stmt = self._parse_statement()
            stmts.append(stmt)
            self._skip_newlines()

        if self._at(TokenKind.DEDENT):
            self._advance()
        return stmts

    def _looks_like_match_arm(self) -> bool:
        """Check if current position looks like an implicit match arm."""
        tok = self._current()
        # Pattern starts: TypeIdentifier, literal, or _
        if tok.kind == TokenKind.TYPE_IDENTIFIER:
            # Look for => after variant pattern
            return self._scan_for_fat_arrow()
        if tok.kind == TokenKind.IDENTIFIER and tok.value == '_':
            return self._peek(1).kind == TokenKind.FAT_ARROW
        if tok.kind in (TokenKind.INTEGER_LIT, TokenKind.DECIMAL_LIT,
                        TokenKind.STRING_LIT, TokenKind.BOOLEAN_LIT):
            return self._peek(1).kind == TokenKind.FAT_ARROW
        return False

    def _scan_for_fat_arrow(self) -> bool:
        """Scan ahead from a TypeIdentifier to check for =>."""
        idx = self.pos + 1
        # Skip past possible variant fields: TypeId(args) or just TypeId
        if idx < len(self.tokens) and self.tokens[idx].kind == TokenKind.LPAREN:
            depth = 1
            idx += 1
            while idx < len(self.tokens) and depth > 0:
                if self.tokens[idx].kind == TokenKind.LPAREN:
                    depth += 1
                elif self.tokens[idx].kind == TokenKind.RPAREN:
                    depth -= 1
                idx += 1
        # After variant, should see =>
        return idx < len(self.tokens) and self.tokens[idx].kind == TokenKind.FAT_ARROW

    def _parse_implicit_match_arms(self) -> list[MatchArm]:
        """Parse a sequence of match arms for implicit match."""
        arms: list[MatchArm] = []
        while not self._at(TokenKind.DEDENT) and not self._at(TokenKind.EOF):
            self._skip_newlines()
            if self._at(TokenKind.DEDENT) or self._at(TokenKind.EOF):
                break
            if not self._looks_like_match_arm():
                break
            arm = self._parse_match_arm()
            arms.append(arm)
            self._skip_newlines()
        return arms

    # ── Statements ───────────────────────────────────────────────

    def _parse_statement(self) -> Stmt:
        """Parse a statement: var decl, assignment, or expression."""
        # Variable declaration: identifier 'as' Type '=' expr
        if (self._at(TokenKind.IDENTIFIER)
                and self._peek(1).kind == TokenKind.AS):
            return self._parse_var_decl()

        # Assignment: identifier '=' expr (but not ==)
        if (self._at(TokenKind.IDENTIFIER)
                and self._peek(1).kind == TokenKind.ASSIGN):
            return self._parse_assignment()

        # Expression statement
        expr = self._parse_expression(0)
        return ExprStmt(expr, expr.span)

    def _parse_var_decl(self) -> VarDecl:
        start = self._current().span
        name_tok = self._advance()  # identifier
        self._advance()  # 'as'
        type_expr = self._parse_type_expr()
        self._expect(TokenKind.ASSIGN)
        value = self._parse_expression(0)
        end = value.span
        return VarDecl(name_tok.value, type_expr, value,
                       self._span(start, end))

    def _parse_assignment(self) -> Assignment:
        start = self._current().span
        name_tok = self._advance()
        self._advance()  # '='
        value = self._parse_expression(0)
        end = value.span
        return Assignment(name_tok.value, value,
                          self._span(start, end))

    # ── Pratt expression parser ──────────────────────────────────

    def _parse_expression(self, min_bp: int) -> Expr:
        """Parse an expression using Pratt parsing with binding powers."""
        left = self._parse_prefix()

        while True:
            tok = self._current()

            # Postfix operators: !, ., (), []
            if tok.kind == TokenKind.BANG and not self._is_prefix_bang():
                if _POSTFIX_BP < min_bp:
                    break
                self._advance()
                left = FailPropExpr(
                    left, self._span(left.span, tok.span),
                )
                continue

            if tok.kind == TokenKind.DOT:
                if _POSTFIX_BP < min_bp:
                    break
                self._advance()
                field_tok = self._expect(TokenKind.IDENTIFIER)
                left = FieldExpr(
                    left, field_tok.value,
                    self._span(left.span, field_tok.span),
                )
                continue

            if (tok.kind == TokenKind.LPAREN
                    and isinstance(left, (IdentifierExpr, TypeIdentifierExpr))):
                if _POSTFIX_BP < min_bp:
                    break
                left = self._parse_call_expr(left)
                continue

            if tok.kind == TokenKind.LBRACKET:
                if _POSTFIX_BP < min_bp:
                    break
                self._advance()
                index = self._parse_expression(0)
                self._expect(TokenKind.RBRACKET)
                left = IndexExpr(
                    left, index,
                    self._span(left.span, self._current().span),
                )
                continue

            # Generic type args after TypeIdentifier: Type<A, B>
            # In expression context, < after TypeIdentifier is generic args, not comparison
            if (tok.kind == TokenKind.LESS
                    and isinstance(left, TypeIdentifierExpr)):
                if _POSTFIX_BP < min_bp:
                    break
                # Try to parse as generic type args for a call
                # Save position for backtracking
                save_pos = self.pos
                try:
                    self._advance()  # <
                    args: list[TypeExpr] = [self._parse_type_expr()]
                    while self._at(TokenKind.COMMA):
                        self._advance()
                        args.append(self._parse_type_expr())
                    self._expect(TokenKind.GREATER)
                    # If followed by (, it's a call with type args, otherwise treat as type ref
                    if self._at(TokenKind.LPAREN):
                        # Build a GenericType-like expression and then parse call
                        # For now, fold into the left as a type identifier with generic args
                        pass
                    left = TypeIdentifierExpr(
                        left.name,
                        self._span(left.span, self._current().span),
                    )
                    continue
                except Exception:
                    self.pos = save_pos
                    # Fall through to infix

            # Infix operators
            if tok.kind in _INFIX_BP:
                left_bp, right_bp = _INFIX_BP[tok.kind]
                if left_bp < min_bp:
                    break
                op_tok = self._advance()
                self._skip_newlines()
                right = self._parse_expression(right_bp)
                op_str = _OP_STRINGS.get(op_tok.kind, op_tok.value)
                if op_tok.kind == TokenKind.PIPE_ARROW:
                    left = PipeExpr(
                        left, right,
                        self._span(left.span, right.span),
                    )
                else:
                    left = BinaryExpr(
                        left, op_str, right,
                        self._span(left.span, right.span),
                    )
                continue

            break

        return left

    def _is_prefix_bang(self) -> bool:
        """Check if ! at current position is prefix (unary not) rather than postfix (fail prop)."""
        # ! is prefix if previous token is an operator, keyword, or start of expression
        # In practice: if ! follows a value, it's postfix. Otherwise prefix.
        # Since we're in the infix loop, we already have a `left`, so ! is postfix.
        return False

    def _parse_prefix(self) -> Expr:
        """Parse a prefix expression (atom or unary operator)."""
        tok = self._current()

        # Unary operators
        if tok.kind == TokenKind.BANG:
            self._advance()
            operand = self._parse_expression(_PREFIX_BP)
            return UnaryExpr(
                '!', operand,
                self._span(tok.span, operand.span),
            )

        if tok.kind == TokenKind.MINUS:
            self._advance()
            operand = self._parse_expression(_PREFIX_BP)
            return UnaryExpr(
                '-', operand,
                self._span(tok.span, operand.span),
            )

        # Lambda: |params| body
        if tok.kind == TokenKind.PIPE:
            return self._parse_lambda()

        # Literals
        if tok.kind == TokenKind.INTEGER_LIT:
            self._advance()
            return IntegerLit(tok.value, tok.span)

        if tok.kind == TokenKind.DECIMAL_LIT:
            self._advance()
            return DecimalLit(tok.value, tok.span)

        if tok.kind == TokenKind.STRING_LIT:
            return self._parse_string_or_interp()

        if tok.kind == TokenKind.TRIPLE_STRING_LIT:
            self._advance()
            return TripleStringLit(tok.value, tok.span)

        if tok.kind == TokenKind.BOOLEAN_LIT:
            self._advance()
            return BooleanLit(tok.value == 'true', tok.span)

        if tok.kind == TokenKind.CHAR_LIT:
            self._advance()
            return CharLit(tok.value, tok.span)

        if tok.kind == TokenKind.REGEX_LIT:
            self._advance()
            return RegexLit(tok.value, tok.span)

        # Parenthesized expression
        if tok.kind == TokenKind.LPAREN:
            self._advance()
            expr = self._parse_expression(0)
            self._expect(TokenKind.RPAREN)
            return expr

        # List literal
        if tok.kind == TokenKind.LBRACKET:
            return self._parse_list_literal()

        # valid expression
        if tok.kind == TokenKind.VALID:
            return self._parse_valid_expr()

        # if expression
        if tok.kind == TokenKind.IF:
            return self._parse_if_expr()

        # match expression
        if tok.kind == TokenKind.MATCH:
            return self._parse_match_expr()

        # Identifiers
        if tok.kind == TokenKind.IDENTIFIER:
            self._advance()
            return IdentifierExpr(tok.value, tok.span)

        if tok.kind == TokenKind.TYPE_IDENTIFIER:
            self._advance()
            return TypeIdentifierExpr(tok.value, tok.span)

        if tok.kind == TokenKind.CONSTANT_IDENTIFIER:
            self._advance()
            return IdentifierExpr(tok.value, tok.span)

        self._error(f"unexpected token in expression: {tok.kind.name} ({tok.value!r})", tok.span)
        raise _ParseError

    def _parse_string_or_interp(self) -> Expr:
        """Parse a string literal or string interpolation."""
        start = self._current().span
        parts: list[Expr] = []

        # Collect STRING_LIT and INTERP_START/END sequences
        while self._at_any(TokenKind.STRING_LIT, TokenKind.INTERP_START):
            if self._at(TokenKind.STRING_LIT):
                tok = self._advance()
                parts.append(StringLit(tok.value, tok.span))
            elif self._at(TokenKind.INTERP_START):
                self._advance()  # INTERP_START
                expr = self._parse_expression(0)
                parts.append(expr)
                if self._at(TokenKind.INTERP_END):
                    self._advance()

        if len(parts) == 1 and isinstance(parts[0], StringLit):
            return parts[0]

        end = parts[-1].span if parts else start
        return StringInterp(parts, self._span(start, end))

    def _parse_call_expr(self, func: Expr) -> CallExpr:
        """Parse a function call: func(args)."""
        self._advance()  # (
        args: list[Expr] = []
        while not self._at(TokenKind.RPAREN) and not self._at(TokenKind.EOF):
            if args:
                self._expect(TokenKind.COMMA)
            args.append(self._parse_expression(0))
        end_tok = self._expect(TokenKind.RPAREN)
        return CallExpr(
            func, args, self._span(func.span, end_tok.span),
        )

    def _parse_list_literal(self) -> ListLiteral:
        start = self._current().span
        self._advance()  # [
        elements: list[Expr] = []
        while not self._at(TokenKind.RBRACKET) and not self._at(TokenKind.EOF):
            if elements:
                self._expect(TokenKind.COMMA)
            elements.append(self._parse_expression(0))
        end_tok = self._expect(TokenKind.RBRACKET)
        return ListLiteral(
            elements, self._span(start, end_tok.span),
        )

    def _parse_valid_expr(self) -> ValidExpr:
        start = self._current().span
        self._advance()  # 'valid'
        name_tok = self._expect(TokenKind.IDENTIFIER)
        args = None
        if self._at(TokenKind.LPAREN):
            self._advance()
            args = []
            while not self._at(TokenKind.RPAREN) and not self._at(TokenKind.EOF):
                if args:
                    self._expect(TokenKind.COMMA)
                args.append(self._parse_expression(0))
            self._expect(TokenKind.RPAREN)
        end = self._current().span
        return ValidExpr(name_tok.value, args,
                         self._span(start, end))

    def _parse_if_expr(self) -> IfExpr:
        start = self._current().span
        self._advance()  # 'if'
        condition = self._parse_expression(0)
        self._skip_newlines()

        then_body: list[Stmt] = []
        if self._at(TokenKind.INDENT):
            self._advance()
            while not self._at(TokenKind.DEDENT) and not self._at(TokenKind.EOF):
                self._skip_newlines()
                if self._at(TokenKind.DEDENT) or self._at(TokenKind.EOF):
                    break
                then_body.append(self._parse_statement())
                self._skip_newlines()
            if self._at(TokenKind.DEDENT):
                self._advance()
        else:
            then_body.append(self._parse_statement())

        self._skip_newlines()
        else_body: list[Stmt] = []
        if self._at(TokenKind.ELSE):
            self._advance()
            self._skip_newlines()
            if self._at(TokenKind.INDENT):
                self._advance()
                while not self._at(TokenKind.DEDENT) and not self._at(TokenKind.EOF):
                    self._skip_newlines()
                    if self._at(TokenKind.DEDENT) or self._at(TokenKind.EOF):
                        break
                    else_body.append(self._parse_statement())
                    self._skip_newlines()
                if self._at(TokenKind.DEDENT):
                    self._advance()
            else:
                else_body.append(self._parse_statement())

        end = self._current().span
        return IfExpr(condition, then_body, else_body,
                      self._span(start, end))

    def _parse_match_expr(self) -> MatchExpr:
        start = self._current().span
        self._advance()  # 'match'
        subject = self._parse_expression(0)
        self._skip_newlines()

        arms: list[MatchArm] = []
        if self._at(TokenKind.INDENT):
            self._advance()
            while not self._at(TokenKind.DEDENT) and not self._at(TokenKind.EOF):
                self._skip_newlines()
                if self._at(TokenKind.DEDENT) or self._at(TokenKind.EOF):
                    break
                arm = self._parse_match_arm()
                arms.append(arm)
                self._skip_newlines()
            if self._at(TokenKind.DEDENT):
                self._advance()
        else:
            # Inline match arms
            arm = self._parse_match_arm()
            arms.append(arm)

        end = self._current().span
        return MatchExpr(subject, arms,
                         self._span(start, end))

    def _parse_match_arm(self) -> MatchArm:
        start = self._current().span
        pattern = self._parse_pattern()
        self._expect(TokenKind.FAT_ARROW)
        self._skip_newlines()

        body: list[Stmt] = []
        if self._at(TokenKind.INDENT):
            self._advance()
            while not self._at(TokenKind.DEDENT) and not self._at(TokenKind.EOF):
                self._skip_newlines()
                if self._at(TokenKind.DEDENT) or self._at(TokenKind.EOF):
                    break
                body.append(self._parse_statement())
                self._skip_newlines()
            if self._at(TokenKind.DEDENT):
                self._advance()
        else:
            body.append(self._parse_statement())

        end = self._current().span
        return MatchArm(pattern, body,
                        self._span(start, end))

    def _parse_lambda(self) -> LambdaExpr:
        start = self._current().span
        self._advance()  # |
        params: list[str] = []
        while not self._at(TokenKind.PIPE) and not self._at(TokenKind.EOF):
            if params:
                self._expect(TokenKind.COMMA)
            params.append(self._expect(TokenKind.IDENTIFIER).value)
        self._expect(TokenKind.PIPE)
        body = self._parse_expression(0)
        return LambdaExpr(
            params, body, self._span(start, body.span),
        )

    # ── Patterns ─────────────────────────────────────────────────

    def _parse_pattern(self) -> Pattern:
        tok = self._current()

        if tok.kind == TokenKind.TYPE_IDENTIFIER:
            return self._parse_variant_pattern()

        if tok.kind == TokenKind.IDENTIFIER and tok.value == '_':
            self._advance()
            return WildcardPattern(tok.span)

        if tok.kind == TokenKind.IDENTIFIER:
            self._advance()
            return BindingPattern(tok.value, tok.span)

        if tok.kind in (TokenKind.INTEGER_LIT, TokenKind.DECIMAL_LIT,
                        TokenKind.STRING_LIT, TokenKind.BOOLEAN_LIT):
            self._advance()
            return LiteralPattern(tok.value, tok.span)

        self._error(f"expected pattern, got {tok.kind.name}", tok.span)
        raise _ParseError

    def _parse_variant_pattern(self) -> VariantPattern:
        start = self._current().span
        name_tok = self._advance()
        fields: list[Pattern] = []

        if self._at(TokenKind.LPAREN):
            self._advance()
            while not self._at(TokenKind.RPAREN) and not self._at(TokenKind.EOF):
                if fields:
                    self._expect(TokenKind.COMMA)
                fields.append(self._parse_pattern())
            self._expect(TokenKind.RPAREN)

        end = self._current().span
        return VariantPattern(name_tok.value, fields,
                              self._span(start, end))


class _ParseError(Exception):
    """Internal exception for parser error recovery."""
