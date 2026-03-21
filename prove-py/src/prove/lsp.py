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

from prove._body_gen import generate_body
from prove._nl_intent import VERB_SYNONYMS as _VERB_PROSE_HINTS
from prove.ast_nodes import (
    ConstantDef,
    FunctionDef,
    ImportDecl,
    ImportItem,
    MainDef,
    MatchExpr,
    Module,
    ModuleDecl,
    TypeDef,
    VarDecl,
    WhileLoop,
)
from prove.checker import Checker
from prove.errors import CompileError, Diagnostic, Severity
from prove.formatter import ProveFormatter
from prove.lexer import Lexer
from prove.nlp_store import (
    load_lsp_bigrams,
    load_lsp_completions,
    load_lsp_from_blocks,
)
from prove.parser import Parser
from prove.stdlib_loader import (
    ImportSuggestion,
    build_import_index,
)
from prove.symbols import FunctionSignature, SymbolKind, SymbolTable
from prove.tokens import KEYWORDS, Token, TokenKind
from prove.types import BUILTIN_FUNCTIONS, type_name

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

    params = ", ".join(f"{n}: {type_name(t)}" for n, t in zip(sig.param_names, sig.param_types))
    ret = type_name(sig.return_type)
    verb = f"{sig.verb} " if sig.verb else ""
    fail = "!" if sig.can_fail else ""
    return f"{verb}{sig.name}({params}) {ret}{fail}"


def _sig_params_display(sig: FunctionSignature) -> str:
    """Format just the parameter list and return type: '(a: Integer, b: Integer) Integer'."""

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
    inlay_type_map: dict[tuple[int, int], str] = field(default_factory=dict)


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


def _ast_type_str(te: object) -> str:
    """Convert a TypeExpr AST node to a display string (no checker needed)."""
    from prove.ast_nodes import GenericType, ModifiedType, SimpleType

    if isinstance(te, SimpleType):
        return te.name
    if isinstance(te, GenericType):
        args = ", ".join(_ast_type_str(a) for a in te.args)
        return f"{te.name}<{args}>"
    if isinstance(te, ModifiedType):
        parts = []
        for m in te.modifiers:
            parts.append(f"{m.name}:{m.value}" if m.name else m.value)
        mods = " ".join(parts)
        return f"{te.name}:[{mods}]"
    return str(te)


def _ast_sig_str(decl: FunctionDef) -> str:
    """Format a FunctionDef signature as '(name Type, ...) ReturnType[!]'."""
    params = ", ".join(f"{p.name} {_ast_type_str(p.type_expr)}" for p in decl.params)
    ret = f" {_ast_type_str(decl.return_type)}" if decl.return_type is not None else ""
    fail = "!" if decl.can_fail else ""
    return f"({params}){ret}{fail}"


def _tok_text(kind: TokenKind, value: str) -> str:
    return value if value else f"<{kind.name}>"


