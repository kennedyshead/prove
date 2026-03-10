"""Prove Language Server — pygls-based LSP for .prv files.

Provides diagnostics, hover, completion, go-to-definition,
document symbols, signature help, and formatting via stdio transport.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from lsprotocol import types as lsp
from pygls.lsp.server import LanguageServer

from prove.ast_nodes import (
    ConstantDef,
    FunctionDef,
    ImportDecl,
    ImportItem,
    MainDef,
    Module,
    ModuleDecl,
    TypeDef,
)
from prove.checker import Checker
from prove.errors import CompileError, Diagnostic, Severity
from prove.formatter import ProveFormatter
from prove.lexer import Lexer
from prove.parser import Parser
from prove.stdlib_loader import ImportSuggestion, build_import_index
from prove.symbols import FunctionSignature, SymbolKind, SymbolTable
from prove.tokens import KEYWORDS, Token, TokenKind
from prove.types import BUILTIN_FUNCTIONS

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

# Built-in function names (from canonical source in types.py)
_BUILTINS = sorted(BUILTIN_FUNCTIONS)


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

    params = ", ".join(f"{n}: {type_name(t)}" for n, t in zip(sig.param_names, sig.param_types))
    ret = type_name(sig.return_type)
    verb = f"{sig.verb} " if sig.verb else ""
    fail = "!" if sig.can_fail else ""
    return f"{verb}{sig.name}({params}) {ret}{fail}"


def _sig_params_display(sig: FunctionSignature) -> str:
    """Format just the parameter list and return type: '(a: Integer, b: Integer) Integer'."""
    from prove.types import type_name

    params = ", ".join(f"{n}: {type_name(t)}" for n, t in zip(sig.param_names, sig.param_types))
    ret = type_name(sig.return_type)
    fail = "!" if sig.can_fail else ""
    return f"({params}) {ret}{fail}"


# ── Per-document state ────────────────────────────────────────────


@dataclass
class DocumentState:
    """Cached analysis results for a single open document."""

    source: str = ""
    tokens: list[Token] = field(default_factory=list)
    module: Module | None = None
    symbols: SymbolTable | None = None
    diagnostics: list[lsp.Diagnostic] = field(default_factory=list)
    prove_diagnostics: list[Diagnostic] = field(default_factory=list)
    local_import_index: dict[str, list[ImportSuggestion]] = field(
        default_factory=dict,
    )


# ── Project Indexer (Phase 4) ────────────────────────────────────────────

_INDEXER_SKIP_KINDS = frozenset(
    {
        TokenKind.NEWLINE,
        TokenKind.INDENT,
        TokenKind.DEDENT,
        TokenKind.EOF,
        TokenKind.DOC_COMMENT,
    }
)


def _tok_text(kind: TokenKind, value: str) -> str:
    return value if value else f"<{kind.name}>"


class _ProjectIndexer:
    """Incrementally indexes .prv files under a project root for ML completions.

    Maintains per-file ngram and symbol contributions so a single-file save
    only requires re-parsing that file, not the whole project.

    Cache is written to <project-root>/.prove_cache/ as :[Lookup] .prv files.
    """

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root
        self.cache_dir = project_root / ".prove_cache"
        # Per-file contributions (enables incremental patch_file)
        self._file_ngrams: dict[str, list[tuple[str, str, str]]] = {}
        self._file_symbols: dict[str, list[dict]] = {}
        # Aggregated in-memory tables
        self._bigrams: defaultdict[str, Counter] = defaultdict(Counter)
        self._completions: defaultdict[tuple[str, str], Counter] = defaultdict(Counter)
        self._symbols: dict[str, dict] = {}

    # ── Project root detection ───────────────────────────────────────

    @classmethod
    def for_uri(cls, uri: str) -> "_ProjectIndexer | None":
        if uri.startswith("file://"):
            file_path = Path(uri[7:])
        elif uri.startswith("/"):
            file_path = Path(uri)
        else:
            return None
        root = cls._find_root(file_path)
        return cls(root)

    @staticmethod
    def _find_root(file_path: Path) -> Path:
        """Walk up from file_path to find prove.toml; fall back to file's dir."""
        start = file_path.parent if file_path.is_file() else file_path
        for candidate in [start, *start.parents]:
            if (candidate / "prove.toml").exists():
                return candidate
        return start

    # ── Indexing ─────────────────────────────────────────────────────

    def _extract_file(
        self, path: Path, source: str | None = None
    ) -> tuple[list[tuple[str, str, str]], list[dict]]:
        """Parse a file and return (ngrams, symbols). Never raises."""
        try:
            if source is None:
                source = path.read_text(encoding="utf-8")
        except OSError:
            return [], []
        try:
            tokens = Lexer(source, str(path)).lex()
        except Exception:
            return [], []

        # Token ngrams
        filtered = [t for t in tokens if t.kind not in _INDEXER_SKIP_KINDS]
        ngrams: list[tuple[str, str, str]] = []
        for i, tok in enumerate(filtered):
            p2 = _tok_text(filtered[i - 2].kind, filtered[i - 2].value) if i >= 2 else "<START>"
            p1 = _tok_text(filtered[i - 1].kind, filtered[i - 1].value) if i >= 1 else "<START>"
            ngrams.append((p2, p1, _tok_text(tok.kind, tok.value)))

        # Symbols from AST
        symbols: list[dict] = []
        try:
            module = Parser(tokens, str(path)).parse()
            try:
                rel = str(path.relative_to(self.project_root))
            except ValueError:
                rel = str(path)
            for decl in module.declarations:
                if isinstance(decl, FunctionDef):
                    symbols.append(
                        {"name": decl.name, "verb": decl.verb, "kind": "function",
                         "file": rel, "line": decl.span.start_line}
                    )
                elif isinstance(decl, TypeDef):
                    symbols.append(
                        {"name": decl.name, "verb": "type", "kind": "type",
                         "file": rel, "line": decl.span.start_line}
                    )
                elif isinstance(decl, ConstantDef):
                    symbols.append(
                        {"name": decl.name, "verb": "constant", "kind": "constant",
                         "file": rel, "line": decl.span.start_line}
                    )
        except Exception:
            pass

        return ngrams, symbols

    def _add_file(self, path_str: str, ngrams: list, symbols: list) -> None:
        self._file_ngrams[path_str] = ngrams
        self._file_symbols[path_str] = symbols
        for p2, p1, nxt in ngrams:
            self._bigrams[p1][nxt] += 1
            self._completions[(p2, p1)][nxt] += 1
        for sym in symbols:
            self._symbols[sym["name"]] = sym

    def _rebuild_tables(self) -> None:
        self._bigrams = defaultdict(Counter)
        self._completions = defaultdict(Counter)
        self._symbols = {}
        for ngrams in self._file_ngrams.values():
            for p2, p1, nxt in ngrams:
                self._bigrams[p1][nxt] += 1
                self._completions[(p2, p1)][nxt] += 1
        for syms in self._file_symbols.values():
            for sym in syms:
                self._symbols[sym["name"]] = sym

    def index_file(self, path: Path, source: str | None = None) -> None:
        """Index a single file (no-op if already indexed)."""
        path_str = str(path)
        if path_str in self._file_ngrams:
            return
        ngrams, symbols = self._extract_file(path, source)
        self._add_file(path_str, ngrams, symbols)

    def index_all_files(self) -> None:
        """Scan and index all .prv files under project_root, then save cache."""
        for prv_file in sorted(self.project_root.rglob("*.prv")):
            if ".prove_cache" in prv_file.parts:
                continue
            self.index_file(prv_file)
        self.save()

    def patch_file(self, path: Path, source: str) -> None:
        """Re-index a changed file (incremental update), then save cache."""
        path_str = str(path)
        self._file_ngrams.pop(path_str, None)
        self._file_symbols.pop(path_str, None)
        self._rebuild_tables()
        ngrams, symbols = self._extract_file(path, source)
        self._add_file(path_str, ngrams, symbols)
        self.save()

    # ── Cache persistence ─────────────────────────────────────────────

    def save(self) -> None:
        """Write in-memory tables to .prove_cache/ as :[Lookup] .prv files."""
        try:
            self._write_bigrams_cache()
            self._write_completions_cache()
        except Exception:
            pass  # Cache failures are non-fatal

    @staticmethod
    def _prv_str(value: str) -> str:
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'

    def _write_bigrams_cache(self, top_k: int = 5) -> None:
        out = self.cache_dir / "bigrams" / "current.prv"
        out.parent.mkdir(parents=True, exist_ok=True)
        (out.parent / "versions").mkdir(exist_ok=True)
        lines = [
            "// Project bigram cache — auto-generated by prove LSP",
            "type ProjectBigram:[Lookup] is String String Integer where",
        ]
        i = 0
        for prev1, counter in self._bigrams.items():
            for nxt, count in counter.most_common(top_k):
                lines.append(
                    f"    r{i:05d} | {self._prv_str(prev1)} | {self._prv_str(nxt)} | {count}"
                )
                i += 1
        out.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _write_completions_cache(self, top_k: int = 5) -> None:
        out = self.cache_dir / "completions" / "current.prv"
        out.parent.mkdir(parents=True, exist_ok=True)
        (out.parent / "versions").mkdir(exist_ok=True)
        lines = [
            "// Project completion cache — auto-generated by prove LSP",
            "type ProjectCompletion:[Lookup] is String String String where",
        ]
        for i, ((p2, p1), counter) in enumerate(self._completions.items()):
            top = "|".join(tok for tok, _ in counter.most_common(top_k))
            lines.append(
                f"    r{i:05d} | {self._prv_str(p2)} | {self._prv_str(p1)} | {self._prv_str(top)}"
            )
        out.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # ── Completion query ──────────────────────────────────────────────

    def complete(self, prev2: str, prev1: str, prefix: str = "", top_k: int = 5) -> list[str]:
        """Return top completions for (prev2, prev1) context, filtered by prefix."""
        results = [
            tok
            for tok, _ in self._completions.get((prev2, prev1), Counter()).most_common(top_k * 2)
            if not prefix or tok.startswith(prefix)
        ]
        return results[:top_k]

    def complete_unigram(self, prev1: str, prefix: str = "", top_k: int = 5) -> list[str]:
        """Fallback: top tokens following prev1."""
        results = [
            tok
            for tok, _ in self._bigrams.get(prev1, Counter()).most_common(top_k * 2)
            if not prefix or tok.startswith(prefix)
        ]
        return results[:top_k]


