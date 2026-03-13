# Stub Generation — Prose to Code Skeletons (Phase 1)

Generate function stubs and module structure from `narrative` prose. In Prove,
every module can have a `narrative:` block — free-form text describing what the
module does. Every function must declare a verb keyword (`transforms`, `validates`,
`reads`, `creates`, etc.) that names its purpose. This document describes how to
bridge the two: parse the narrative, extract which verbs and nouns it implies, and
generate function signatures with empty `from` blocks (Prove's function body keyword)
marked with `todo`.

The verb-prose mapping comes from `_nl_intent.py` — a pure Python module (no external
deps) that maps English action words like "validates", "checks", "verifies" to Prove's
`validates` verb keyword. The ML n-gram model (an existing per-project + global token
frequency model used by the LSP for code completions) predicts likely function names
and parameter types given verb context.

Phase 1 generates **signatures + empty `from` blocks** with `todo` markers.
Phase 2 ([phase2-feedback-loop.md](phase2-feedback-loop.md)) fills those bodies
using stdlib knowledge and a progressive feedback loop where newly implemented
functions become available as building blocks for future generation.

---

## Background: what exists today

### Inputs available for generation

**From the AST (already parsed):**
- `ModuleDecl.narrative` — free-form prose describing the module's purpose
- `ModuleDecl.domain` — domain tag (e.g. "Finance", "Network")
- `ModuleDecl.temporal` — ordered step names (e.g. ["connect", "authenticate", "query"])

**From `_nl_intent.py` (Phase 1 prerequisite — not yet built):**
- `implied_verbs(text)` — maps prose → set of Prove verbs
- English synonym lists via `_PROSE_STEMS`

**From the ML model (already implemented):**
- Global trigram completions: `(prev2, prev1) → ranked tokens`
- Project indexer symbols: `{name, verb, kind, module, signature, docstring}`
- Bigram frequencies: `(prev1) → next_token` with counts

**From the checker (already implemented):**
- `Checker.symbols` — full symbol table of all known types, functions, modules
- Stdlib module signatures via `stdlib_loader.py`

### What generation means in Prove

Prove's verb system is a **closed set**: `transforms`, `validates`, `reads`, `creates`,
`matches`, `inputs`, `outputs`, `streams`, `detached`, `attached`, `listens`.

Every function must declare exactly one verb. This makes generation a classification
problem over a small label space, not an open-ended text generation task.

The ML model already knows patterns like:
```
After "validates" → likely names: "credential", "input", "format", ...
After "creates"   → likely names: "session", "token", "record", ...
After name "("    → likely param names and types from project context
```

---

## What to build

### Part 1 — Noun extraction from prose

**File:** `prove-py/src/prove/_nl_intent.py` (extends Phase 1 module)

Add `extract_nouns(text)` alongside the existing `implied_verbs(text)`:

```python
# Domain-relevant noun patterns — words that likely become function/type names
_NOUN_STOPS = frozenset({
    "the", "a", "an", "this", "that", "each", "every", "all", "some",
    "is", "are", "was", "were", "be", "been", "being",
    "has", "have", "had", "do", "does", "did",
    "will", "would", "could", "should", "can", "may", "might",
    "and", "or", "but", "not", "no", "nor",
    "from", "into", "with", "for", "to", "of", "in", "on", "at", "by",
    "it", "its", "them", "their", "they",
    "module", "function", "type", "using", "against", "between",
})

def extract_nouns(text: str) -> list[str]:
    """Extract candidate noun phrases from prose (domain objects, not verbs).

    Returns lowercase words that are likely to become function names,
    type names, or parameter names. Preserves order of first occurrence.
    """
    words = re.findall(r"[a-zA-Z_][a-zA-Z0-9_]*", text)
    seen: set[str] = set()
    nouns: list[str] = []
    verb_stems = set()
    for pattern, _verb in _PROSE_STEMS:
        verb_stems.add(pattern)

    for word in words:
        low = word.lower()
        if low in _NOUN_STOPS or low in seen or len(low) < 3:
            continue
        # Skip words that match verb stems
        is_verb = False
        for pattern, _ in _PROSE_STEMS:
            if re.search(pattern, low):
                is_verb = True
                break
        if is_verb:
            continue
        seen.add(low)
        nouns.append(low)

    return nouns
```

### Part 2 — Verb-noun pairing

**File:** `prove-py/src/prove/_nl_intent.py`

Pair extracted verbs and nouns into candidate function signatures:

```python
@dataclass
class FunctionStub:
    verb: str           # e.g. "validates"
    name: str           # e.g. "credential"
    params: list[tuple[str, str]]   # [(name, type), ...]
    return_type: str    # predicted return type
    confidence: float   # 0.0–1.0 based on model support

def pair_verbs_nouns(
    verbs: set[str],
    nouns: list[str],
    model_predict: Callable[[str, str], list[str]] | None = None,
) -> list[FunctionStub]:
    """Generate verb+noun pairings ranked by ML model confidence.

    Each verb is paired with each noun. The model (if available) predicts
    likely parameter types and return types. Confidence is based on how
    strongly the model supports this combination.
    """
    stubs: list[FunctionStub] = []
    for verb in sorted(verbs):
        for noun in nouns:
            params = _predict_params(verb, noun, model_predict)
            ret = _predict_return(verb, noun, model_predict)
            conf = _score_stub(verb, noun, model_predict)
            stubs.append(FunctionStub(
                verb=verb, name=noun,
                params=params, return_type=ret,
                confidence=conf,
            ))
    return sorted(stubs, key=lambda s: -s.confidence)


def _predict_params(
    verb: str, name: str,
    predict: Callable[[str, str], list[str]] | None,
) -> list[tuple[str, str]]:
    """Predict parameter list using model context.

    Falls back to verb-based heuristics:
    - validates: (name Type) Boolean
    - transforms: (name Type) Type
    - reads: (source Source) Type
    - creates: (...) Type
    """
    if predict is not None:
        # Query: what comes after "verb name(" ?
        hits = predict(name, "(")
        if hits:
            # Parse first hit as param name, second as type
            params = []
            for i in range(0, len(hits) - 1, 2):
                params.append((hits[i], hits[i + 1]))
            if params:
                return params

    # Heuristic fallback based on verb family
    _VERB_PARAM_HINTS: dict[str, list[tuple[str, str]]] = {
        "validates": [(name, "String"), ("", "Boolean")],
        "transforms": [("value", "String")],
        "reads": [("source", "String")],
        "creates": [],
        "matches": [("value", "Value")],
        "inputs": [("path", "String")],
        "outputs": [("value", "String")],
    }
    return _VERB_PARAM_HINTS.get(verb, [("value", "String")])


def _predict_return(
    verb: str, name: str,
    predict: Callable[[str, str], list[str]] | None,
) -> str:
    """Predict return type from verb family defaults."""
    _VERB_RETURN_DEFAULTS: dict[str, str] = {
        "validates": "Boolean",
        "transforms": "String",
        "reads": "String",
        "creates": "String",
        "matches": "Boolean",
        "inputs": "String",
        "outputs": "Unit",
    }
    if predict is not None:
        hits = predict(")", name)
        if hits:
            return hits[0]
    return _VERB_RETURN_DEFAULTS.get(verb, "String")


def _score_stub(
    verb: str, name: str,
    predict: Callable[[str, str], list[str]] | None,
) -> float:
    """Score a verb+noun pairing. Higher = more confident."""
    if predict is None:
        return 0.5
    hits = predict(verb, name)
    # If the model predicts this name after this verb, high confidence
    if name in [h.lower() for h in hits]:
        return 0.9
    return 0.3
```

### Part 3 — Skeleton emitter

**File:** `prove-py/src/prove/_generate.py` (new)

Takes `FunctionStub` list + module metadata, emits `.prv` source text:

```python
"""Generate .prv skeleton source from function stubs and module metadata."""

from prove._nl_intent import FunctionStub


def generate_module(
    name: str,
    narrative: str,
    stubs: list[FunctionStub],
    domain: str | None = None,
    imports: list[str] | None = None,
    min_confidence: float = 0.3,
) -> str:
    """Generate a complete .prv module skeleton.

    Functions below min_confidence are emitted as comments.
    All from-blocks are empty (contain `todo` placeholder).
    """
    lines: list[str] = []

    # Module declaration
    lines.append(f"module {name}")
    if domain:
        lines.append(f"  domain: {domain}")
    lines.append(f'  narrative: """{narrative}"""')
    lines.append("")

    # Imports
    if imports:
        for imp in imports:
            lines.append(f"  use {imp}")
        lines.append("")

    # Function stubs
    for stub in stubs:
        if stub.confidence < min_confidence:
            lines.append(f"// Possible: {stub.verb} {stub.name}(...)")
            continue

        # Doc comment placeholder
        lines.append(f"/// TODO: document {stub.name}")

        # Signature
        params_str = ", ".join(
            f"{pname} {ptype}" for pname, ptype in stub.params
        )
        ret = f" {stub.return_type}" if stub.return_type != "Unit" else ""
        lines.append(f"{stub.verb} {stub.name}({params_str}){ret}")

        # Empty from block with todo
        lines.append("from")
        lines.append("  todo")
        lines.append("")

    return "\n".join(lines) + "\n"


def generate_stub_function(stub: FunctionStub) -> str:
    """Generate a single function stub (for incremental addition)."""
    lines: list[str] = []
    lines.append(f"/// TODO: document {stub.name}")
    params_str = ", ".join(
        f"{pname} {ptype}" for pname, ptype in stub.params
    )
    ret = f" {stub.return_type}" if stub.return_type != "Unit" else ""
    lines.append(f"{stub.verb} {stub.name}({params_str}){ret}")
    lines.append("from")
    lines.append("  todo")
    return "\n".join(lines)
```

### Part 4 — `todo` as a first-class incomplete marker

**Files:** `prove-py/src/prove/parser.py`, `prove-py/src/prove/checker.py`

The `todo` keyword in a `from` block signals an intentionally incomplete function.
This needs minimal support:

**Parser:** Recognise `todo` as a valid statement in a `from` block. Produce a
`TodoStmt` AST node.

```python
@dataclass(frozen=True)
class TodoStmt:
    message: str | None   # optional: todo "implement credential check"
    span: Span
```

**Checker:** A function containing `TodoStmt` in its body:
- Emits **I601** info: `"function '{name}' has incomplete implementation (todo)"`
- Suppresses unreachable-code and missing-return warnings for that function
- Counts toward a "completeness score" shown by `prove check --status`

**C emitter:** `todo` compiles to `prove_panic("TODO: <function_name>")` so the
binary fails clearly if an incomplete function is called at runtime.

**Linter integration:** `prove check --status` or `prove check --md` reports:
```
Module Auth: 3/5 functions complete (60%)
  - validates credential     [complete]
  - transforms password      [complete]
  - reads password_hash      [todo]
  - creates session          [todo]
  - validates session        [complete]
```

This is the key UX: the linter becomes a **progress tracker** for generated code.

### Part 5 — CLI command: `prove generate`

**File:** `prove-py/src/prove/cli.py`

```
prove generate <file.prv>   — generate stubs from narrative prose
prove generate --update      — add stubs for new narrative content
```

**Flow:**

1. Parse the `.prv` file (must have a `ModuleDecl` with `narrative`)
2. Extract verbs via `implied_verbs(narrative)`
3. Extract nouns via `extract_nouns(narrative)`
4. Pair verbs+nouns via `pair_verbs_nouns()`, using the warm ML model
5. Filter out stubs for functions that already exist in the file
6. Emit new stubs into the file (append after existing declarations)
7. Run formatter on the result

**`--update` mode:** Re-read the narrative (which may have been edited since
last generation), find new verb+noun pairs not yet covered by existing functions,
and append only the new stubs. Existing functions are never modified.

### Part 6 — LSP code action: "Generate stubs from narrative"

**File:** `prove-py/src/prove/lsp.py`

When the cursor is inside or near a `narrative:` block, offer a code action:
"Generate function stubs from narrative". This runs the same pipeline as
`prove generate` but inserts the result via LSP text edits.

---

## Files changed

| File | Change |
|---|---|
| `prove-py/src/prove/_nl_intent.py` | Add `extract_nouns()`, `FunctionStub`, `pair_verbs_nouns()`, prediction helpers |
| `prove-py/src/prove/_generate.py` | **New** — `generate_module()`, `generate_stub_function()` |
| `prove-py/src/prove/ast_nodes.py` | Add `TodoStmt` dataclass |
| `prove-py/src/prove/parser.py` | Parse `todo` in from-blocks → `TodoStmt` |
| `prove-py/src/prove/checker.py` | Handle `TodoStmt`: emit I601, suppress missing-return |
| `prove-py/src/prove/c_emitter.py` | Emit `prove_panic("TODO: ...")` for `TodoStmt` |
| `prove-py/src/prove/cli.py` | Add `prove generate` command |
| `prove-py/src/prove/lsp.py` | Code action for narrative → stubs |
| `prove-py/tests/test_nl_intent.py` | Tests for `extract_nouns`, `pair_verbs_nouns` |
| `prove-py/tests/test_generate.py` | **New** — tests for skeleton generation |

No changes to formatter, C runtime, or stdlib.

---

## Example: end-to-end flow

**Step 1 — Programmer writes narrative:**

```prove
module Auth
  domain: Security
  narrative: """
    This module validates user credentials against a stored database.
    It reads password hashes from the credentials store, transforms
    plaintext passwords into hashes using bcrypt, and creates session
    tokens for authenticated users.
  """
```

**Step 2 — `prove generate auth.prv` produces:**

```prove
module Auth
  domain: Security
  narrative: """
    This module validates user credentials against a stored database.
    It reads password hashes from the credentials store, transforms
    plaintext passwords into hashes using bcrypt, and creates session
    tokens for authenticated users.
  """

/// TODO: document credentials
validates credentials(user String, password String) Boolean
from
  todo

/// TODO: document password_hash
reads password_hash(user String) String!
from
  todo

/// TODO: document password
transforms password(plaintext String) String
from
  todo

/// TODO: document session
creates session(user String) String
from
  todo
```

**Step 3 — `prove check --status auth.prv` reports:**

```
Module Auth: 0/4 functions complete (0%)
  - validates credentials    [todo]
  - reads password_hash      [todo]
  - transforms password      [todo]
  - creates session          [todo]
```

**Step 4 — Programmer fills in logic, adds missing contracts.**

**Step 5 — Coherence checks (W501-W505) verify that the implementation
matches what the narrative promised.**

---

## Confidence and the ML model's role

The ML model doesn't need to be perfect. Its job is to **narrow the space**:

- **Verb prediction** (deterministic via `_PROSE_STEMS`): "validates" → `validates`
- **Name prediction** (ML-assisted): after `validates` the model suggests `credential`,
  `input`, `format` — the programmer picks the right one or types their own
- **Type prediction** (ML-assisted + heuristic): `validates` functions typically return
  `Boolean`; `reads` functions typically return `Type!` (failable)
- **Parameter prediction** (ML-assisted): the model knows what comes after `name(`

Low-confidence stubs (model score < 0.3) are emitted as comments, not code:
```prove
// Possible: outputs audit_log(...)
```

The programmer can uncomment and fill in, or delete. The bar is intentionally low —
generating a wrong stub that gets deleted costs nothing. Missing a stub that the
programmer has to write from scratch costs more.

---

## Relationship to cache warmup

Stub generation queries the ML model at generation time:

```
_nl_intent.implied_verbs(narrative)  →  {"validates", "reads", "transforms", "creates"}
_nl_intent.extract_nouns(narrative)  →  ["credentials", "password_hash", "password", "session"]
model.complete("validates", "credentials")  →  ["(", "user", "String", ...]
```

Without a warm cache, these model queries require a full reindex first. The
[cache-indexing.md](cache-indexing.md) plan ensures the model is ready instantly,
making `prove generate` fast enough for interactive use.

---

## What this does NOT do (deferred to Phase 2 and 3)

**Phase 2** ([phase2-feedback-loop.md](phase2-feedback-loop.md)):
- **Body generation** — filling `from` blocks with stdlib calls where verb+noun matches
- **Prose generation** — generating `explain`, `chosen`, `why_not` for known functions
- **Progressive re-generation** — filling more stubs as the programmer implements unknowns
- **Provenance tracking** — `@generated` markers distinguishing auto vs human code

**Phase 3** (future):
- **Project-level declaration** — a `prove.toml` or dedicated file describing the
  entire project across multiple modules
- **Cross-module generation** — generating imports and module relationships
- **Declaration regeneration** — updating the declaration text when code changes
- **Contract inference** — predicting `ensures`/`requires` from verb + types
- **Temporal ordering** — using `ModuleDecl.temporal` to sequence function generation

---

## Documentation & AGENTS Updates

When this work is implemented:

- **`docs/cli.md`** — Add the `prove generate [path]` subcommand: what it reads
  (`narrative:` block), what it produces (function stubs with `todo`-marked `from`
  blocks), and the flags (e.g. `--dry-run` to preview without writing).
- **`docs/syntax.md`** — Add a `todo` section: how `todo` marks incomplete `from`
  blocks, that the checker tracks it as an incompleteness diagnostic, and that the
  emitter compiles it to a clear panic.
- **`AGENTS.md`** — Add `prove generate` to the Commands section. Add a note under
  the checker: "`todo` in a `from` block emits an incompleteness warning; the emitter
  compiles it to `prove_panic(\"not implemented: <function name>\")`."
- Run `mkdocs build --strict` after editing docs pages.