class _ProjectIndexer:
    """Incrementally indexes .prv files under a project root for ML completions.

    Maintains per-file ngram and symbol contributions so a single-file save
    only requires re-parsing that file, not the whole project.

    Cache is written to <project-root>/.prove/cache/ as PDAT binary files.
    """

    _CACHE_VERSION = 2  # bump when extraction logic or PDAT schema changes

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root
        self.cache_dir = project_root / ".prove" / "cache"
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
            # Detect module name for auto-import support
            module_name: str | None = None
            for decl in module.declarations:
                if isinstance(decl, ModuleDecl):
                    module_name = decl.name
                    break

            def _collect(decl: object) -> None:
                if isinstance(decl, FunctionDef):
                    symbols.append(
                        {
                            "name": decl.name,
                            "verb": decl.verb,
                            "kind": "function",
                            "file": rel,
                            "line": decl.span.start_line,
                            "module": module_name,
                            "signature": _ast_sig_str(decl),
                            "docstring": decl.doc_comment or "",
                        }
                    )
                elif isinstance(decl, TypeDef):
                    symbols.append(
                        {
                            "name": decl.name,
                            "verb": "types",
                            "kind": "type",
                            "file": rel,
                            "line": decl.span.start_line,
                            "module": module_name,
                            "signature": "",
                            "docstring": decl.doc_comment or "",
                        }
                    )
                elif isinstance(decl, ConstantDef):
                    symbols.append(
                        {
                            "name": decl.name,
                            "verb": "constant",
                            "kind": "constant",
                            "file": rel,
                            "line": decl.span.start_line,
                            "module": module_name,
                            "signature": "",
                            "docstring": decl.doc_comment or "",
                        }
                    )
                elif isinstance(decl, ModuleDecl):
                    for td in decl.types:
                        _collect(td)
                    for cd in decl.constants:
                        _collect(cd)
                    for sub in decl.body:
                        _collect(sub)

            for decl in module.declarations:
                _collect(decl)
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
        from prove.config import _RESERVED_SRC_DIRS

        for prv_file in sorted(self.project_root.rglob("*.prv")):
            if _RESERVED_SRC_DIRS & set(prv_file.relative_to(self.project_root).parts):
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

    def _manifest_path(self) -> Path:
        return self.cache_dir / "manifest.json"

    def _write_manifest(self) -> None:
        import json
        import time

        files: dict[str, dict] = {}
        for path_str in self._file_ngrams:
            p = Path(path_str)
            try:
                st = p.stat()
                files[str(p.relative_to(self.project_root))] = {
                    "mtime": int(st.st_mtime),
                    "size": st.st_size,
                }
            except OSError:
                pass
        manifest = {
            "cache_version": self._CACHE_VERSION,
            "indexed_at": int(time.time()),
            "files": files,
        }
        self._manifest_path().write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    def _read_manifest(self) -> dict | None:
        import json

        try:
            data = json.loads(self._manifest_path().read_text(encoding="utf-8"))
            if data.get("cache_version") != self._CACHE_VERSION:
                return None  # incompatible version → treat as missing
            return data
        except Exception:
            return None

    def is_cache_valid(self) -> bool:
        """True if manifest exists, version matches, and all tracked files are unchanged."""
        manifest = self._read_manifest()
        if manifest is None:
            return False
        files = manifest.get("files", {})
        if not files:
            return False
        for rel, info in files.items():
            p = self.project_root / rel
            try:
                st = p.stat()
                if int(st.st_mtime) != info["mtime"] or st.st_size != info["size"]:
                    return False
            except OSError:
                return False  # file deleted → stale
        # Also check for new .prv files not in manifest
        from prove.config import _RESERVED_SRC_DIRS

        for prv in self.project_root.rglob("*.prv"):
            if _RESERVED_SRC_DIRS & set(prv.relative_to(self.project_root).parts):
                continue
            rel = str(prv.relative_to(self.project_root))
            if rel not in files:
                return False  # new file → stale
        return True

    def load(self) -> bool:
        """Restore in-memory tables from cache. Returns True on success."""
        try:
            from prove.store_binary import read_pdat

            bigrams_path = self.cache_dir / "bigrams" / "current.bin"
            completions_path = self.cache_dir / "completions" / "current.bin"
            if not bigrams_path.exists() or not completions_path.exists():
                return False
            bigrams_data = read_pdat(bigrams_path)
            for _, row in bigrams_data["variants"]:
                prev1, nxt, count = row[0], row[1], int(row[2])
                self._bigrams[prev1][nxt] = count
            completions_data = read_pdat(completions_path)
            for _, row in completions_data["variants"]:
                p2, p1, top = row[0], row[1], row[2]
                for tok in top.split("|"):
                    if tok:
                        self._completions[(p2, p1)][tok] += 1
            # Rebuild symbol table from manifest file list (re-parse symbols — cheap)
            manifest = self._read_manifest()
            if manifest:
                for rel in manifest["files"]:
                    p = self.project_root / rel
                    _, symbols = self._extract_file(p)
                    for sym in symbols:
                        self._symbols[sym["name"]] = sym
                    self._file_ngrams[str(p)] = []  # mark as indexed
                    self._file_symbols[str(p)] = symbols
            return True
        except Exception:
            return False

    def save(self) -> None:
        """Write in-memory tables to .prove/cache/ as PDAT binary files."""
        try:
            self._write_bigrams_cache()
            self._write_completions_cache()
            self._write_manifest()
        except Exception:
            pass  # Cache failures are non-fatal

    def _write_bigrams_cache(self, top_k: int = 5) -> None:
        from prove.store_binary import write_pdat

        out = self.cache_dir / "bigrams" / "current.bin"
        out.parent.mkdir(parents=True, exist_ok=True)
        (out.parent / "versions").mkdir(exist_ok=True)
        columns = ["String", "String", "Integer"]
        variants: list[tuple[str, list[str]]] = []
        i = 0
        for prev1, counter in self._bigrams.items():
            for nxt, count in counter.most_common(top_k):
                variants.append((f"r{i:05d}", [prev1, nxt, str(count)]))
                i += 1
        write_pdat(out, "ProjectBigram", columns, variants)

    def _write_completions_cache(self, top_k: int = 5) -> None:
        from prove.store_binary import write_pdat

        out = self.cache_dir / "completions" / "current.bin"
        out.parent.mkdir(parents=True, exist_ok=True)
        (out.parent / "versions").mkdir(exist_ok=True)
        columns = ["String", "String", "String"]
        variants: list[tuple[str, list[str]]] = []
        for i, ((p2, p1), counter) in enumerate(self._completions.items()):
            top = "|".join(tok for tok, _ in counter.most_common(top_k))
            variants.append((f"r{i:05d}", [p2, p1, top]))
        write_pdat(out, "ProjectCompletion", columns, variants)

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


# ── .intent file support ─────────────────────────────────────────────


@dataclass
class IntentDocumentState:
    """Cached analysis results for an open .intent file."""

    source: str = ""
    project: object | None = None  # IntentProject
    diagnostics: list[lsp.Diagnostic] = field(default_factory=list)


_intent_state: dict[str, IntentDocumentState] = {}

_INTENT_SEVERITY_MAP = {
    "error": lsp.DiagnosticSeverity.Error,
    "warning": lsp.DiagnosticSeverity.Warning,
    "info": lsp.DiagnosticSeverity.Information,
}

# Verbs recognized in .intent files (for completions)
_INTENT_VERBS = [
    "validates",
    "transforms",
    "reads",
    "creates",
    "matches",
    "inputs",
    "outputs",
    "streams",
    "listens",
    "detached",
    "attached",
]

_INTENT_KEYWORDS = [
    "project",
    "purpose",
    "domain",
    "vocabulary",
    "module",
    "flow",
    "constraints",
]


def _is_intent_uri(uri: str) -> bool:
    """True if the URI points to a .intent file."""
    return uri.endswith(".intent")


def _analyze_intent(uri: str, source: str) -> IntentDocumentState:
    """Parse an .intent file and return diagnostics."""
    from prove.intent_parser import parse_intent

    ids = IntentDocumentState(source=source)
    diags: list[lsp.Diagnostic] = []

    result = parse_intent(source, uri)
    ids.project = result.project

    for d in result.diagnostics:
        line = max(d.line - 1, 0)
        sev = _INTENT_SEVERITY_MAP.get(d.severity, lsp.DiagnosticSeverity.Warning)
        code = d.code or "I000"
        diags.append(
            lsp.Diagnostic(
                range=lsp.Range(
                    start=lsp.Position(line=line, character=0),
                    end=lsp.Position(line=line, character=1000),
                ),
                severity=sev,
                source="prove-intent",
                code=code,
                message=f"[{code}] {d.message}" if d.code else d.message,
            )
        )

    # Post-parse checks (only if project parsed successfully)
    if result.project is not None:
        project = result.project
        # W602: vocabulary term defined but never referenced
        for vocab in project.vocabulary:
            referenced = False
            for mod in project.modules:
                mod_text = " ".join(f"{i.verb} {i.noun} {i.context}" for i in mod.intents).lower()
                if vocab.name.lower() in mod_text:
                    referenced = True
                    break
            if not referenced:
                diags.append(
                    lsp.Diagnostic(
                        range=lsp.Range(
                            start=lsp.Position(0, 0),
                            end=lsp.Position(0, 1000),
                        ),
                        severity=lsp.DiagnosticSeverity.Warning,
                        source="prove-intent",
                        code="W602",
                        message=(
                            f"[W602] vocabulary term '{vocab.name}' is defined but never referenced"
                        ),
                    )
                )

        # W603: flow references a module not defined in project.modules
        defined_modules = {m.name for m in project.modules}
        for flow in project.flows:
            for step in flow.steps:
                if step.module not in defined_modules:
                    diags.append(
                        lsp.Diagnostic(
                            range=lsp.Range(
                                start=lsp.Position(0, 0),
                                end=lsp.Position(0, 1000),
                            ),
                            severity=lsp.DiagnosticSeverity.Warning,
                            source="prove-intent",
                            code="W603",
                            message=f"[W603] flow references undefined module '{step.module}'",
                        )
                    )

    ids.diagnostics = diags
    _intent_state[uri] = ids
    return ids