# ── Server ────────────────────────────────────────────────────────

server = LanguageServer(
    "prove-lsp",
    "0.1.0",
    text_document_sync_kind=lsp.TextDocumentSyncKind.Full,
)
_state: dict[str, DocumentState] = {}
_MAX_CACHED_DOCUMENTS = 50
_project_indexer: _ProjectIndexer | None = None


def _ensure_project_indexed(uri: str) -> None:
    """Create and populate project indexer for uri's project (once per session)."""
    global _project_indexer
    if _project_indexer is None:
        _project_indexer = _ProjectIndexer.for_uri(uri)
    if _project_indexer is not None and not _project_indexer._file_ngrams:
        _project_indexer.index_all_files()


def _compile_diag(d: object) -> lsp.Diagnostic:
    """Convert a prove Diagnostic to an LSP Diagnostic."""
    span_range = lsp.Range(start=lsp.Position(0, 0), end=lsp.Position(0, 0))
    if hasattr(d, "labels") and d.labels:
        span_range = span_to_range(d.labels[0].span)
    sev = _SEVERITY_MAP.get(getattr(d, "severity", None), lsp.DiagnosticSeverity.Error)
    code = getattr(d, "code", "E000")
    msg = getattr(d, "message", str(d))
    doc_url = getattr(d, "doc_url", None)
    code_desc = None
    if doc_url:
        code_desc = lsp.CodeDescription(href=doc_url)
    return lsp.Diagnostic(
        range=span_range,
        severity=sev,
        source="prove",
        code=code,
        message=f"[{code}] {msg}",
        code_description=code_desc,
    )


