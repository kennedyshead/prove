# 12a — AST Node & Parser Changes

**Parent:** [`12-listens-event-dispatcher.md`](12-listens-event-dispatcher.md)
**Status:** Planned
**Files:** `src/prove/ast_nodes.py`, `src/prove/parser.py`, `src/prove/formatter.py`

## Context

The `listens` verb is being reworked from a simple cooperative loop into an event dispatcher. Instead of taking an algebraic type value as a parameter, it now takes a `List<Attached>` (registered worker functions) and declares its event protocol via a new `event_type` block-level annotation.

**New syntax:**
```prove
listens handler(workers List<Attached>)
    event_type Event
from
    Exit           => handler
    Data(payload)  => fire(payload)&
```

This plan covers adding the `event_type` field to the AST and parsing it.

## AST: Add `event_type` to FunctionDef

### `src/prove/ast_nodes.py` (line 490)

The current `FunctionDef` dataclass has these fields:

```python
@dataclass(frozen=True)
class FunctionDef:
    verb: str
    name: str
    params: list[Param]
    return_type: TypeExpr | None
    can_fail: bool
    ensures: list[Expr]
    requires: list[Expr]
    explain: ExplainBlock | None
    terminates: Expr | None
    trusted: str | None
    binary: bool
    why_not: list[str]
    chosen: str | None
    near_misses: list[NearMiss]
    know: list[Expr]
    assume: list[Expr]
    believe: list[Expr]
    intent: str | None
    satisfies: list[str]
    body: list[Stmt | MatchExpr]
    doc_comment: str | None
    span: Span
```

Add a new field after `satisfies`:

```python
    satisfies: list[str]
    event_type: TypeExpr | None   # NEW — only valid on listens verb
    body: list[Stmt | MatchExpr]
```

- `TypeExpr | None` — `None` for all non-`listens` functions
- Every existing `FunctionDef(...)` constructor call in the codebase must be updated to include `event_type=None`

## Parser: Parse `event_type` annotation

### `parser.py`

The `event_type` annotation is parsed in the same block as `ensures`, `requires`, `terminates`, etc. — between the verb line and `from`.

**Syntax:**

```
event_type TypeName
```

No colon (matches `terminates` syntax). The value is a bare type name reference (a `TypeExpr`).

**Parse rules:**

1. After parsing the function signature, check for annotation keywords
2. When `event_type` is encountered:
   - Parse the next token as a `TypeExpr` (type name reference)
   - Store in `FunctionDef.event_type`
3. If `event_type` appears more than once → parser error (duplicate annotation)
4. `event_type` is accepted syntactically on any verb — the **checker** rejects it on non-`listens` verbs (separation of concerns: parser accepts, checker validates)

**Integration point:** The annotation keyword list that the parser checks needs `event_type` added. Look at how `terminates` is parsed — `event_type` follows the same pattern (keyword + expression/type).

**Important:** Search the codebase for all `FunctionDef(` constructor calls (in parser, tests, helpers) and add `event_type=None` to each. There are many — use `search_text` for `FunctionDef(` across `*.py` files. Missing any will cause `TypeError` at runtime.

## Formatter: Canonical ordering

### `formatter.py`

Add `event_type` to the canonical annotation ordering. It should appear after `satisfies` and before `explain`:

```
requires → ensures → terminates → trusted → know/assume/believe →
why_not/chosen → near_miss → satisfies → event_type → explain
```

When formatting a `listens` function, emit `event_type` on its own indented line:

```prove
listens handler(workers List<Attached>)
    event_type Event
    from
        ...
```

## Checklist

- [ ] Add `event_type: TypeExpr | None` field to `FunctionDef` in `ast_nodes.py`
- [ ] Update all `FunctionDef(...)` constructor calls to include `event_type=None` (grep for `FunctionDef(`)
- [ ] Parse `event_type` keyword in annotation block of `parser.py`
- [ ] Emit `event_type` in `formatter.py` canonical ordering
- [ ] Update `docs/AGENTS.md` with the new AST field