def _intent_completions(source: str, position: lsp.Position) -> list[lsp.CompletionItem]:
    """Return context-aware completions for .intent files."""
    items: list[lsp.CompletionItem] = []
    lines = source.splitlines()
    line_idx = position.line
    current_line = lines[line_idx] if line_idx < len(lines) else ""

    # Detect current section by scanning upward
    section: str | None = None
    for i in range(line_idx, -1, -1):
        ln = lines[i].strip() if i < len(lines) else ""
        if ln.startswith("module "):
            section = "module"
            break
        if ln == "vocabulary":
            section = "vocabulary"
            break
        if ln == "flow":
            section = "flow"
            break
        if ln == "constraints":
            section = "constraints"
            break
        if ln.startswith("project "):
            section = "project"
            break

    indent = len(current_line) - len(current_line.lstrip())

    if section == "module" and indent >= 2:
        # Inside a module block: suggest verbs
        for verb in _INTENT_VERBS:
            items.append(
                lsp.CompletionItem(
                    label=verb,
                    kind=lsp.CompletionItemKind.Keyword,
                    detail="intent verb",
                )
            )
    elif section == "flow" and indent >= 2:
        # Inside a flow block: suggest module names from current state
        for uri, ids in _intent_state.items():
            if ids.project is not None:
                for mod in ids.project.modules:
                    items.append(
                        lsp.CompletionItem(
                            label=mod.name,
                            kind=lsp.CompletionItemKind.Module,
                            detail="module",
                        )
                    )
                break
    elif section == "vocabulary" and indent >= 2:
        # Suggest vocabulary structure
        items.append(
            lsp.CompletionItem(
                label="Name is description",
                kind=lsp.CompletionItemKind.Snippet,
                detail="vocabulary entry",
                insert_text="Name is ",
            )
        )
    elif indent < 2 or section == "project":
        # Top-level: suggest section keywords
        for kw in _INTENT_KEYWORDS:
            items.append(
                lsp.CompletionItem(
                    label=kw,
                    kind=lsp.CompletionItemKind.Keyword,
                    detail=".intent keyword",
                )
            )

    return items


def _intent_code_actions(
    uri: str,
    ids: IntentDocumentState,
) -> list[lsp.CodeAction]:
    """Return code actions for .intent files."""
    actions: list[lsp.CodeAction] = []
    if ids.project is None:
        return actions

    from prove.intent_generator import generate_module_source

    for mod in ids.project.modules:
        source = generate_module_source(mod, ids.project)

        # Determine output path
        file_path = uri[7:] if uri.startswith("file://") else uri
        project_dir = Path(file_path).parent
        prv_path = project_dir / f"{mod.name.lower()}.prv"
        prv_uri = f"file://{prv_path}"

        actions.append(
            lsp.CodeAction(
                title=f"Generate {mod.name.lower()}.prv from intent",
                kind=lsp.CodeActionKind.Source,
                edit=lsp.WorkspaceEdit(
                    document_changes=[
                        lsp.CreateFile(
                            uri=prv_uri,
                            kind="create",
                            options=lsp.CreateFileOptions(overwrite=True),
                        ),
                        lsp.TextDocumentEdit(
                            text_document=lsp.OptionalVersionedTextDocumentIdentifier(
                                uri=prv_uri,
                                version=None,
                            ),
                            edits=[
                                lsp.TextEdit(
                                    range=lsp.Range(
                                        start=lsp.Position(0, 0),
                                        end=lsp.Position(0, 0),
                                    ),
                                    new_text=source,
                                )
                            ],
                        ),
                    ],
                ),
            )
        )

    return actions


def _ensure_project_indexed(uri: str) -> None:
    """Create and populate project indexer for uri's project (once per session)."""
    global _project_indexer
    if _project_indexer is None:
        _project_indexer = _ProjectIndexer.for_uri(uri)
    if _project_indexer is None:
        return
    if _project_indexer._file_ngrams:
        return  # already populated this session

    # Try warm load first
    if _project_indexer.is_cache_valid():
        if _project_indexer.load():
            return  # warm start — no file parsing needed

    # Cache missing, stale, or corrupt → full reindex
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
    Searches the project src/ directory (including subdirectories) when a
    prove.toml is found, falling back to the file's parent directory.
    """
    from pathlib import Path

    from prove.config import discover_prv_files
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

    # Try to find project root for subdirectory discovery
    try:
        from prove.config import find_config

        config_path = find_config(file_path)
        src_dir = config_path.parent / "src"
        if not src_dir.is_dir():
            src_dir = config_path.parent
        prv_files = discover_prv_files(src_dir)
    except (FileNotFoundError, Exception):
        # Fallback: look for .prv files in parent directory (including subdirs)
        prv_files = discover_prv_files(file_path.parent)

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
        for type_name in info.types:  # noqa: F402
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

        # Index exported constants
        for const_name in info.constants:
            index.setdefault(const_name, []).append(
                ImportSuggestion(
                    module=module_name,
                    verb="constants",
                    name=const_name,
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
        checker._coherence = True  # always run coherence in editor (shown as warnings)
        symbols = checker.check(module)
        ds.symbols = symbols
        ds.local_import_index = _build_local_import_index(local_modules)
        ds.prove_diagnostics = checker.diagnostics
        ds.inlay_type_map = checker.inlay_type_map
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


def _extract_row_context_tokens(source: str, position: lsp.Position, n: int = 2) -> list[str]:
    """Return the last n non-whitespace tokens from the current row only (before cursor).

    Unlike _extract_context_tokens, this never crosses line boundaries — the
    entire current row is available as context. Returns '<START>' sentinels
    when fewer than n tokens exist on the row.
    """
    lines = source.splitlines()
    line_idx = position.line
    col = position.character

    if line_idx >= len(lines):
        return ["<START>"] * n

    row_text = lines[line_idx][:col]

    try:
        tokens = Lexer(row_text, "<completion>").lex()
    except Exception:
        return ["<START>"] * n

    filtered = [t for t in tokens if t.kind not in _INDEXER_SKIP_KINDS]
    result: list[str] = []
    for tok in filtered[-n:]:
        result.append(_tok_text(tok.kind, tok.value))
    while len(result) < n:
        result.insert(0, "<START>")
    return result


# ── Prose context detection (Phase 5a) ───────────────────────────────────

_PROSE_BLOCK_KEYWORDS = frozenset({"intent", "chosen", "why_not"})

# English synonyms shown in prose blocks — shared canonical map from _nl_intent.
_ALL_PROSE_VERB_WORDS: list[str] = [w for words in _VERB_PROSE_HINTS.values() for w in words]


def _cursor_in_triple_quote_block(lines: list[str], line_idx: int, keyword: str) -> bool:
    """True if line_idx is between a `keyword: \"\"\"` and its closing `\"\"\"`."""
    open_line: int | None = None
    for i in range(line_idx, -1, -1):
        stripped = lines[i].lstrip()
        if stripped.startswith(keyword) and '"""' in lines[i]:
            open_line = i
            break
        if '"""' in lines[i] and i < line_idx:
            return False
    if open_line is None or open_line == line_idx:
        return False
    for i in range(open_line + 1, line_idx):
        if '"""' in lines[i]:
            return False
    return True