def _resolve_local_modules(uri: str) -> dict | None:
    """Discover sibling .prv files and build a local module registry.

    Returns None if the URI is not a file:// path or has no siblings.
    """
    from pathlib import Path

    from prove.module_resolver import build_module_registry

    # Convert file:// URI to a local path
    if uri.startswith("file://"):
        file_path = Path(uri[7:])
    elif uri.startswith("/"):
        file_path = Path(uri)
    else:
        return None

    if not file_path.exists():
        return None

    # Look for sibling .prv files in the same directory
    parent = file_path.parent
    prv_files = sorted(parent.glob("*.prv"))
    if len(prv_files) <= 1:
        return None

    try:
        return build_module_registry(prv_files)
    except Exception:
        return None


def _find_project_dir(uri: str) -> Path | None:
    """Walk up directories from file to find prove.toml (project root)."""
    from prove.config import find_config

    if uri.startswith("file://"):
        file_path = Path(uri[7:])
    elif uri.startswith("/"):
        file_path = Path(uri)
    else:
        return None

    if not file_path.exists():
        return None

    try:
        config_path = find_config(file_path.parent)
        return config_path.parent
    except FileNotFoundError:
        return None


def _build_local_import_index(
    local_modules: dict | None,
) -> dict[str, list[ImportSuggestion]]:
    """Build an import suggestion index from local (sibling) modules."""
    if not local_modules:
        return {}

    index: dict[str, list[ImportSuggestion]] = {}
    for module_name, info in local_modules.items():
        # Index exported types
        for type_name in info.types:
            index.setdefault(type_name, []).append(
                ImportSuggestion(module=module_name, verb="types", name=type_name),
            )

        # Index exported functions
        for sig in info.functions:
            index.setdefault(sig.name, []).append(
                ImportSuggestion(
                    module=module_name,
                    verb=sig.verb,
                    name=sig.name,
                    signature=_sig_params_display(sig),
                ),
            )

    return index


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
        diags.extend(_compile_diag(d) for d in e.diagnostics)
        ds.diagnostics = diags
        _state[uri] = ds
        return ds
    except Exception:
        import traceback

        diags.append(
            lsp.Diagnostic(
                range=lsp.Range(start=lsp.Position(0, 0), end=lsp.Position(0, 0)),
                severity=lsp.DiagnosticSeverity.Error,
                source="prove",
                message=f"[internal] lexer error: {traceback.format_exc()}",
            )
        )
        ds.diagnostics = diags
        _state[uri] = ds
        return ds

    # Phase 2: Parse
    try:
        module = Parser(tokens, filename).parse()
        ds.module = module
    except CompileError as e:
        diags.extend(_compile_diag(d) for d in e.diagnostics)
        ds.diagnostics = diags
        _state[uri] = ds
        return ds
    except Exception:
        import traceback

        diags.append(
            lsp.Diagnostic(
                range=lsp.Range(start=lsp.Position(0, 0), end=lsp.Position(0, 0)),
                severity=lsp.DiagnosticSeverity.Error,
                source="prove",
                message=f"[internal] parser error: {traceback.format_exc()}",
            )
        )
        ds.diagnostics = diags
        _state[uri] = ds
        return ds

    # Phase 3: Check
    try:
        local_modules = _resolve_local_modules(uri)
        project_dir = _find_project_dir(uri)
        checker = Checker(local_modules=local_modules, project_dir=project_dir)
        symbols = checker.check(module)
        ds.symbols = symbols
        ds.local_import_index = _build_local_import_index(local_modules)
        ds.prove_diagnostics = checker.diagnostics
        diags.extend(_compile_diag(d) for d in checker.diagnostics)
    except Exception:
        import traceback

        diags.append(
            lsp.Diagnostic(
                range=lsp.Range(start=lsp.Position(0, 0), end=lsp.Position(0, 0)),
                severity=lsp.DiagnosticSeverity.Error,
                source="prove",
                message=f"[internal] checker error: {traceback.format_exc()}",
            )
        )

    ds.diagnostics = diags
    _state[uri] = ds
    # Evict oldest entries if cache grows too large
    if len(_state) > _MAX_CACHED_DOCUMENTS:
        excess = len(_state) - _MAX_CACHED_DOCUMENTS
        for old_uri in list(_state)[:excess]:
            if old_uri != uri:
                del _state[old_uri]
    return ds


