# Narrative & Explain Prose Analysis

Prove functions declare a **verb** keyword (`transforms`, `validates`, `reads`, `creates`,
`matches`, `inputs`, `outputs`, etc.) that names their purpose. Modules can have a
**`narrative:`** block — free-form prose describing what the module does. Functions can have
**`explain`** blocks (step-by-step documentation of the `from` body), **`intent:`** (why the
function exists), **`chosen:`** (which approach was taken), and **`why_not:`** (rejected
alternatives). Today these prose blocks are parsed by the compiler but mostly inert — no
semantic analysis connects the prose to the code it describes.

This document describes how to parse `narrative` and `explain` blocks with NL techniques
to map prose to actual Prove verbs, then use that mapping for LSP autocomplete and
compiler lint inside those blocks. Pure Python, no external dependencies.

---

## Background: what exists today

### AST nodes (ast_nodes.py)

```python
# Module level
class ModuleDecl:
    narrative: str | None   # triple-quoted prose, e.g. "This module validates..."
    domain: str | None

# Function level — all prose annotations
class FunctionDef:
    explain:   ExplainBlock | None  # entries with optional `when` condition + prose text
    intent:    str | None           # single string ("why this function exists")
    chosen:    str | None           # single string ("why this approach")
    why_not:   list[str]            # rejected alternatives

class ExplainBlock:
    entries: list[ExplainEntry]

class ExplainEntry:
    condition: Expr | None   # None = unconditional prose line
    text:      str
```

### Current behaviour

| Block | Current use |
|---|---|
| `narrative` | `--coherence` CLI flag → `checker._check_coherence()`: word-overlap between narrative words and function names → I340 info |
| `explain` | C emitter only — drives `if/else` chains when entries have `when` conditions |
| `intent` | Checker warns W311 when set but no `ensures`/`requires` |
| `chosen` / `why_not` | Inert (parsed, stored, formatted — never analysed) |

### Coherence flag wiring (checker.py `Checker.__init__` / `check()`)

```python
self._coherence: bool = False   # set by CLI --coherence

# in check() second pass:
if self._coherence:
    self._check_coherence(module)   # → I340 today; new checks go here
```

`_check_coherence` (method on `Checker`) currently only checks function name vocab.

### LSP completion pipeline (lsp.py `completion()`)

```
completion()
  Phase 1-4: keyword / builtin / stdlib / symbol-table items
  Phase 5: ML n-gram completions prepended
  Dedup + return
```

The LSP runs `Checker` in `_analyze()` but **never sets `_coherence = True`**.
Prose blocks are therefore invisible to the checker in the editor.

---

## What to build

### Phase 1 — `_nl_intent.py` (new file)

`prove-py/src/prove/_nl_intent.py`

Pure Python, no external deps. Two public helpers consumed by checker + LSP.

#### 1a. `PROSE_TO_VERB` and `implied_verbs(text)`

```python
# Each key is a regex alternation of synonyms → Prove verb keyword
_PROSE_STEMS: list[tuple[str, str]] = [
    (r"transform|convert|comput|calculat|process|produc",  "transforms"),
    (r"validat|check|verif|ensur|guard",                   "validates"),
    (r"\bread|fetch|load|retriev|queri",                   "reads"),
    (r"creat|make|build|construct|generat",                "creates"),
    (r"match|compar|classif|select",                       "matches"),
    (r"output|write|print|send|emit|log|display",          "outputs"),
    (r"input|receiv|accept|pars|tak",                      "inputs"),
    (r"listen|watch|monitor|wait",                         "listens"),
]

def implied_verbs(text: str) -> set[str]:
    """Return Prove verb keywords implied by action words in prose text."""
    words = re.findall(r"[a-z]+", text.lower())
    result: set[str] = set()
    for word in words:
        for pattern, verb in _PROSE_STEMS:
            if re.search(pattern, word):
                result.add(verb)
                break
    return result
```

#### 1b. `body_tokens(fd)` — extract meaningful names from a function's `from` body

```python
def body_tokens(fd: FunctionDef) -> set[str]:
    """Return param names + called function names from the from-body."""
    names: set[str] = {p.name for p in fd.params}
    def _collect(node):
        if isinstance(node, CallExpr):
            if isinstance(node.func, IdentifierExpr):
                names.add(node.func.name)
            for a in node.args:
                _collect(a)
        elif isinstance(node, (BinaryExpr, UnaryExpr, FieldExpr, PipeExpr)):
            for child in vars(node).values():
                if isinstance(child, (list, tuple)):
                    for x in child: _collect(x)
                elif hasattr(child, '__dataclass_fields__'):
                    _collect(child)
    for stmt in fd.body:
        _collect(stmt)
    return names
```