def _cursor_in_explain_block(lines: list[str], line_idx: int) -> bool:
    """True if line_idx is an indented content line inside an explain block."""
    current_indent = len(lines[line_idx]) - len(lines[line_idx].lstrip())
    for i in range(line_idx - 1, -1, -1):
        line = lines[i]
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip())
        if indent < current_indent and line.lstrip().startswith("explain"):
            return True
        if indent < current_indent:
            break
    return False


def _find_enclosing_fd(module: Module | None, line_idx: int) -> FunctionDef | None:
    """Return the FunctionDef whose span contains the given 0-indexed line."""
    if module is None:
        return None
    target = line_idx + 1  # spans are 1-indexed
    for decl in module.declarations:
        if isinstance(decl, FunctionDef):
            if decl.span.start_line <= target <= decl.span.end_line:
                return decl
    return None


def _prose_context(
    source: str,
    position: lsp.Position,
    module: Module | None,
) -> tuple[str | None, FunctionDef | None]:
    """Return (context_kind, enclosing_fd) when cursor is inside a prose block.

    context_kind is one of: "narrative", "explain", "intent", "chosen", "why_not".
    Returns (None, None) when cursor is in normal code.
    """
    lines = source.splitlines()
    line_idx = position.line
    if line_idx >= len(lines):
        return None, None
    current = lines[line_idx]
    stripped = current.lstrip()

    for kw in _PROSE_BLOCK_KEYWORDS:
        if stripped.startswith(f"{kw}:") or stripped == kw:
            fd = _find_enclosing_fd(module, line_idx)
            return kw, fd

    if _cursor_in_triple_quote_block(lines, line_idx, "narrative:"):
        return "narrative", None

    if _cursor_in_explain_block(lines, line_idx):
        fd = _find_enclosing_fd(module, line_idx)
        return "explain", fd

    return None, None


def _prose_completions(
    context_kind: str,
    fd: FunctionDef | None,
    module: Module | None,
) -> list[lsp.CompletionItem]:
    """Return context-sensitive completions for prose blocks."""
    items: list[lsp.CompletionItem] = []

    def _text(word: str, detail: str, sort_prefix: str = "0") -> lsp.CompletionItem:
        return lsp.CompletionItem(
            label=word,
            kind=lsp.CompletionItemKind.Text,
            detail=detail,
            sort_text=f"\x00{sort_prefix}_{word}",
            label_details=lsp.CompletionItemLabelDetails(description=detail),
        )

    if context_kind == "narrative":
        existing_narrative = ""
        if module is not None:
            for decl in module.declarations:
                if isinstance(decl, ModuleDecl) and decl.narrative:
                    existing_narrative = decl.narrative
                    break
        from prove._nl_intent import implied_verbs

        already_implied = implied_verbs(existing_narrative)
        for word in _ALL_PROSE_VERB_WORDS:
            prove_verb = next((v for v, words in _VERB_PROSE_HINTS.items() if word in words), "")
            sort = "0" if prove_verb in already_implied else "1"
            items.append(_text(word, f"→ {prove_verb}", sort))
        if module is not None:
            for decl in module.declarations:
                if isinstance(decl, FunctionDef):
                    items.append(_text(decl.name.replace("_", " "), "function", "2"))

    elif context_kind == "explain":
        if fd is not None:
            from prove._nl_intent import body_tokens

            for tok in sorted(body_tokens(fd)):
                items.append(_text(tok, "body", "0"))
            for word in _VERB_PROSE_HINTS.get(fd.verb, []):
                items.append(_text(word, fd.verb, "1"))

    elif context_kind == "intent":
        if fd is not None:
            for p in fd.params:
                items.append(_text(p.name, "param", "0"))
            starters = {
                "transforms": [f"Transforms {p.name} into" for p in fd.params[:1]],
                "validates": [f"Validates {p.name}" for p in fd.params[:1]],
                "reads": [f"Reads {p.name} from" for p in fd.params[:1]],
                "creates": ["Creates a new"],
                "outputs": ["Outputs"],
            }
            for phrase in starters.get(fd.verb, []):
                items.append(_text(phrase, "phrase", "1"))

    elif context_kind == "chosen":
        if fd is not None:
            from prove._nl_intent import body_tokens

            for tok in sorted(body_tokens(fd)):
                items.append(_text(tok, "body", "0"))
            for word in _VERB_PROSE_HINTS.get(fd.verb, []):
                items.append(_text(word, fd.verb, "0"))
            starters = {
                "transforms": ["linear scan because", "recursive because", "iterative because"],
                "validates": ["early-exit because", "regex because", "range check because"],
                "reads": ["lazy load because", "cached read because"],
                "creates": ["builder pattern because", "factory because"],
                "matches": ["pattern match because", "lookup table because"],
            }
            for phrase in starters.get(fd.verb, []):
                items.append(_text(phrase, "approach", "1"))

    elif context_kind == "why_not":
        if fd is not None and module is not None:
            for decl in module.declarations:
                if isinstance(decl, FunctionDef) and decl.name != fd.name:
                    items.append(_text(decl.name, "function", "0"))
            alt_phrases = [
                "hash map because",
                "binary search because",
                "linear scan because",
                "recursive approach because",
                "lookup table because",
                "regex because",
                "manual parse because",
                "eager evaluation because",
                "lazy evaluation because",
            ]
            for phrase in alt_phrases:
                items.append(_text(phrase, "alternative", "1"))

    return items