def _extract_context_tokens(source: str, position: lsp.Position, n: int = 2) -> list[str]:
    """Return the last n non-whitespace tokens before the cursor position.

    Uses the Prove Lexer on the text up to the cursor. Returns tokens as
    strings (value if non-empty, else <KIND>). Returns '<START>' sentinels
    when fewer than n tokens precede the cursor.
    """
    lines = source.splitlines()
    line_idx = position.line
    col = position.character
    # Truncate source at cursor
    truncated_lines = lines[:line_idx]
    if line_idx < len(lines):
        truncated_lines.append(lines[line_idx][:col])
    truncated = "\n".join(truncated_lines)

    try:
        tokens = Lexer(truncated, "<completion>").lex()
    except Exception:
        return ["<START>"] * n

    filtered = [t for t in tokens if t.kind not in _INDEXER_SKIP_KINDS]
    result: list[str] = []
    for tok in filtered[-n:]:
        result.append(_tok_text(tok.kind, tok.value))
    while len(result) < n:
        result.insert(0, "<START>")
    return result


def _ml_completions(source: str, position: lsp.Position) -> list[lsp.CompletionItem]:
    """Return ML-ranked completion items from the project indexer + global model.

    Project suggestions are prepended (rank higher). Falls back to unigram
    if no bigram match. Gracefully returns [] if indexer is unavailable.
    """
    if _project_indexer is None:
        return []

    context = _extract_context_tokens(source, position, n=2)
    prev2, prev1 = context[0], context[1]

    # Extract current partial word as prefix filter
    lines = source.splitlines()
    line_idx = position.line
    col = position.character
    prefix = ""
    if line_idx < len(lines):
        text = lines[line_idx][:col]
        m = re.search(r"[\w<>_]+$", text)
        if m:
            prefix = m.group()

    project_hits = _project_indexer.complete(prev2, prev1, prefix)
    if not project_hits:
        project_hits = _project_indexer.complete_unigram(prev1, prefix)

    global_hits = _global_model_complete(prev2, prev1, prefix)

    # Merge: project first, then global, deduplicated
    seen_toks: set[str] = set()
    merged: list[str] = []
    for tok in project_hits + global_hits:
        if tok not in seen_toks and not tok.startswith("<"):
            seen_toks.add(tok)
            merged.append(tok)

    items: list[lsp.CompletionItem] = []
    for i, tok in enumerate(merged[:10]):
        items.append(
            lsp.CompletionItem(
                label=tok,
                kind=lsp.CompletionItemKind.Text,
                detail="ml",
                sort_text=f"\x00{i:02d}_{tok}",  # sorts before other items
                label_details=lsp.CompletionItemLabelDetails(description="ml"),
            )
        )
    return items


# ── Global model loader (Phase 5) ────────────────────────────────────────

_GLOBAL_MODEL_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data" / "lsp-ml-store"
_global_bigrams: dict[str, list[str]] | None = None  # prev1 → ranked list
_global_completions: dict[tuple[str, str], list[str]] | None = None  # (p2,p1) → ranked list


def _load_global_model() -> None:
    """Load global model from data/lsp-ml-store/ :[Lookup] .prv files (once)."""
    global _global_bigrams, _global_completions
    if _global_bigrams is not None:
        return

    _global_bigrams = {}
    _global_completions = {}

    def _parse_lookup_rows(path: Path) -> list[list[str]]:
        """Parse rows from a :[Lookup] .prv file into lists of string values."""
        rows = []
        if not path.exists():
            return rows
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line.startswith("r") or "|" not in line:
                continue
            parts = [p.strip() for p in line.split("|")[1:]]  # skip row id
            decoded = []
            for p in parts:
                if p.startswith('"') and p.endswith('"'):
                    decoded.append(p[1:-1].replace('\\"', '"').replace("\\\\", "\\"))
                else:
                    try:
                        decoded.append(int(p))  # type: ignore[arg-type]
                    except ValueError:
                        decoded.append(p)
            rows.append(decoded)
        return rows

    # Load unigram (bigrams table): (prev1, next_tok, count)
    bg_path = _GLOBAL_MODEL_DIR / "bigrams" / "current.prv"
    for row in _parse_lookup_rows(bg_path):
        if len(row) >= 2:
            prev1 = str(row[0])
            nxt = str(row[1])
            _global_bigrams.setdefault(prev1, []).append(nxt)

    # Load completions table: (prev2, prev1, pipe-separated list)
    co_path = _GLOBAL_MODEL_DIR / "completions" / "current.prv"
    for row in _parse_lookup_rows(co_path):
        if len(row) >= 3:
            prev2, prev1 = str(row[0]), str(row[1])
            toks = [t for t in str(row[2]).split("|") if t]
            _global_completions[(prev2, prev1)] = toks


def _global_model_complete(prev2: str, prev1: str, prefix: str = "", top_k: int = 5) -> list[str]:
    """Query global model; falls back to unigram. Returns [] if model not loaded."""
    try:
        _load_global_model()
    except Exception:
        return []

    results: list[str] = []
    if _global_completions is not None:
        for tok in _global_completions.get((prev2, prev1), []):
            if not prefix or tok.startswith(prefix):
                results.append(tok)
            if len(results) >= top_k:
                break

    if not results and _global_bigrams is not None:
        for tok in _global_bigrams.get(prev1, []):
            if not prefix or tok.startswith(prefix):
                results.append(tok)
            if len(results) >= top_k:
                break

    return results


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
    server.text_document_publish_diagnostics(
        lsp.PublishDiagnosticsParams(
            uri=uri,
            diagnostics=ds.diagnostics,
        )
    )
    try:
        _ensure_project_indexed(uri)
    except Exception:
        pass