#### 1c. `prose_overlaps(prose, tokens)` — simple check for W502

```python
def prose_overlaps(prose: str, tokens: set[str]) -> bool:
    """True if any word in prose matches a token (case-insensitive, stems)."""
    prose_words = {w.lower() for w in re.findall(r"[a-zA-Z_][a-zA-Z0-9_]*", prose)}
    lower_tokens = {t.lower() for t in tokens}
    # Direct overlap
    if prose_words & lower_tokens:
        return True
    # Stem overlap: prose word is a prefix of a token or vice versa (≥4 chars)
    for pw in prose_words:
        if len(pw) >= 4:
            for t in lower_tokens:
                if t.startswith(pw) or pw.startswith(t[:4]):
                    return True
    return False
```

---

### Phase 2 — Checker coherence lints

**File:** `prove-py/src/prove/_check_contracts.py`

Add three methods to the `CheckContractsMixin` class. Call them from `checker._check_coherence()` after the existing I340 block.

#### W501 — function verb not implied by narrative

```python
def _check_narrative_verb_coherence(self, mod_decl: ModuleDecl, fns: list[FunctionDef]) -> None:
    """W501: function verb not described in module narrative."""
    if mod_decl.narrative is None:
        return
    from prove._nl_intent import implied_verbs
    verbs = implied_verbs(mod_decl.narrative)
    if not verbs:
        return
    for fd in fns:
        if fd.verb not in verbs:
            self._warn(
                "W501",
                f"verb '{fd.verb}' not described in module narrative",
                fd.span,
                notes=[f"narrative implies: {', '.join(sorted(verbs))}"],
            )
```

#### W502 — explain entry doesn't match from-body

```python
def _check_explain_body_coherence(self, fd: FunctionDef) -> None:
    """W502: explain entry text has no overlap with from-body operations."""
    if fd.explain is None:
        return
    from prove._nl_intent import body_tokens, prose_overlaps
    tokens = body_tokens(fd)
    if not tokens:
        return
    for entry in fd.explain.entries:
        if entry.condition is not None:
            continue  # `when` entries are structural, skip
        if entry.text.strip() and not prose_overlaps(entry.text, tokens):
            self._warn(
                "W502",
                f"explain entry doesn't correspond to any operation in from-block",
                fd.span,
                notes=[
                    f"entry: '{entry.text.strip()}'",
                    f"body references: {', '.join(sorted(tokens))}",
                ],
            )
```

#### W503 — chosen without why_not

```python
def _check_chosen_has_why_not(self, fd: FunctionDef) -> None:
    """W503: chosen declared without any why_not alternatives."""
    if fd.chosen and not fd.why_not:
        self._warn(
            "W503",
            "chosen declared without any why_not alternatives",
            fd.span,
            notes=["Add at least one `why_not` entry to document rejected approaches."],
        )
```

#### W504 — chosen text doesn't relate to the function body

```python
def _check_chosen_body_coherence(self, fd: FunctionDef) -> None:
    """W504: chosen text has no overlap with from-body operations or params."""
    if not fd.chosen:
        return
    from prove._nl_intent import body_tokens, prose_overlaps
    tokens = body_tokens(fd)
    if tokens and not prose_overlaps(fd.chosen, tokens):
        self._warn(
            "W504",
            "chosen text doesn't correspond to any operation in from-block",
            fd.span,
            notes=[
                f"chosen: '{fd.chosen}'",
                f"body references: {', '.join(sorted(tokens))}",
            ],
        )
```

#### W505 — why_not entry mentions no known name

Each `why_not` string is a rejected alternative. It should name something real — a function,
type, or recognisable approach — not be a vague sentence with no anchors.

```python
def _check_why_not_names(self, fd: FunctionDef, known_names: set[str]) -> None:
    """W505: why_not entry mentions no function/type name from current scope."""
    for entry in fd.why_not:
        words = {w.lower() for w in re.findall(r"[a-zA-Z_][a-zA-Z0-9_]*", entry)}
        lower_known = {n.lower() for n in known_names}
        if not words & lower_known:
            self._warn(
                "W505",
                f"why_not entry mentions no known function or type",
                fd.span,
                notes=[
                    f"entry: '{entry}'",
                    "Reference a function name, type, or algorithm to anchor the rejection.",
                ],
            )
```

`known_names` is built once per module from `self.symbols` (all function names + type names)
and passed down:

```python
# in _check_coherence():
known_names = (
    set(self.symbols.all_functions().keys())
    | set(self.symbols.all_types().keys())
)
for fd in fns:
    self._check_why_not_names(fd, known_names)
```

#### Wire into `_check_coherence` (checker.py `Checker._check_coherence`)

```python
def _check_coherence(self, module: Module) -> None:
    # ... existing I340 narrative vocabulary check ...

    # NEW: collect all FunctionDefs + known names
    fns = [d for d in module.declarations if isinstance(d, FunctionDef)]
    known_names = (
        set(self.symbols.all_functions().keys())
        | set(self.symbols.all_types().keys())
    )
    if mod_decl:
        self._check_narrative_verb_coherence(mod_decl, fns)
    for fd in fns:
        self._check_explain_body_coherence(fd)
        self._check_chosen_has_why_not(fd)
        self._check_chosen_body_coherence(fd)
        self._check_why_not_names(fd, known_names)
```

#### Enable coherence in the LSP (lsp.py `_analyze`)

```python
checker = Checker(local_modules=local_modules, project_dir=project_dir)
checker._coherence = True   # always run coherence in editor (shown as hints)
symbols = checker.check(module)
```

W501–W503 use `Severity.WARNING` so they appear as warnings in the editor, not errors.

---

### Phase 3 — LSP prose context detection

**File:** `prove-py/src/prove/lsp.py`

New function before `_ml_completions`:

```python
_PROSE_BLOCK_KEYWORDS = frozenset({"intent", "chosen", "why_not"})

def _prose_context(
    source: str,
    position: lsp.Position,
    module: Module | None,
) -> tuple[str | None, FunctionDef | None]:
    """Return (context_kind, enclosing_fd) when cursor is inside a prose block.

    context_kind is one of: "narrative", "explain", "intent", "chosen", "why_not"
    Returns (None, None) when cursor is in normal code.
    """
    lines = source.splitlines()
    line_idx = position.line
    if line_idx >= len(lines):
        return None, None
    current = lines[line_idx]
    stripped = current.lstrip()

    # Check single-line prose keywords: intent/chosen/why_not
    for kw in _PROSE_BLOCK_KEYWORDS:
        if stripped.startswith(f"{kw}:") or stripped == kw:
            fd = _find_enclosing_fd(module, line_idx)
            return kw, fd

    # Check if inside narrative triple-quote block
    # Walk backward to find 'narrative: """' and forward for closing '"""'
    in_narrative = _cursor_in_triple_quote_block(lines, line_idx, "narrative:")
    if in_narrative:
        return "narrative", None

    # Check if inside an explain block (indented lines after 'explain')
    in_explain = _cursor_in_explain_block(lines, line_idx)
    if in_explain:
        fd = _find_enclosing_fd(module, line_idx)
        return "explain", fd

    return None, None


def _cursor_in_triple_quote_block(lines: list[str], line_idx: int, keyword: str) -> bool:
    """True if line_idx is between a `keyword: \"\"\"` and its closing `\"\"\"`."""
    open_line = None
    for i in range(line_idx, -1, -1):
        stripped = lines[i].lstrip()
        if stripped.startswith(keyword) and '"""' in lines[i]:
            open_line = i
            break
        if '"""' in lines[i] and i < line_idx:
            # Hit a closing triple-quote before finding the open keyword
            return False
    if open_line is None or open_line == line_idx:
        return False
    # Now check if there's a closing """ between open_line+1 and line_idx
    for i in range(open_line + 1, line_idx):
        if '"""' in lines[i]:
            return False  # already closed before cursor
    return True