# ── From-block body generation (Phase 6) ───────────────────────────────


def _find_fd_at_cursor(source: str, position: lsp.Position) -> FunctionDef | None:
    """Return the FunctionDef whose span contains the given 0-indexed position."""
    lines = source.splitlines()
    line_idx = position.line
    col = position.character
    truncated_lines = lines[:line_idx]
    if line_idx < len(lines):
        truncated_lines.append(lines[line_idx][:col])
    truncated = "\n".join(truncated_lines)

    try:
        tokens = Lexer(truncated, "<completion>").lex()
        module = Parser(tokens, "<completion>").parse()
    except Exception:
        return None

    target = line_idx + 1
    for decl in module.declarations:
        if isinstance(decl, FunctionDef):
            if decl.span.start_line <= target <= decl.span.end_line:
                return decl
    return None


def _is_in_from_block(source: str, position: lsp.Position) -> bool:
    """True if the cursor is inside a `from` block (after the `from` keyword line)."""
    lines = source.splitlines()
    line_idx = position.line
    if line_idx >= len(lines):
        return False

    current_indent = len(lines[line_idx]) - len(lines[line_idx].lstrip())
    if current_indent <= 0:
        return False

    for i in range(line_idx - 1, -1, -1):
        line = lines[i]
        stripped = line.strip()
        if not stripped:
            continue
        indent = len(line) - len(line.lstrip())
        if indent < current_indent and stripped == "from":
            return True
        if indent < current_indent:
            return False
    return False


def _generate_from_block_snippet(
    fd: FunctionDef,
    module: Module | None,
) -> str:
    """Generate a complete `from` block body for a function definition."""
    param_names = [p.name for p in fd.params]
    nouns = [p.name for p in fd.params]

    body = generate_body(
        verb=fd.verb or "transforms",
        name=fd.name,
        nouns=nouns,
        param_names=param_names,
        declaration_text=fd.doc_comment or None,
    )

    if not body.stmts:
        return "    todo"

    lines: list[str] = []
    for stmt in body.stmts:
        lines.append(f"    {stmt.code}")

    return "\n".join(lines)


def _from_block_completions(
    source: str,
    position: lsp.Position,
    ds: DocumentState | None,
) -> list[lsp.CompletionItem]:
    """Return body-generation completions when inside a `from` block.

    Uses the enclosing function's signature to generate the full from-block
    via the body generation engine.
    """
    if not _is_in_from_block(source, position):
        return []

    fd = _find_fd_at_cursor(source, position)
    if fd is None:
        return []

    snippet = _generate_from_block_snippet(fd, ds.module if ds else None)
    if not snippet.strip():
        return []

    lines = snippet.splitlines()
    if len(lines) == 1:
        return [
            lsp.CompletionItem(
                label=lines[0].strip(),
                kind=lsp.CompletionItemKind.Snippet,
                detail="generated body",
                insert_text=snippet,
                insert_text_format=lsp.InsertTextFormat.Snippet,
                sort_text="\x00gen_body",
                label_details=lsp.CompletionItemLabelDetails(description="generated"),
            )
        ]

    return [
        lsp.CompletionItem(
            label=f"from... ({len(lines)} lines)",
            kind=lsp.CompletionItemKind.Snippet,
            detail=f"Generate {fd.verb} {fd.name} body",
            insert_text=snippet + "\n",
            insert_text_format=lsp.InsertTextFormat.Snippet,
            sort_text="\x00gen_body",
            label_details=lsp.CompletionItemLabelDetails(description="generated"),
        )
    ]


# ── From-block n-gram model (Phase 6) ────────────────────────────────


def _from_block_ngram_complete(
    source: str,
    position: lsp.Position,
    top_k: int = 5,
) -> list[str]:
    """Return n-gram completions for from-block token sequences."""
    try:
        model = load_lsp_from_blocks()
    except Exception:
        return []

    row_context = _extract_row_context_tokens(source, position, n=2)
    if row_context[1] != "<START>":
        # Current row has tokens — use them for tightest context
        prev2, prev1 = row_context[0], row_context[1]
    else:
        context = _extract_context_tokens(source, position, n=2)
        prev2, prev1 = context[0], context[1]

    lines = source.splitlines()
    line_idx = position.line
    col = position.character
    prefix = ""
    if line_idx < len(lines):
        text = lines[line_idx][:col]
        m = re.search(r"[\w<>_]+$", text)
        if m:
            prefix = m.group()

    results: list[str] = []
    for tok in model.get((prev2, prev1), []):
        if not prefix or tok.startswith(prefix):
            results.append(tok)
        if len(results) >= top_k:
            break

    if not results:
        for tok in model.get(("<START>", prev1), []):
            if not prefix or tok.startswith(prefix):
                results.append(tok)
            if len(results) >= top_k:
                break

    return results