@server.feature(lsp.TEXT_DOCUMENT_DID_CHANGE)
def did_change(params: lsp.DidChangeTextDocumentParams) -> None:
    uri = params.text_document.uri
    # Full sync — take last content change
    source = params.content_changes[-1].text if params.content_changes else ""
    ds = _analyze(uri, source)
    server.text_document_publish_diagnostics(
        lsp.PublishDiagnosticsParams(
            uri=uri,
            diagnostics=ds.diagnostics,
        )
    )


@server.feature(lsp.TEXT_DOCUMENT_DID_CLOSE)
def did_close(params: lsp.DidCloseTextDocumentParams) -> None:
    _state.pop(params.text_document.uri, None)


@server.feature(lsp.TEXT_DOCUMENT_DID_SAVE)
def did_save(params: lsp.DidSaveTextDocumentParams) -> None:
    if _project_indexer is None:
        return
    uri = params.text_document.uri
    if uri.startswith("file://"):
        path = Path(uri[7:])
    elif uri.startswith("/"):
        path = Path(uri)
    else:
        return
    if path.suffix != ".prv" or not path.exists():
        return
    try:
        source = path.read_text(encoding="utf-8")
        _project_indexer.patch_file(path, source)
    except Exception:
        pass


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
        return lsp.Hover(
            contents=lsp.MarkupContent(
                kind=lsp.MarkupKind.Markdown,
                value=content,
            )
        )

    # Try function lookup
    sig = ds.symbols.resolve_function_any(word)
    if sig is not None:
        content = f"**function** `{_types_display(sig)}`"
        return lsp.Hover(
            contents=lsp.MarkupContent(
                kind=lsp.MarkupKind.Markdown,
                value=content,
            )
        )

    # Try type lookup
    resolved = ds.symbols.resolve_type(word)
    if resolved is not None:
        from prove.types import type_name

        content = f"**type** `{word}` = `{type_name(resolved)}`"
        return lsp.Hover(
            contents=lsp.MarkupContent(
                kind=lsp.MarkupKind.Markdown,
                value=content,
            )
        )

    return None


