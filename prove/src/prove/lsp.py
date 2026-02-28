"""Prove Language Server — pygls-based LSP for .prv files.

Provides diagnostics, hover, completion, go-to-definition,
document symbols, signature help, and formatting via stdio transport.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from lsprotocol import types as lsp
from pygls.lsp.server import LanguageServer

from prove.ast_nodes import (
    ConstantDef,
    FunctionDef,
    MainDef,
    Module,
    ModuleDecl,
    TypeDef,
)
from prove.checker import Checker
from prove.errors import CompileError, Severity
from prove.formatter import ProveFormatter
from prove.lexer import Lexer
from prove.parser import Parser
from prove.symbols import FunctionSignature, SymbolKind, SymbolTable
from prove.tokens import KEYWORDS, Token

# ── Conversion helpers ────────────────────────────────────────────

_SEVERITY_MAP = {
    Severity.ERROR: lsp.DiagnosticSeverity.Error,
    Severity.WARNING: lsp.DiagnosticSeverity.Warning,
    Severity.NOTE: lsp.DiagnosticSeverity.Information,
}

# Prove SymbolKind → LSP SymbolKind
_SYMBOL_KIND_MAP = {
    SymbolKind.FUNCTION: lsp.SymbolKind.Function,
    SymbolKind.TYPE: lsp.SymbolKind.Class,
    SymbolKind.CONSTANT: lsp.SymbolKind.Constant,
    SymbolKind.VARIABLE: lsp.SymbolKind.Variable,
    SymbolKind.PARAMETER: lsp.SymbolKind.Variable,
}

# All Prove keywords for completion
_KEYWORD_COMPLETIONS = sorted(KEYWORDS.keys())

# Built-in function names
_BUILTINS = [
    "println", "print", "readln", "len", "map", "filter", "reduce",
    "to_string", "clamp",
]


def span_to_range(span: object) -> lsp.Range:
    """Convert a 1-indexed Prove Span to a 0-indexed LSP Range."""
    sl = getattr(span, "start_line", 1)
    sc = getattr(span, "start_col", 1)
    el = getattr(span, "end_line", sl)
    ec = getattr(span, "end_col", sc)
    return lsp.Range(
        start=lsp.Position(line=sl - 1, character=sc - 1),
        end=lsp.Position(line=el - 1, character=ec),
    )


def _types_display(sig: FunctionSignature) -> str:
    """Format a function signature for display."""
    from prove.types import type_name
    params = ", ".join(
        f"{n}: {type_name(t)}" for n, t in zip(sig.param_names, sig.param_types)
    )
    ret = type_name(sig.return_type)
    verb = f"{sig.verb} " if sig.verb else ""
    fail = "!" if sig.can_fail else ""
    return f"{verb}{sig.name}({params}) {ret}{fail}"


# ── Per-document state ────────────────────────────────────────────


@dataclass
class DocumentState:
    """Cached analysis results for a single open document."""

    source: str = ""
    tokens: list[Token] = field(default_factory=list)
    module: Module | None = None
    symbols: SymbolTable | None = None
    diagnostics: list[lsp.Diagnostic] = field(default_factory=list)


# ── Server ────────────────────────────────────────────────────────

server = LanguageServer("prove-lsp", "0.1.0")
_state: dict[str, DocumentState] = {}


def _analyze(uri: str, source: str) -> DocumentState:
    """Run Lexer → Parser → Checker, cache results, return state."""
    ds = DocumentState(source=source)
    diags: list[lsp.Diagnostic] = []
    filename = uri

    # Phase 1: Lex
    try:
        tokens = Lexer(source, filename).lex()
        ds.tokens = tokens
    except CompileError as e:
        for d in e.diagnostics:
            diags.append(lsp.Diagnostic(
                range=span_to_range(d.labels[0].span) if d.labels else lsp.Range(
                    start=lsp.Position(0, 0), end=lsp.Position(0, 0),
                ),
                severity=_SEVERITY_MAP.get(d.severity, lsp.DiagnosticSeverity.Error),
                source="prove",
                message=f"[{d.code}] {d.message}",
            ))
        ds.diagnostics = diags
        _state[uri] = ds
        return ds

    # Phase 2: Parse
    try:
        module = Parser(tokens, filename).parse()
        ds.module = module
    except CompileError as e:
        for d in e.diagnostics:
            diags.append(lsp.Diagnostic(
                range=span_to_range(d.labels[0].span) if d.labels else lsp.Range(
                    start=lsp.Position(0, 0), end=lsp.Position(0, 0),
                ),
                severity=_SEVERITY_MAP.get(d.severity, lsp.DiagnosticSeverity.Error),
                source="prove",
                message=f"[{d.code}] {d.message}",
            ))
        ds.diagnostics = diags
        _state[uri] = ds
        return ds

    # Phase 3: Check
    checker = Checker()
    symbols = checker.check(module)
    ds.symbols = symbols

    for d in checker.diagnostics:
        diags.append(lsp.Diagnostic(
            range=span_to_range(d.labels[0].span) if d.labels else lsp.Range(
                start=lsp.Position(0, 0), end=lsp.Position(0, 0),
            ),
            severity=_SEVERITY_MAP.get(d.severity, lsp.DiagnosticSeverity.Error),
            source="prove",
            message=f"[{d.code}] {d.message}",
        ))

    ds.diagnostics = diags
    _state[uri] = ds
    return ds


def _get_word_at(source: str, line: int, character: int) -> str:
    """Extract the word at the given 0-indexed position."""
    lines = source.splitlines()
    if line < 0 or line >= len(lines):
        return ""
    text = lines[line]
    if character < 0 or character >= len(text):
        # Try character-1 in case cursor is right after the word
        if character > 0 and character <= len(text):
            character -= 1
        else:
            return ""

    # Walk back to start of word
    start = character
    while start > 0 and (text[start - 1].isalnum() or text[start - 1] == "_"):
        start -= 1

    # Walk forward to end of word
    end = character
    while end < len(text) and (text[end].isalnum() or text[end] == "_"):
        end += 1

    return text[start:end]


# ── LSP Feature Handlers ─────────────────────────────────────────


@server.feature(lsp.TEXT_DOCUMENT_DID_OPEN)
def did_open(params: lsp.DidOpenTextDocumentParams) -> None:
    uri = params.text_document.uri
    source = params.text_document.text
    ds = _analyze(uri, source)
    server.text_document_publish_diagnostics(lsp.PublishDiagnosticsParams(
        uri=uri,
        diagnostics=ds.diagnostics,
    ))


@server.feature(lsp.TEXT_DOCUMENT_DID_CHANGE)
def did_change(params: lsp.DidChangeTextDocumentParams) -> None:
    uri = params.text_document.uri
    # Full sync — take last content change
    source = params.content_changes[-1].text if params.content_changes else ""
    ds = _analyze(uri, source)
    server.text_document_publish_diagnostics(lsp.PublishDiagnosticsParams(
        uri=uri,
        diagnostics=ds.diagnostics,
    ))


@server.feature(lsp.TEXT_DOCUMENT_DID_CLOSE)
def did_close(params: lsp.DidCloseTextDocumentParams) -> None:
    _state.pop(params.text_document.uri, None)


@server.feature(lsp.TEXT_DOCUMENT_HOVER)
def hover(params: lsp.HoverParams) -> lsp.Hover | None:
    uri = params.text_document.uri
    ds = _state.get(uri)
    if ds is None or ds.symbols is None:
        return None

    word = _get_word_at(ds.source, params.position.line, params.position.character)
    if not word:
        return None

    # Try symbol lookup
    sym = ds.symbols.lookup(word)
    if sym is not None:
        from prove.types import type_name
        kind = sym.kind.name.lower()
        ty = type_name(sym.resolved_type)
        verb_prefix = f"{sym.verb} " if sym.verb else ""
        content = f"**{kind}** `{verb_prefix}{sym.name}` : `{ty}`"
        return lsp.Hover(contents=lsp.MarkupContent(
            kind=lsp.MarkupKind.Markdown,
            value=content,
        ))

    # Try function lookup
    sig = ds.symbols.resolve_function_any(word)
    if sig is not None:
        content = f"**function** `{_types_display(sig)}`"
        return lsp.Hover(contents=lsp.MarkupContent(
            kind=lsp.MarkupKind.Markdown,
            value=content,
        ))

    # Try type lookup
    resolved = ds.symbols.resolve_type(word)
    if resolved is not None:
        from prove.types import type_name
        content = f"**type** `{word}` = `{type_name(resolved)}`"
        return lsp.Hover(contents=lsp.MarkupContent(
            kind=lsp.MarkupKind.Markdown,
            value=content,
        ))

    return None


@server.feature(
    lsp.TEXT_DOCUMENT_COMPLETION,
    lsp.CompletionOptions(trigger_characters=[".", "(", "|"]),
)
def completion(params: lsp.CompletionParams) -> lsp.CompletionList:
    uri = params.text_document.uri
    ds = _state.get(uri)
    items: list[lsp.CompletionItem] = []

    # Keywords
    for kw in _KEYWORD_COMPLETIONS:
        items.append(lsp.CompletionItem(
            label=kw,
            kind=lsp.CompletionItemKind.Keyword,
        ))

    # Builtins
    for name in _BUILTINS:
        items.append(lsp.CompletionItem(
            label=name,
            kind=lsp.CompletionItemKind.Function,
        ))

    if ds is not None and ds.symbols is not None:
        # All known names from symbol table
        for name in ds.symbols.all_known_names():
            sym = ds.symbols.lookup(name)
            if sym is not None:
                kind_map = {
                    SymbolKind.FUNCTION: lsp.CompletionItemKind.Function,
                    SymbolKind.TYPE: lsp.CompletionItemKind.Class,
                    SymbolKind.CONSTANT: lsp.CompletionItemKind.Constant,
                    SymbolKind.VARIABLE: lsp.CompletionItemKind.Variable,
                    SymbolKind.PARAMETER: lsp.CompletionItemKind.Variable,
                }
                items.append(lsp.CompletionItem(
                    label=name,
                    kind=kind_map.get(sym.kind, lsp.CompletionItemKind.Text),
                ))
            else:
                items.append(lsp.CompletionItem(
                    label=name,
                    kind=lsp.CompletionItemKind.Text,
                ))

        # Function snippets
        for (_verb, fname), sigs in ds.symbols.all_functions().items():
            if sigs:
                sig = sigs[0]
                params_str = ", ".join(sig.param_names)
                items.append(lsp.CompletionItem(
                    label=fname,
                    kind=lsp.CompletionItemKind.Function,
                    detail=_types_display(sig),
                    insert_text=f"{fname}({params_str})",
                    insert_text_format=lsp.InsertTextFormat.PlainText,
                ))

    # Deduplicate by label
    seen: set[str] = set()
    unique: list[lsp.CompletionItem] = []
    for item in items:
        if item.label not in seen:
            seen.add(item.label)
            unique.append(item)

    return lsp.CompletionList(is_incomplete=False, items=unique)


@server.feature(lsp.TEXT_DOCUMENT_DEFINITION)
def definition(params: lsp.DefinitionParams) -> lsp.Location | None:
    uri = params.text_document.uri
    ds = _state.get(uri)
    if ds is None or ds.symbols is None:
        return None

    word = _get_word_at(ds.source, params.position.line, params.position.character)
    if not word:
        return None

    # Look up symbol
    sym = ds.symbols.lookup(word)
    if sym is not None and sym.span.file != "<builtin>":
        target_uri = uri  # same file for now (single-file analysis)
        return lsp.Location(
            uri=target_uri,
            range=span_to_range(sym.span),
        )

    # Try function lookup
    sig = ds.symbols.resolve_function_any(word)
    if sig is not None and sig.span.file != "<builtin>":
        return lsp.Location(
            uri=uri,
            range=span_to_range(sig.span),
        )

    return None


@server.feature(lsp.TEXT_DOCUMENT_DOCUMENT_SYMBOL)
def document_symbol(params: lsp.DocumentSymbolParams) -> list[lsp.DocumentSymbol]:
    uri = params.text_document.uri
    ds = _state.get(uri)
    if ds is None or ds.module is None:
        return []

    symbols: list[lsp.DocumentSymbol] = []
    for decl in ds.module.declarations:
        sym = _decl_to_symbol(decl)
        if sym is not None:
            symbols.append(sym)

    return symbols


def _decl_to_symbol(decl: object) -> lsp.DocumentSymbol | None:
    """Convert a top-level declaration to an LSP DocumentSymbol."""
    if isinstance(decl, FunctionDef):
        params_str = ", ".join(p.name for p in decl.params)
        detail = f"{decl.verb} ({params_str})"
        return lsp.DocumentSymbol(
            name=decl.name,
            kind=lsp.SymbolKind.Function,
            range=span_to_range(decl.span),
            selection_range=span_to_range(decl.span),
            detail=detail,
        )
    if isinstance(decl, MainDef):
        return lsp.DocumentSymbol(
            name="main",
            kind=lsp.SymbolKind.Function,
            range=span_to_range(decl.span),
            selection_range=span_to_range(decl.span),
        )
    if isinstance(decl, TypeDef):
        return lsp.DocumentSymbol(
            name=decl.name,
            kind=lsp.SymbolKind.Class,
            range=span_to_range(decl.span),
            selection_range=span_to_range(decl.span),
        )
    if isinstance(decl, ConstantDef):
        return lsp.DocumentSymbol(
            name=decl.name,
            kind=lsp.SymbolKind.Constant,
            range=span_to_range(decl.span),
            selection_range=span_to_range(decl.span),
        )
    if isinstance(decl, ModuleDecl):
        children: list[lsp.DocumentSymbol] = []
        for sub in decl.body:
            child = _decl_to_symbol(sub)
            if child is not None:
                children.append(child)
        return lsp.DocumentSymbol(
            name=decl.name,
            kind=lsp.SymbolKind.Module,
            range=span_to_range(decl.span),
            selection_range=span_to_range(decl.span),
            children=children if children else None,
        )
    return None


@server.feature(
    lsp.TEXT_DOCUMENT_SIGNATURE_HELP,
    lsp.SignatureHelpOptions(trigger_characters=["(", ","]),
)
def signature_help(params: lsp.SignatureHelpParams) -> lsp.SignatureHelp | None:
    uri = params.text_document.uri
    ds = _state.get(uri)
    if ds is None or ds.symbols is None:
        return None

    # Walk backward from cursor to find the function name before '('
    lines = ds.source.splitlines()
    line = params.position.line
    if line >= len(lines):
        return None

    text = lines[line]
    col = min(params.position.character, len(text))

    # Find the opening paren
    depth = 0
    pos = col - 1
    while pos >= 0:
        ch = text[pos]
        if ch == ")":
            depth += 1
        elif ch == "(":
            if depth == 0:
                break
            depth -= 1
        pos -= 1

    if pos < 0:
        return None

    # Extract function name before the paren
    end = pos
    while end > 0 and (text[end - 1].isalnum() or text[end - 1] == "_"):
        end -= 1
    func_name = text[end:pos]

    if not func_name:
        return None

    sig = ds.symbols.resolve_function_any(func_name)
    if sig is None:
        return None

    from prove.types import type_name

    params_info = [
        lsp.ParameterInformation(
            label=f"{n}: {type_name(t)}",
        )
        for n, t in zip(sig.param_names, sig.param_types)
    ]

    return lsp.SignatureHelp(
        signatures=[
            lsp.SignatureInformation(
                label=_types_display(sig),
                parameters=params_info,
            ),
        ],
        active_signature=0,
        active_parameter=0,
    )


@server.feature(lsp.TEXT_DOCUMENT_FORMATTING)
def formatting(params: lsp.DocumentFormattingParams) -> list[lsp.TextEdit] | None:
    uri = params.text_document.uri
    ds = _state.get(uri)
    if ds is None or ds.module is None:
        return None

    fmt = ProveFormatter()
    formatted = fmt.format(ds.module)

    if formatted == ds.source:
        return None

    # Replace entire document
    lines = ds.source.splitlines()
    end_line = len(lines)
    end_char = len(lines[-1]) if lines else 0

    return [lsp.TextEdit(
        range=lsp.Range(
            start=lsp.Position(0, 0),
            end=lsp.Position(end_line, end_char),
        ),
        new_text=formatted,
    )]


# ── Entry point ──────────────────────────────────────────────────


def main() -> None:
    """Start the Prove language server on stdio."""
    server.start_io()