def _cursor_in_explain_block(lines: list[str], line_idx: int) -> bool:
    """True if line_idx is an indented content line inside an explain block."""
    # Walk backward: find 'explain' keyword at lower indent
    current_indent = len(lines[line_idx]) - len(lines[line_idx].lstrip())
    for i in range(line_idx - 1, -1, -1):
        line = lines[i]
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip())
        if indent < current_indent and line.lstrip().startswith("explain"):
            return True
        if indent < current_indent:
            break  # Hit something else at lower indent — not in explain
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
```

---

### Phase 4 — LSP prose-mode completions

**File:** `prove-py/src/prove/lsp.py`

New function `_prose_completions`, and wire it in `completion()`.

```python
# English synonyms shown as completions inside narrative/explain (maps to Prove verb)
_VERB_PROSE_HINTS: dict[str, list[str]] = {
    "transforms": ["transforms", "converts", "computes", "calculates", "processes"],
    "validates":  ["validates", "checks", "verifies", "ensures", "guards"],
    "reads":      ["reads", "fetches", "loads", "retrieves", "queries"],
    "creates":    ["creates", "builds", "constructs", "generates", "makes"],
    "matches":    ["matches", "compares", "classifies", "selects"],
    "outputs":    ["outputs", "writes", "prints", "sends", "emits", "logs"],
    "inputs":     ["inputs", "receives", "accepts", "parses"],
    "listens":    ["listens", "monitors", "watches", "waits"],
}
_ALL_PROSE_VERB_WORDS: list[str] = [w for words in _VERB_PROSE_HINTS.values() for w in words]


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
        # Prose verb words (all, ranked by narrative content of module if available)
        existing_narrative = ""
        if module:
            for decl in module.declarations:
                if isinstance(decl, ModuleDecl) and decl.narrative:
                    existing_narrative = decl.narrative
                    break
        from prove._nl_intent import implied_verbs
        already_implied = implied_verbs(existing_narrative)
        for word in _ALL_PROSE_VERB_WORDS:
            # Determine which Prove verb this word belongs to
            prove_verb = next(
                (v for v, words in _VERB_PROSE_HINTS.items() if word in words), ""
            )
            sort = "0" if prove_verb in already_implied else "1"
            items.append(_text(word, f"→ {prove_verb}", sort))
        # Function names from module (lowercase, for natural prose)
        if module:
            for decl in module.declarations:
                if isinstance(decl, FunctionDef):
                    items.append(_text(decl.name.replace("_", " "), "function", "2"))

    elif context_kind == "explain":
        if fd is not None:
            from prove._nl_intent import body_tokens
            # Param names and called function names from the body
            for tok in sorted(body_tokens(fd)):
                items.append(_text(tok, "body", "0"))
            # Prose synonyms for the function's own verb
            for word in _VERB_PROSE_HINTS.get(fd.verb, []):
                items.append(_text(word, fd.verb, "1"))

    elif context_kind == "intent":
        if fd is not None:
            for p in fd.params:
                items.append(_text(p.name, "param", "0"))
            if fd.return_type is not None:
                items.append(_text(_ast_type_str(fd.return_type), "return type", "0"))
            starters = {
                "transforms": [f"Transforms {p.name} into" for p in fd.params[:1]],
                "validates":  [f"Validates {p.name}" for p in fd.params[:1]],
                "reads":      [f"Reads {p.name} from" for p in fd.params[:1]],
                "creates":    ["Creates a new"],
                "outputs":    ["Outputs"],
            }
            for phrase in starters.get(fd.verb, []):
                items.append(_text(phrase, "phrase", "1"))

    elif context_kind == "chosen":
        if fd is not None:
            # Body tokens: the actual operations used — this is the chosen approach
            from prove._nl_intent import body_tokens
            for tok in sorted(body_tokens(fd)):
                items.append(_text(tok, "body", "0"))
            # Prose synonyms for the function's verb (describe the approach in English)
            for word in _VERB_PROSE_HINTS.get(fd.verb, []):
                items.append(_text(word, fd.verb, "0"))
            # Phrase starters: "X because", "X for", "X over Y"
            starters = {
                "transforms": ["linear scan because", "recursive because", "iterative because"],
                "validates":  ["early-exit because", "regex because", "range check because"],
                "reads":      ["lazy load because", "cached read because"],
                "creates":    ["builder pattern because", "factory because"],
                "matches":    ["pattern match because", "lookup table because"],
            }
            for phrase in starters.get(fd.verb, []):
                items.append(_text(phrase, "approach", "1"))

    elif context_kind == "why_not":
        if fd is not None:
            # Suggest function names from module — the most useful anchors
            if module:
                for decl in module.declarations:
                    if isinstance(decl, FunctionDef) and decl.name != fd.name:
                        items.append(_text(decl.name, "function", "0"))
            # Suggest type names from module
            if module:
                for decl in module.declarations:
                    if isinstance(decl, (ModuleDecl,)):
                        for td in getattr(decl, "types", []):
                            items.append(_text(td.name, "type", "0"))
            # Common algorithmic alternative phrases
            alt_phrases = [
                "hash map because", "binary search because", "linear scan because",
                "recursive approach because", "lookup table because",
                "regex because", "manual parse because",
                "eager evaluation because", "lazy evaluation because",
            ]
            for phrase in alt_phrases:
                items.append(_text(phrase, "alternative", "1"))

    return items