@server.feature(
    lsp.TEXT_DOCUMENT_COMPLETION,
    lsp.CompletionOptions(trigger_characters=[".", "(", "|"]),
)
def completion(params: lsp.CompletionParams) -> lsp.CompletionList:
    uri = params.text_document.uri
    ds = _state.get(uri)
    items: list[lsp.CompletionItem] = []

    # Keywords with documentation
    _KEYWORD_DOCS: dict[str, str] = {
        "narrative": "Module-level documentation (required)",
        "explain": "Implementation documentation block (documents from block steps)",
        "domain": "Tags module's problem domain (e.g., Finance, Physics)",
        "why_not": "Documents rejected alternatives",
        "chosen": "Explains the selected approach",
        "trusted": "Opts out of verification (use with rationale)",
        "requires": "Precondition contract",
        "ensures": "Postcondition contract",
        "intent": "Statement-level purpose annotation",
        "near_miss": "Boundary test inputs that almost break the code",
    }
    for kw in _KEYWORD_COMPLETIONS:
        item = lsp.CompletionItem(
            label=kw,
            kind=lsp.CompletionItemKind.Keyword,
        )
        if kw in _KEYWORD_DOCS:
            item.documentation = lsp.MarkupContent(
                kind=lsp.MarkupKind.Markdown,
                value=_KEYWORD_DOCS[kw],
            )
        items.append(item)

    # Builtins (runtime intrinsics — C-backed, not .prv)
    _BUILTIN_SIGS: dict[str, str] = {
        "len": "(list: List<Value>) Integer",
        "map": "(list: List<Value>, fn: (Value) -> Output) List<Output>",
        "filter": "(list: List<Value>, fn: (Value) -> Boolean) List<Value>",
        "reduce": "(list: List<Value>, init: Output, fn: (Output, Value) -> Output) Output",
        "to_string": "(value: Value) String",
        "clamp": "(value: Integer, low: Integer, high: Integer) Integer",
    }
    for name in _BUILTINS:
        items.append(
            lsp.CompletionItem(
                label=name,
                kind=lsp.CompletionItemKind.Function,
                detail=_BUILTIN_SIGS.get(name, "builtin"),
                label_details=lsp.CompletionItemLabelDetails(
                    description="builtin",
                ),
            )
        )

    # Built-in types (always available)
    from prove.types import BUILTINS as _TYPE_BUILTINS

    for type_name in _TYPE_BUILTINS:
        items.append(
            lsp.CompletionItem(
                label=type_name,
                kind=lsp.CompletionItemKind.Class,
                detail="type",
            )
        )
    # Generic types
    for type_name in ("List", "Result", "Option"):
        items.append(
            lsp.CompletionItem(
                label=type_name,
                kind=lsp.CompletionItemKind.Class,
                detail="type",
            )
        )

    # Stdlib + local module functions and types — one item per verb variant
    index = _merged_import_index(ds)
    for name, suggestions in index.items():
        for s in suggestions:
            is_type = s.verb == "types"
            # Compute auto-import edit if we have document state
            additional_edits: list[lsp.TextEdit] | None = None
            already_imported = False
            if ds is not None:
                edit = _build_import_edit(ds, s)
                if edit is not None:
                    additional_edits = [edit]
                elif ds.module is not None:
                    # Already imported - mark it but don't skip
                    already_imported = True
            # Label shows module + verb + name (e.g., "InputOutput outputs console")
            label = f"{s.module} {s.verb or 'function'} {name}"
            # Detail: "Auto-import" for importable, verb for already imported
            detail = "Auto-import" if not already_imported else (s.verb or "")
            # Documentation: for types use type_def, for functions use signature
            if is_type and s.type_def:
                doc_value = f"```prove\n{s.type_def}\n```"
                if s.docstring:
                    doc_value += f"\n---\n{s.docstring}"
            else:
                sig_line = f"{name}{s.signature}" if s.signature else f"{name}"
                if s.docstring:
                    doc_value = f"```prove\n{sig_line}\n```\n---\n{s.docstring}"
                else:
                    doc_value = f"```prove\n{sig_line}\n```"
            documentation = lsp.MarkupContent(
                kind=lsp.MarkupKind.Markdown,
                value=doc_value,
            )
            items.append(
                lsp.CompletionItem(
                    label=label,
                    kind=(
                        lsp.CompletionItemKind.Struct
                        if is_type
                        else lsp.CompletionItemKind.Function
                    ),
                    detail=detail,
                    documentation=documentation,
                    insert_text=name,
                    insert_text_format=lsp.InsertTextFormat.PlainText,
                    label_details=lsp.CompletionItemLabelDetails(
                        detail=f" {s.verb}" if s.verb and s.verb != "types" else None,
                        description=s.module,
                    ),
                    filter_text=name,
                    sort_text=f"{name}_{s.verb}_{s.signature}"
                    if s.verb
                    else f"{name}_{s.signature}",
                    additional_text_edits=additional_edits,
                )
            )

    # Symbol table completions (when file parses successfully)
    if ds is not None and ds.symbols is not None:
        # Collect function names so we skip them in all_known_names
        # (they're handled more thoroughly by the all_functions loop below)
        func_names = {fname for (_verb, fname) in ds.symbols.all_functions()}

        # All known names from symbol table (excluding function names)
        # Skip if the same name exists in stdlib (to avoid duplicates with import suggestions)
        stdlib_names = set(index.keys()) if index else set()
        for name in ds.symbols.all_known_names():
            if name in func_names:
                continue
            sym = ds.symbols.lookup(name)
            # Skip local types that also exist in stdlib (stdlib version wins)
            if sym is not None and sym.kind == SymbolKind.TYPE and name in stdlib_names:
                continue
            if sym is not None:
                from prove.types import type_name as _tn

                kind_map = {
                    SymbolKind.FUNCTION: lsp.CompletionItemKind.Function,
                    SymbolKind.TYPE: lsp.CompletionItemKind.Class,
                    SymbolKind.CONSTANT: lsp.CompletionItemKind.Constant,
                    SymbolKind.VARIABLE: lsp.CompletionItemKind.Variable,
                    SymbolKind.PARAMETER: lsp.CompletionItemKind.Variable,
                }
                verb_prefix = f"{sym.verb} " if sym.verb else ""
                items.append(
                    lsp.CompletionItem(
                        label=name,
                        kind=kind_map.get(sym.kind, lsp.CompletionItemKind.Text),
                        detail=f"{verb_prefix}{_tn(sym.resolved_type)}",
                    )
                )
            else:
                items.append(
                    lsp.CompletionItem(
                        label=name,
                        kind=lsp.CompletionItemKind.Text,
                    )
                )

        # Function signatures — show all overloads (skip imported ones)
        for (_verb, fname), sigs in ds.symbols.all_functions().items():
            for sig in sigs:
                # Skip functions from imported modules (they're shown in stdlib section)
                if hasattr(sig, "module") and sig.module is not None:
                    continue
                # Label: "verb name" (e.g., "transforms add")
                label = f"{sig.verb or 'function'} {fname}"
                # Detail: "verb" (e.g., "transforms")
                detail = sig.verb or ""
                # Documentation: name + signature (no verb)
                sig_line = f"{fname}{_sig_params_display(sig)}"
                if sig.doc_comment:
                    doc_value = f"```prove\n{sig_line}\n```\n---\n{sig.doc_comment}"
                else:
                    doc_value = f"```prove\n{sig_line}\n```"
                documentation = lsp.MarkupContent(
                    kind=lsp.MarkupKind.Markdown,
                    value=doc_value,
                )
                items.append(
                    lsp.CompletionItem(
                        label=label,
                        kind=lsp.CompletionItemKind.Function,
                        detail=detail,
                        documentation=documentation,
                        insert_text=fname,
                        insert_text_format=lsp.InsertTextFormat.PlainText,
                        label_details=lsp.CompletionItemLabelDetails(
                            detail=f" {sig.verb}" if sig.verb else None,
                        ),
                        sort_text=f"{fname}_{sig.verb}_{_sig_params_display(sig)}"
                        if sig.verb
                        else f"{fname}_{_sig_params_display(sig)}",
                    )
                )

    # Phase 5 — ML completion suggestions
    if _project_indexer is not None and ds is not None:
        ml_items = _ml_completions(ds.source, params.position)
        items = ml_items + items  # project/global ML suggestions rank first

    # Deduplicate by (label, sort_text) — verb variants are distinct.
    # Later items (symbol table) override earlier ones (stdlib index)
    # when both have detail, because local definitions are more specific.
    seen: dict[tuple[str, str], lsp.CompletionItem] = {}
    for item in items:
        key = (item.label, item.sort_text or item.label)
        existing = seen.get(key)
        if existing is None:
            seen[key] = item
        elif item.detail:
            seen[key] = item

    return lsp.CompletionList(
        is_incomplete=False,
        items=list(seen.values()),
    )


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
        for td in decl.types:
            children.append(
                lsp.DocumentSymbol(
                    name=td.name,
                    kind=lsp.SymbolKind.Class,
                    range=span_to_range(td.span),
                    selection_range=span_to_range(td.span),
                )
            )
        for cd in decl.constants:
            children.append(
                lsp.DocumentSymbol(
                    name=cd.name,
                    kind=lsp.SymbolKind.Constant,
                    range=span_to_range(cd.span),
                    selection_range=span_to_range(cd.span),
                )
            )
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

    # Look backwards from the function name to find the verb
    verb = None
    verbs = ("transforms", "inputs", "outputs", "reads", "validates", "creates", "matches")
    search_start = max(0, end - 20)  # Look at most 20 chars before
    before_func = text[search_start:end].strip()
    for v in verbs:
        if before_func.endswith(v):
            verb = v
            break

    # Count current arguments to match by arity
    arg_count = text[pos:col].count(",") + 1 if col > pos else 0

    # Collect all matching overloads for this function name
    from prove.types import type_name

    all_sigs: list[FunctionSignature] = []
    for (_v, fname), sigs in ds.symbols.all_functions().items():
        if fname == func_name:
            if verb and _v == verb:
                all_sigs.extend(sigs)
            elif not verb:
                all_sigs.extend(sigs)

    if not all_sigs:
        # Fallback to single resolution
        sig = ds.symbols.resolve_function_any(func_name)
        if sig is None:
            return None
        all_sigs = [sig]

    sig_infos = []
    for sig in all_sigs:
        params_info = [
            lsp.ParameterInformation(
                label=f"{n}: {type_name(t)}",
            )
            for n, t in zip(sig.param_names, sig.param_types)
        ]
        sig_infos.append(
            lsp.SignatureInformation(
                label=_types_display(sig),
                parameters=params_info,
            )
        )

    return lsp.SignatureHelp(
        signatures=sig_infos,
        active_signature=0,
        active_parameter=0,
    )