def _from_block_ngram_completions(
    source: str,
    position: lsp.Position,
) -> list[lsp.CompletionItem]:
    """Return multi-token snippet completions from the from-block n-gram model."""
    if not _is_in_from_block(source, position):
        return []

    tokens = _from_block_ngram_complete(source, position)
    if not tokens:
        return []

    items: list[lsp.CompletionItem] = []
    for tok in tokens:
        if tok.startswith("<") or tok.startswith('"'):
            continue
        try:
            float(tok)
            continue
        except ValueError:
            pass

        items.append(
            lsp.CompletionItem(
                label=tok,
                kind=lsp.CompletionItemKind.Text,
                detail="from-block ml",
                sort_text="\x00from_ml",
                label_details=lsp.CompletionItemLabelDetails(description="ml"),
            )
        )
    return items[:10]


def _ml_completions(
    source: str,
    position: lsp.Position,
    ds: DocumentState | None = None,
) -> list[lsp.CompletionItem]:
    """Return ML-ranked completion items from the project indexer + global model.

    Project suggestions are prepended (rank higher). Falls back to unigram
    if no bigram match. Gracefully returns [] if indexer is unavailable.
    """
    if _project_indexer is None:
        return []

    row_context = _extract_row_context_tokens(source, position, n=2)
    if row_context[1] != "<START>":
        # Current row has tokens — use them for tightest context
        prev2, prev1 = row_context[0], row_context[1]
    else:
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

    # Project symbols — context-filtered so we don't flood every completion
    _VERB_KEYWORDS = frozenset(
        {"transforms", "validates", "inputs", "outputs", "reads", "creates", "matches"}
    )
    _TYPE_TRIGGERS = frozenset({"as", "is", "type", "Result", "Option", "List"})
    want_functions = prev1 in _VERB_KEYWORDS
    want_types = prev1 in _TYPE_TRIGGERS
    # With a prefix: show matching symbols of the right kind
    # Without a prefix: only show when context clearly calls for it
    symbol_hits: list[tuple[str, str]] = []  # (name, verb)
    for name, sym in _project_indexer._symbols.items():
        verb = sym.get("verb", "")
        kind = sym.get("kind", "")
        if prefix and not name.startswith(prefix):
            continue
        if not prefix and not want_functions and not want_types:
            continue  # no prefix + no clear context = skip
        if want_types and kind not in ("type",):
            continue
        if want_functions and kind not in ("function",):
            continue
        symbol_hits.append((name, verb))
    symbol_hits.sort(key=lambda x: x[0])

    # Merge: project ngrams first, then global ngrams — deduplicated
    seen_toks: set[str] = set()
    merged: list[str] = []
    for tok in project_hits + global_hits:
        # Skip sentinels and raw string/number literals
        if tok in seen_toks or tok.startswith("<") or tok.startswith('"'):
            continue
        try:
            float(tok)
            continue  # skip bare number tokens
        except ValueError:
            pass
        seen_toks.add(tok)
        merged.append(tok)

    items: list[lsp.CompletionItem] = []

    # Project symbols first (highest priority — directly defined in this project)
    for name, verb in symbol_hits:
        seen_toks.add(name)
        sym = _project_indexer._symbols[name]
        mod_name = sym.get("module")
        kind = sym.get("kind", "")
        signature = sym.get("signature", "")
        docstring = sym.get("docstring", "")

        # Auto-import edit: insert `use ModuleName` if symbol is from another module
        additional_edits: list[lsp.TextEdit] | None = None
        if ds is not None and mod_name:
            suggestion = ImportSuggestion(module=mod_name, verb=verb or None, name=name)
            edit = _build_import_edit(ds, suggestion)
            if edit is not None:
                additional_edits = [edit]

        # Documentation: signature + docstring, same format as stdlib completions
        sig_line = f"{verb} {name}{signature}" if verb else f"{name}{signature}"
        if docstring:
            doc_value = f"```prove\n{sig_line}\n```\n---\n{docstring}"
        else:
            doc_value = f"```prove\n{sig_line}\n```"

        items.append(
            lsp.CompletionItem(
                label=name,
                kind=(
                    lsp.CompletionItemKind.Class
                    if kind == "type"
                    else lsp.CompletionItemKind.Constant
                    if kind == "constant"
                    else lsp.CompletionItemKind.Function
                ),
                detail=mod_name or "project",
                documentation=lsp.MarkupContent(
                    kind=lsp.MarkupKind.Markdown,
                    value=doc_value,
                ),
                sort_text=f"\x00p_{name}",
                label_details=lsp.CompletionItemLabelDetails(
                    detail=f" {verb}" if verb else None,
                    description=mod_name or "project",
                ),
                additional_text_edits=additional_edits,
            )
        )

    for i, tok in enumerate(merged[:10]):
        if tok in seen_toks:
            continue
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
# Uses prove.data package (via nlp_store.py) for pip-installed data.
# Falls back gracefully if the store files are missing (e.g. dev mode).


def _global_model_complete(prev2: str, prev1: str, prefix: str = "", top_k: int = 5) -> list[str]:
    """Query global LSP ML model; falls back to unigram. Returns [] if model not loaded."""
    try:
        completions = load_lsp_completions()
    except Exception:
        return []

    results: list[str] = []
    for tok in completions.get((prev2, prev1), []):
        if not prefix or tok.startswith(prefix):
            results.append(tok)
        if len(results) >= top_k:
            break

    if not results:
        try:
            bigrams = load_lsp_bigrams()
            for tok, _count in bigrams.get(prev1, []):
                if not prefix or tok.startswith(prefix):
                    results.append(tok)
                if len(results) >= top_k:
                    break
        except Exception:
            pass

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
    if _is_intent_uri(uri):
        ids = _analyze_intent(uri, source)
        server.text_document_publish_diagnostics(
            lsp.PublishDiagnosticsParams(uri=uri, diagnostics=ids.diagnostics)
        )
        return
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
    if _is_intent_uri(uri):
        ids = _analyze_intent(uri, source)
        server.text_document_publish_diagnostics(
            lsp.PublishDiagnosticsParams(uri=uri, diagnostics=ids.diagnostics)
        )
        return
    ds = _analyze(uri, source)
    server.text_document_publish_diagnostics(
        lsp.PublishDiagnosticsParams(
            uri=uri,
            diagnostics=ds.diagnostics,
        )
    )
    # Patch indexer with unsaved content so completions reflect current edits
    if _project_indexer is not None and uri.startswith("file://"):
        path = Path(uri[7:])
        if path.suffix == ".prv":
            try:
                _project_indexer.patch_file(path, source)
            except Exception:
                pass