```

#### Wire into `completion()` — insert before Phase 5 (ML n-gram section)

```python
    # Phase 5a — prose-mode completions (suppress ML n-gram items in prose context)
    if ds is not None and ds.module is not None:
        prose_kind, prose_fd = _prose_context(ds.source, params.position, ds.module)
        if prose_kind is not None:
            prose_items = _prose_completions(prose_kind, prose_fd, ds.module)
            # In prose context: prepend prose items, skip ML n-gram phase
            items = prose_items + items
            return lsp.CompletionList(is_incomplete=False, items=_dedup(items))

    # Phase 5 — ML completion suggestions (existing)
    if _project_indexer is not None and ds is not None:
        ml_items = _ml_completions(ds.source, params.position, ds=ds)
        items = ml_items + items
```

Extract the existing dedup loop into `_dedup(items)` for reuse.

---

## Files changed

| File | Change |
|---|---|
| `prove-py/src/prove/_nl_intent.py` | **New** — `implied_verbs()`, `body_tokens()`, `prose_overlaps()` |
| `prove-py/src/prove/_check_contracts.py` | Add `_check_narrative_verb_coherence`, `_check_explain_body_coherence`, `_check_chosen_has_why_not`, `_check_chosen_body_coherence`, `_check_why_not_names`; call from `_check_coherence` |
| `prove-py/src/prove/checker.py` | In `_check_coherence()`: call three new methods |
| `prove-py/src/prove/lsp.py` | Enable `_coherence=True` in `_analyze()`; add `_prose_context()`, `_find_enclosing_fd()`, `_cursor_in_*` helpers, `_prose_completions()`; wire Phase 5a in `completion()` |
| `prove-py/tests/test_checker_contracts.py` | Unit tests for W501, W502, W503 |
| `prove-py/tests/test_nl_intent.py` | **New** — unit tests for `implied_verbs`, `body_tokens`, `prose_overlaps` |

No changes to parser, AST, lexer, emitter, C runtime, or formatter.

---

## Test cases to add

```python
# W501 — verb not in narrative
source = '''
module Calc
  narrative: """Reads numbers from input."""
transforms add(a Integer, b Integer) Integer
from a + b
'''
check_warns(source, "W501")  # "transforms" not implied by "reads"

# W502 — explain entry stale
source = '''
transforms add(a Integer, b Integer) Integer
  explain
    subtracts b from a
from a + b
'''
check_warns(source, "W502")  # "subtracts" doesn't match body tokens {a, b}

# W503 — chosen without why_not
source = '''
transforms sort(items List<Integer>) List<Integer>
  chosen: "merge sort for stability"
from items
'''
check_warns(source, "W503")

# W504 — chosen text doesn't match body
source = '''
transforms add(a Integer, b Integer) Integer
  chosen: "subtraction for speed"
  why_not: "addition is slower"
from a + b
'''
check_warns(source, "W504")  # "subtraction" doesn't match body tokens {a, b}

# W505 — why_not entry vague (no known names)
source = '''
transforms sort(items List<Integer>) List<Integer>
  chosen: "merge sort"
  why_not: "it was too slow"   # no function/type name anchoring the rejection
from items
'''
check_warns(source, "W505")

# No warnings — well-formed counterfactual block
source = '''
transforms sort(items List<Integer>) List<Integer>
  chosen: "merge sort for stable ordering"
  why_not: "quick_sort because unstable"
from items
'''
check_ok(source)   # quick_sort is a known name in scope
```

---

## What this enables

- `narrative: """This module validates user passwords..."""` → LSP suggests "validates",
  "checks", "verifies" inside the block; later ranks `validates` first when declaring functions
- Writing an `explain` entry → LSP suggests param names and called-function names
  so prose stays accurate to the implementation
- `prove check --coherence` → W501 flags a `transforms` function in a module whose
  narrative only talks about reading; W502 flags an explain entry that no longer matches
  what the from-block does; W503 flags undocumented design choices
- LSP always runs coherence (as warnings), CLI requires `--coherence` to surface them

---

## Documentation & AGENTS Updates

When this work is implemented:

- **`docs/contracts.md`** — Add a "Prose Coherence" section documenting W501–W505:
  what each warning catches, how to resolve it, and how to enable `--coherence` on the
  CLI. Include an example showing a module narrative, a mismatched function verb, and
  the W501 output.
- **`docs/cli.md`** — Add `--coherence` flag to the `prove check` command reference.
- **`AGENTS.md`** — Add `_nl_intent.py` to the key files list: "Pure Python module;
  `implied_verbs(text)` extracts Prove verb set from English prose; shared by the checker
  (`--coherence`) and LSP (prose completions)." Note W501–W505 in the checker mixin list.
- Run `mkdocs build --strict` after editing docs pages.