@server.feature(lsp.TEXT_DOCUMENT_FORMATTING)
def formatting(params: lsp.DocumentFormattingParams) -> list[lsp.TextEdit] | None:
    uri = params.text_document.uri
    ds = _state.get(uri)
    if ds is None or ds.module is None:
        return None

    # Filter to only I302 (unused imports) for formatting - don't remove unused types
    fmt_diags = [d for d in ds.prove_diagnostics if d.code == "I302"]
    fmt = ProveFormatter(symbols=ds.symbols, diagnostics=fmt_diags)
    formatted = fmt.format(ds.module)

    if formatted == ds.source:
        return None

    # Replace entire document
    lines = ds.source.splitlines()
    end_line = len(lines)
    end_char = len(lines[-1]) if lines else 0

    return [
        lsp.TextEdit(
            range=lsp.Range(
                start=lsp.Position(0, 0),
                end=lsp.Position(end_line, end_char),
            ),
            new_text=formatted,
        )
    ]


# ── Auto-import code actions ─────────────────────────────────────


def _is_importable_error(diag: lsp.Diagnostic) -> bool:
    """Match E310/W310 (undefined name) or E300 (undefined type) diagnostics."""
    return diag.code in ("E310", "I310", "E300")


# Keep old name as alias for backwards compat in tests
_is_e310 = _is_importable_error


def _extract_undefined_name(message: str) -> str | None:
    """Extract name from diagnostic messages about undefined/implicitly typed names."""
    m = re.search(r"(?:undefined (?:name|type)|implicitly typed) '(\w+)'", message)
    return m.group(1) if m else None


_IMPORT_VERBS = {
    "transforms",
    "validates",
    "inputs",
    "outputs",
    "reads",
    "creates",
    "matches",
    "types",
}


def _merged_import_index(
    ds: DocumentState | None,
) -> dict[str, list[ImportSuggestion]]:
    """Merge stdlib import index with local module imports."""
    index = dict(build_import_index())  # shallow copy
    if ds is not None and ds.local_import_index:
        for name, suggestions in ds.local_import_index.items():
            index.setdefault(name, []).extend(suggestions)
    return index