@server.feature(lsp.TEXT_DOCUMENT_DID_CLOSE)
def did_close(params: lsp.DidCloseTextDocumentParams) -> None:
    uri = params.text_document.uri
    _state.pop(uri, None)
    _intent_state.pop(uri, None)


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
    if _is_intent_uri(uri):
        ids = _intent_state.get(uri)
        source = ids.source if ids else ""
        items = _intent_completions(source, params.position)
        return lsp.CompletionList(is_incomplete=False, items=items)
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

    for type_name in _TYPE_BUILTINS:  # noqa: F402
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
            # Label shows module + verb + name (e.g., "System outputs console")
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

    # Phase 5b — from-block body generation (highest priority when in `from` block)
    source = ds.source if ds else ""
    from_items = _from_block_completions(source, params.position, ds)
    if from_items:
        # Also add n-gram suggestions for partial tokens
        ngram_items = _from_block_ngram_completions(source, params.position)
        # Prepend generated items but keep stdlib/symbol items so imported
        # and auto-import function suggestions remain visible.
        items = from_items + ngram_items + items

    # Phase 5a — prose-mode completions (suppress ML n-gram items in prose context)
    if ds is not None and ds.module is not None:
        prose_kind, prose_fd = _prose_context(ds.source, params.position, ds.module)
        if prose_kind is not None:
            prose_items = _prose_completions(prose_kind, prose_fd, ds.module)
            items = prose_items + items
            seen_prose: dict[tuple[str, str], lsp.CompletionItem] = {}
            for item in items:
                key = (item.label, item.sort_text or item.label)
                if key not in seen_prose or item.detail:
                    seen_prose[key] = item
            return lsp.CompletionList(is_incomplete=False, items=list(seen_prose.values()))

    # Phase 5 — ML completion suggestions
    if _project_indexer is not None and ds is not None:
        ml_items = _ml_completions(ds.source, params.position, ds=ds)
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

    # Look up symbol — only use for locally-defined (non-imported) symbols
    sym = ds.symbols.lookup(word)
    if sym is not None and not sym.is_imported and sym.span.file != "<builtin>":
        return lsp.Location(
            uri=uri,
            range=span_to_range(sym.span),
        )

    # Local variables inside function bodies take priority (VarDecl, params)
    if ds.module is not None:
        loc = _find_local_var_definition(word, params.position, ds)
        if loc is not None:
            return loc

    # For imported symbols (or fallback), resolve via FunctionSignature which
    # carries the actual declaration span in the source file.
    sig = ds.symbols.resolve_function_any(word)
    if sig is not None and sig.span.file not in ("<builtin>", "<stdlib>"):
        loc = _resolve_sig_location(sig, uri)
        if loc is not None:
            return loc

    # Imported constants and types: find the definition in the source module
    if sym is not None and sym.is_imported:
        loc = _resolve_imported_symbol(word, uri, ds)
        if loc is not None:
            return loc

    return None


def _resolve_sig_location(sig: FunctionSignature, current_uri: str) -> lsp.Location | None:
    """Build an LSP Location from a FunctionSignature's span."""
    from pathlib import Path

    span_file = sig.span.file
    if span_file.startswith("<stdlib:"):
        from prove.stdlib_loader import stdlib_prv_path

        module_name = span_file[len("<stdlib:") : -1]
        prv_path = stdlib_prv_path(module_name)
        if prv_path is not None and prv_path.exists():
            return lsp.Location(uri=prv_path.as_uri(), range=span_to_range(sig.span))
    else:
        return lsp.Location(uri=Path(span_file).as_uri(), range=span_to_range(sig.span))
    return None


def _resolve_imported_symbol(name: str, uri: str, ds: DocumentState) -> lsp.Location | None:
    """Find the definition of an imported constant or type in sibling modules."""
    from pathlib import Path

    if uri.startswith("file://"):
        file_path = Path(uri[7:])
    elif uri.startswith("/"):
        file_path = Path(uri)
    else:
        return None

    parent = file_path.parent

    # Find which module the symbol is imported from by checking import declarations
    if ds.module is None:
        return None

    from prove.ast_nodes import ModuleDecl

    source_module: str | None = None
    for decl in ds.module.declarations:
        if isinstance(decl, ModuleDecl):
            for imp in decl.imports:
                for item in imp.items:
                    if item.name == name:
                        source_module = imp.module
                        break
                if source_module:
                    break
            break

    if source_module is None:
        return None

    # Check stdlib first
    from prove.stdlib_loader import is_stdlib_module, stdlib_prv_path

    if is_stdlib_module(source_module):
        prv_path = stdlib_prv_path(source_module)
        if prv_path is not None and prv_path.exists():
            loc = _find_name_in_file(name, prv_path)
            if loc is not None:
                return loc

    # Look for a local module file: <module_name>.prv (lowercased)
    for prv_file in parent.glob("*.prv"):
        stem = prv_file.stem
        # Module names are CamelCase; file stems may be lower or mixed
        if stem.lower() == source_module.lower() or stem == source_module:
            loc = _find_name_in_file(name, prv_file)
            if loc is not None:
                return loc

    return None


def _find_name_in_file(name: str, file_path: Path) -> lsp.Location | None:
    """Search a .prv file for a constant or type definition by name."""
    import re

    try:
        source = file_path.read_text()
    except OSError:
        return None

    for i, line in enumerate(source.splitlines()):
        # Match constant: `NAME as Type = ...` or `NAME = ...`
        if re.match(rf"\s*{re.escape(name)}\s+as\s+", line) or re.match(
            rf"\s*{re.escape(name)}\s*=\s*", line
        ):
            col = line.index(name)
            return lsp.Location(
                uri=file_path.as_uri(),
                range=lsp.Range(
                    start=lsp.Position(line=i, character=col),
                    end=lsp.Position(line=i, character=col + len(name)),
                ),
            )
        # Match type definition (record/algebraic)
        if re.match(rf"\s*{re.escape(name)}\s*$", line) or re.match(
            rf"\s*{re.escape(name)}\s", line
        ):
            # Check if next line looks like a type body (field definitions)
            lines = source.splitlines()
            if i + 1 < len(lines) and re.match(r"\s+\w+\s+\w+", lines[i + 1]):
                col = line.index(name)
                return lsp.Location(
                    uri=file_path.as_uri(),
                    range=lsp.Range(
                        start=lsp.Position(line=i, character=col),
                        end=lsp.Position(line=i, character=col + len(name)),
                    ),
                )

    return None


