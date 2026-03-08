# `prove lsp` — Complete Flow

Step-by-step description of what happens from CLI invocation through the language server lifecycle.

---

## CLI Entry Point

**Command:** `prove lsp`

No arguments or flags.

**Source:** `cli.py` → `lsp()` function

---

## Step 1 — Start the language server

```python
from prove.lsp import main as lsp_main
lsp_main()
```

### `lsp_main()`:

```python
server.start_io()
```

- Creates a `pygls` `LanguageServer` instance named `prove-lsp` version `0.1.0`
- Uses **stdio transport** (reads JSON-RPC from stdin, writes to stdout)
- Text document sync mode: `Full` (entire document re-sent on every change)
- Blocks until the client disconnects or sends a shutdown request

---

## Server Configuration

```python
server = LanguageServer(
    "prove-lsp",
    "0.1.0",
    text_document_sync_kind=lsp.TextDocumentSyncKind.Full,
)
```

### Server capabilities

| Feature | Trigger | Description |
|---------|---------|-------------|
| Diagnostics | on open/change | Errors, warnings, info from Lexer + Parser + Checker |
| Hover | cursor position | Type info for symbols, functions, types |
| Completion | `.`, `(`, `\|` | Keywords, builtins, stdlib, local symbols, auto-import |
| Go-to-Definition | cursor position | Jump to symbol/function definition |
| Document Symbols | outline request | Module structure (functions, types, constants) |
| Signature Help | `(`, `,` | Parameter info for function calls |
| Formatting | format request | Full-document formatting via `ProveFormatter` |
| Code Actions | on diagnostic | Quick-fix auto-imports for undefined names |

---

## Step 2 — Document lifecycle

### `textDocument/didOpen`

```
lsp.py → did_open()
```

1. Extract URI and source text from params
2. Call `_analyze(uri, source)` → `DocumentState`
3. Publish diagnostics to client

### `textDocument/didChange`

```
lsp.py → did_change()
```

1. Extract URI and latest content (full sync — takes last change)
2. Call `_analyze(uri, source)` → `DocumentState`
3. Publish diagnostics to client

### `textDocument/didClose`

```
lsp.py → did_close()
```

1. Remove document state from `_state` cache

---

## Step 3 — Analysis pipeline (`_analyze`)

```
lsp.py → _analyze(uri, source) → DocumentState
```

### DocumentState

```python
@dataclass
class DocumentState:
    source: str = ""
    tokens: list[Token] = []
    module: Module | None = None
    symbols: SymbolTable | None = None
    diagnostics: list[lsp.Diagnostic] = []
    prove_diagnostics: list[Diagnostic] = []
    local_import_index: dict[str, list[ImportSuggestion]] = {}
```

### Phase 1: Lex

```python
tokens = Lexer(source, filename).lex()
```

- **On `CompileError`:** converts to LSP diagnostics, stops analysis
- **On unexpected exception:** creates internal error diagnostic, stops analysis

### Phase 2: Parse

```python
module = Parser(tokens, filename).parse()
```

- **On `CompileError`:** converts to LSP diagnostics, stops analysis
- **On unexpected exception:** creates internal error diagnostic, stops analysis

### Phase 3: Check

```python
local_modules = _resolve_local_modules(uri)
project_dir = _find_project_dir(uri)
checker = Checker(local_modules=local_modules, project_dir=project_dir)
symbols = checker.check(module)
```

#### `_resolve_local_modules(uri)`

1. Convert `file://` URI to local path
2. Find sibling `.prv` files in the same directory
3. **If ≤ 1 file:** return `None`
4. **If multiple:** call `build_module_registry(prv_files)`
5. **On any error:** return `None`

#### `_find_project_dir(uri)`

1. Convert URI to path
2. Walk up directories looking for `prove.toml` via `find_config()`
3. Return project root or `None`

#### Local import index

```python
ds.local_import_index = _build_local_import_index(local_modules)
```

Builds a name → `ImportSuggestion` mapping from sibling modules (types and functions).

### Diagnostic conversion

All Prove diagnostics are converted to LSP format via `_compile_diag()`:

```python
lsp.Diagnostic(
    range=span_to_range(d.labels[0].span),   # 1-indexed → 0-indexed
    severity=_SEVERITY_MAP[d.severity],       # ERROR/WARNING/NOTE → LSP severity
    source="prove",
    code=d.code,                              # e.g., "E200"
    message=f"[{d.code}] {d.message}",
    code_description=CodeDescription(href=d.doc_url),  # clickable link
)
```

---

## Step 4 — Feature handlers

### Hover (`textDocument/hover`)

```
lsp.py → hover()
```

1. Extract word at cursor position via `_get_word_at()`
2. Try three lookups in order:
   - **Symbol lookup:** `symbols.lookup(word)` → `"**kind** `verb name` : `Type`"`
   - **Function lookup:** `symbols.resolve_function_any(word)` → `"**function** `signature`"`
   - **Type lookup:** `symbols.resolve_type(word)` → `"**type** `Name` = `resolved`"`
3. Returns `None` if no match

### Completion (`textDocument/completion`)

```
lsp.py → completion()
```

Trigger characters: `.`, `(`, `|`

Builds completion items from multiple sources:

1. **Keywords** — all Prove keywords with documentation for annotation keywords
2. **Builtins** — `len`, `map`, `filter`, `reduce`, `to_string`, `clamp` with signatures
3. **Built-in types** — `Integer`, `String`, `Boolean`, etc. + `List`, `Result`, `Option`
4. **Stdlib + local imports** — merged index from `build_import_index()` + local modules
   - Each item includes auto-import edit (adds import line to module header)
   - Shows module name, verb, and signature in detail/documentation
5. **Symbol table names** — variables, constants, parameters from current file
6. **Function signatures** — user-defined functions (not already shown from imports)

Deduplication by `(label, sort_text)` — later items override earlier when both have detail.

### Go-to-Definition (`textDocument/definition`)

```
lsp.py → definition()
```

1. Extract word at cursor
2. Try symbol lookup → return location if `span.file != "<builtin>"`
3. Try function lookup → return location if `span.file != "<builtin>"`
4. Returns `None` for builtins (no source location)

### Document Symbols (`textDocument/documentSymbol`)

```
lsp.py → document_symbol()
```

Walks top-level declarations and converts to LSP symbols:

| AST Node | LSP Kind | Detail |
|----------|----------|--------|
| `FunctionDef` | Function | `"verb (params)"` |
| `MainDef` | Function | |
| `TypeDef` | Class | |
| `ConstantDef` | Constant | |
| `ModuleDecl` | Module | Children: types, constants, body |

### Signature Help (`textDocument/signatureHelp`)

```
lsp.py → signature_help()
```

Trigger characters: `(`, `,`

1. Walk backward from cursor to find opening `(`
2. Extract function name before the paren
3. Look backward for verb keyword (within 20 chars)
4. Count current arguments (comma count)
5. Look up function signature:
   - **If verb found:** `resolve_function(verb, name, arity)`
   - **If no verb:** `resolve_function_any(name)`
6. Return signature with parameter info

### Formatting (`textDocument/formatting`)

```
lsp.py → formatting()
```

1. Get cached document state
2. Filter diagnostics to only `I302` (unused imports) for formatting
3. Create `ProveFormatter(symbols=symbols, diagnostics=filtered)`
4. Format the module AST
5. **If unchanged:** return `None`
6. **If changed:** return single `TextEdit` replacing entire document

### Code Actions (`textDocument/codeAction`)

```
lsp.py → code_action()
```

Quick-fix code actions for auto-importing:

1. Filter diagnostics to importable errors: `E310` (undefined name), `I310` (implicitly typed), `E300` (undefined type)
2. Extract the undefined name from the diagnostic message
3. Look up in merged import index (stdlib + local modules)
4. For each suggestion: compute `TextEdit` to add/extend import line
5. Return `CodeAction` with `QuickFix` kind

#### `_build_import_edit(ds, suggestion)`

Two strategies:

**AST-based (preferred):**
1. Find the `ModuleDecl` in the parsed AST
2. Search existing imports for the same module
3. **If same module found:** extend the import line with the new name
4. **If not found:** insert new import line after the last import (or after module header)

**Text-based fallback (when AST unavailable):**
1. Scan source lines for `module` header and import region
2. Insert new import line after the last import

---

## Complete Pipeline Diagram

```
prove lsp
│
└─ server.start_io() ← blocks, handles JSON-RPC via stdio
   │
   ├─ textDocument/didOpen
   │  └─ _analyze(uri, source)
   │     ├─ Lexer.lex() → tokens
   │     ├─ Parser.parse() → Module
   │     ├─ _resolve_local_modules() → dict | None
   │     ├─ _find_project_dir() → Path | None
   │     ├─ Checker.check() → SymbolTable
   │     ├─ _build_local_import_index() → name→suggestions
   │     └─ Convert diagnostics → publish to client
   │
   ├─ textDocument/didChange
   │  └─ _analyze(uri, source) [same as above]
   │
   ├─ textDocument/didClose
   │  └─ Remove from _state cache
   │
   ├─ textDocument/hover
   │  └─ Symbol / function / type lookup → markdown
   │
   ├─ textDocument/completion
   │  └─ Keywords + builtins + types + stdlib + symbols + functions
   │     └─ Auto-import edits for stdlib/local items
   │
   ├─ textDocument/definition
   │  └─ Symbol / function lookup → Location
   │
   ├─ textDocument/documentSymbol
   │  └─ Walk declarations → DocumentSymbol tree
   │
   ├─ textDocument/signatureHelp
   │  └─ Find function at cursor → ParameterInformation
   │
   ├─ textDocument/formatting
   │  └─ ProveFormatter.format() → TextEdit (whole document)
   │
   └─ textDocument/codeAction
      └─ Auto-import quick-fixes for undefined names
```

---

## File Map

| File | Role |
|------|------|
| `cli.py` | CLI entry point (one-line `lsp_main()` call) |
| `lsp.py` | Language server: all handlers, analysis pipeline, state management |
| `lexer.py` | Source → token stream |
| `parser.py` | Token stream → Module AST |
| `checker.py` | Semantic analysis, type checking |
| `formatter.py` | AST → canonical Prove source (formatting handler) |
| `module_resolver.py` | Cross-file import registry (sibling modules) |
| `config.py` | `prove.toml` discovery (for project_dir) |
| `stdlib_loader.py` | Stdlib import index for auto-import suggestions |
| `symbols.py` | Symbol table (hover, completion, go-to-def, signature help) |
| `tokens.py` | Token kinds, keyword list (completion) |
| `errors.py` | Diagnostic types and severity mapping |