def _build_import_edit_text(
    source: str,
    suggestion: ImportSuggestion,
) -> lsp.TextEdit | None:
    """Text-based fallback for auto-import when the AST is not available.

    Scans source lines to find the module header and existing imports,
    then inserts the new import at the right location.
    """
    lines = source.splitlines()
    verb_prefix = f"{suggestion.verb} " if suggestion.verb else ""
    new_import = f"  {suggestion.module} {verb_prefix}{suggestion.name}\n"

    # Check if already imported (simple text match)
    for line in lines:
        stripped = line.strip()
        if suggestion.name in stripped and suggestion.module in stripped:
            return None

    # Find the module header region
    module_line: int | None = None
    header_end: int = 0
    last_import_line: int | None = None

    for i, line in enumerate(lines):
        stripped = line.strip()

        if stripped.startswith("module ") and module_line is None:
            module_line = i
            header_end = i + 1
            continue

        if module_line is None:
            continue

        # Still in the header (narrative/temporal)
        if stripped.startswith("narrative:") or stripped.startswith("temporal:"):
            header_end = i + 1
            continue

        # Import lines: indented "ModuleName verb name, name"
        # e.g. "  InputOutput outputs console"
        if line.startswith("  ") and stripped:
            parts = stripped.split()
            if len(parts) >= 3 and parts[0][0].isupper() and parts[1] in _IMPORT_VERBS:
                last_import_line = i
                continue

        # Past the header/import region — stop scanning
        break

    if module_line is None:
        return None

    if last_import_line is not None:
        insert_line = last_import_line + 1
    else:
        insert_line = header_end

    return lsp.TextEdit(
        range=lsp.Range(
            start=lsp.Position(line=insert_line, character=0),
            end=lsp.Position(line=insert_line, character=0),
        ),
        new_text=new_import,
    )


def _build_import_edit(
    ds: DocumentState,
    suggestion: ImportSuggestion,
) -> lsp.TextEdit | None:
    """Compute TextEdit to insert or extend an import inside a module block.

    Falls back to text-based insertion when the module is not parsed.
    """
    if ds.module is None:
        return _build_import_edit_text(ds.source, suggestion)

    from prove.formatter import ProveFormatter

    # Find the ModuleDecl that owns the imports.
    mod_decl: ModuleDecl | None = None
    for decl in ds.module.declarations:
        if isinstance(decl, ModuleDecl):
            mod_decl = decl
            break

    if mod_decl is None:
        # No module declaration — insert one at line 0 with the import.
        verb_prefix = f"{suggestion.verb} " if suggestion.verb else ""
        new_line = f"  {suggestion.module} {verb_prefix}{suggestion.name}\n"
        return lsp.TextEdit(
            range=lsp.Range(
                start=lsp.Position(line=0, character=0),
                end=lsp.Position(line=0, character=0),
            ),
            new_text=new_line,
        )

    # Search existing imports in the module.
    last_import_line = -1
    for imp in mod_decl.imports:
        imp_line = imp.span.start_line - 1  # 0-indexed
        if imp_line > last_import_line:
            last_import_line = imp_line

        if imp.module != suggestion.module:
            continue

        # Same module — check if this specific verb+name is already imported.
        for item in imp.items:
            if item.name == suggestion.name:
                # If imported item has no verb, it matches any verb
                # If suggestion has no verb, it matches any imported verb
                if item.verb is None or suggestion.verb is None:
                    return None
                if item.verb == suggestion.verb:
                    return None

        # Extend: rebuild the import line with the new name.
        new_items = list(imp.items) + [
            ImportItem(suggestion.verb, suggestion.name, imp.span),
        ]
        new_decl = ImportDecl(imp.module, new_items, imp.span)
        new_line = f"  {ProveFormatter()._format_import_decl(new_decl)}"

        source_lines = ds.source.splitlines()
        line_text = source_lines[imp_line] if imp_line < len(source_lines) else ""
        return lsp.TextEdit(
            range=lsp.Range(
                start=lsp.Position(line=imp_line, character=0),
                end=lsp.Position(line=imp_line, character=len(line_text)),
            ),
            new_text=new_line,
        )

    # No existing import for this module — insert a new indented line.
    verb_prefix = f"{suggestion.verb} " if suggestion.verb else ""
    new_line = f"  {suggestion.module} {verb_prefix}{suggestion.name}\n"
    # Insert after the last import, or after the module header line.
    if last_import_line >= 0:
        insert_line = last_import_line + 1
    else:
        # After narrative/temporal or the module line itself.
        insert_line = mod_decl.span.start_line  # 0-indexed: line after 'module X'
    return lsp.TextEdit(
        range=lsp.Range(
            start=lsp.Position(line=insert_line, character=0),
            end=lsp.Position(line=insert_line, character=0),
        ),
        new_text=new_line,
    )


@server.feature(
    lsp.TEXT_DOCUMENT_CODE_ACTION,
    lsp.CodeActionOptions(code_action_kinds=[lsp.CodeActionKind.QuickFix]),
)
def code_action(params: lsp.CodeActionParams) -> list[lsp.CodeAction] | None:
    uri = params.text_document.uri
    ds = _state.get(uri)
    if ds is None:
        return None

    index = _merged_import_index(ds)
    actions: list[lsp.CodeAction] = []

    for diag in params.context.diagnostics:
        if not _is_importable_error(diag):
            continue
        name = _extract_undefined_name(diag.message)
        if name is None or name not in index:
            continue

        suggestions = index[name]
        for suggestion in suggestions:
            edit = _build_import_edit(ds, suggestion)
            if edit is None:
                continue
            verb_part = f" ({suggestion.verb})" if suggestion.verb else ""
            title = f"Import {suggestion.name} from {suggestion.module}{verb_part}"
            actions.append(
                lsp.CodeAction(
                    title=title,
                    kind=lsp.CodeActionKind.QuickFix,
                    diagnostics=[diag],
                    is_preferred=len(suggestions) == 1,
                    edit=lsp.WorkspaceEdit(changes={uri: [edit]}),
                )
            )

    return actions if actions else None


# ── Entry point ──────────────────────────────────────────────────


def main() -> None:
    """Start the Prove language server on stdio."""
    server.start_io()