def _find_local_var_definition(
    name: str, position: lsp.Position, ds: DocumentState
) -> lsp.Location | None:
    """Find a local variable definition in the AST near the cursor position."""
    from prove.ast_nodes import FunctionDef, MainDef

    if ds.module is None:
        return None

    # Recover the URI from the state cache
    uri = ""
    for cached_uri, cached_ds in _state.items():
        if cached_ds is ds:
            uri = cached_uri
            break

    # Find the function containing the cursor
    cursor_line = position.line + 1  # 1-indexed
    for decl in ds.module.declarations:
        if not isinstance(decl, (FunctionDef, MainDef)):
            continue
        if decl.span.start_line <= cursor_line <= decl.span.end_line:
            # Search this function's body for VarDecl (including nested match arms)
            found = _search_body_for_var(name, decl.body)
            if found is not None:
                return lsp.Location(uri=uri, range=span_to_range(found.span))
            # Also check function parameters (FunctionDef only)
            if isinstance(decl, FunctionDef):
                for param in decl.params:
                    if param.name == name:
                        return lsp.Location(uri=uri, range=span_to_range(param.span))
            break

    return None


def _search_body_for_var(name: str, body: list) -> VarDecl | None:
    """Recursively search a statement list for a VarDecl with the given name."""
    from prove.ast_nodes import ExprStmt, MatchExpr, VarDecl

    for stmt in body:
        if isinstance(stmt, VarDecl) and stmt.name == name:
            return stmt
        # Recurse into match arms
        if isinstance(stmt, MatchExpr):
            for arm in stmt.arms:
                result = _search_body_for_var(name, arm.body)
                if result is not None:
                    return result
        if isinstance(stmt, ExprStmt) and isinstance(stmt.expr, MatchExpr):
            for arm in stmt.expr.arms:
                result = _search_body_for_var(name, arm.body)
                if result is not None:
                    return result
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

    # Collect all matching overloads for this function name

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
    "constants",
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

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if stripped.startswith("module ") and module_line is None:
            module_line = i
            header_end = i + 1
            i += 1
            continue

        if module_line is None:
            i += 1
            continue

        # Still in the header (narrative/temporal)
        if stripped.startswith("narrative:") or stripped.startswith("temporal:"):
            header_end = i + 1
            # Handle multiline triple-quote block: skip to closing """
            rest = stripped[stripped.index(":") + 1 :].strip()
            if rest.startswith('"""'):
                inner = rest[3:]
                if '"""' not in inner:  # closing """ not on the same line
                    i += 1
                    while i < len(lines):
                        if '"""' in lines[i]:
                            header_end = i + 1
                            i += 1
                            break
                        i += 1
                    continue
            i += 1
            continue

        # Import lines: indented "ModuleName verb name, name"
        # e.g. "  System outputs console"
        if line.startswith("  ") and stripped:
            parts = stripped.split()
            if len(parts) >= 3 and parts[0][0].isupper() and parts[1] in _IMPORT_VERBS:
                last_import_line = i
                i += 1
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
        formatted = ProveFormatter()._format_import_decl(new_decl)
        # Add module-level indent (2 spaces) to each line of the formatted import
        new_line = "\n".join(f"  {line}" for line in formatted.split("\n"))

        source_lines = ds.source.splitlines()
        # Use the full span of the import (may be multi-line)
        end_line = imp.span.end_line - 1  # 0-indexed
        end_line_text = source_lines[end_line] if end_line < len(source_lines) else ""
        return lsp.TextEdit(
            range=lsp.Range(
                start=lsp.Position(line=imp_line, character=0),
                end=lsp.Position(line=end_line, character=len(end_line_text)),
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
    lsp.CodeActionOptions(
        code_action_kinds=[
            lsp.CodeActionKind.QuickFix,
            lsp.CodeActionKind.Source,
        ]
    ),
)
def code_action(params: lsp.CodeActionParams) -> list[lsp.CodeAction] | None:
    uri = params.text_document.uri
    if _is_intent_uri(uri):
        ids = _intent_state.get(uri)
        if ids is None:
            return None
        actions = _intent_code_actions(uri, ids)
        return actions if actions else None
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


# ── Inlay hints ──────────────────────────────────────────────────


def _collect_var_decls(stmts: list) -> list[VarDecl]:
    """Recursively collect VarDecl nodes from a statement/expression list."""
    result: list[VarDecl] = []
    for stmt in stmts:
        if isinstance(stmt, VarDecl):
            result.append(stmt)
        elif isinstance(stmt, MatchExpr):
            for arm in stmt.arms:
                result.extend(_collect_var_decls(arm.body))
        elif isinstance(stmt, WhileLoop):
            result.extend(_collect_var_decls(stmt.body))
    return result


@server.feature(
    lsp.TEXT_DOCUMENT_INLAY_HINT,
    lsp.InlayHintOptions(),
)
def inlay_hint(params: lsp.InlayHintParams) -> list[lsp.InlayHint] | None:
    uri = params.text_document.uri
    ds = _state.get(uri)
    if ds is None or ds.module is None or not ds.inlay_type_map:
        return None

    hints: list[lsp.InlayHint] = []
    for decl in ds.module.declarations:
        body = getattr(decl, "body", None)
        if not body:
            continue
        for vd in _collect_var_decls(body):
            if vd.type_expr is not None:
                continue
            ty = ds.inlay_type_map.get((vd.span.start_line, vd.span.start_col))
            if ty is None:
                continue
            hints.append(
                lsp.InlayHint(
                    position=lsp.Position(
                        line=vd.span.start_line - 1,
                        character=vd.span.start_col - 1 + len(vd.name),
                    ),
                    label=f" {ty}",
                    kind=lsp.InlayHintKind.Type,
                )
            )
    return hints or None


# ── Entry point ──────────────────────────────────────────────────


def main() -> None:
    """Start the Prove language server on stdio."""
    server.start_io()
