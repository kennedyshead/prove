# Async Plan — Ticket #20

## Overview

Add async/concurrency support to Prove via three new verbs: `detached`, `attached`,
and `listens`. These form a new **async verb family**, following the same syntax
patterns as the IO verb family (`inputs`/`outputs`/`streams`).

`listens` is the async loop verb. The IO verb `streams` (file/IO loop) will be built
later to mirror the `listens` pattern — not a prerequisite.

## Verb Families

| Pattern | Async | IO |
|---------|-------|----|
| Push, move on | `detached` | `outputs` |
| Pull, await | `attached` | `inputs` |
| Loop until exit | `listens` | `streams` (future) |
| — | **Pure:** transforms, validates, reads, creates, matches | |

## Syntax

```prove
// Fire and forget — spawn and move on, no result
detached log(event Event)
from
  send(event)&

// Spawn and await — caller blocks until result is ready
attached fetch(url String) String
from
  request(url)&

// Loop until exit — listen to async source, exit via Exit() arm
listens event(source EventSource) Event
from
    Exit() => _
    Data(payload) => process(payload)&
```

The `listens` verb loops until a match arm with `Exit()` terminates the loop.
The `from` block is a top-level match expression — arms are applied to each item
received from `source`. `Exit()` is the mandatory termination arm.

## The `&` Marker

The `&` suffix marks an async invocation at the **call site**, analogous to `!`
for failable calls:

| Marker | Meaning | Example |
|--------|---------|---------|
| `!` | can fail | `result = parse(input)!` |
| `&` | async invocation | `data = fetch(url)&` |

The verb (`detached`, `attached`, `listens`) declares async intent at the function
level. `&` only appears at call sites within async bodies where work is dispatched.

## Safety Model

- **Blocking IO calls** in async body → checker error (`inputs`/`outputs` are blocking)
- **Missing `&`** when calling an async function from async body → checker error
- **Await** → implicit within async body
- **Cancellation** → implicit via coroutine state flag
- **No shared mutable state** → Prove's pure verb family guarantees this

---

## C Coroutine Model

**Runtime: `ucontext_t` stackful coroutines** (POSIX, available on macOS and Linux).
No external dependencies. Windows fallback: sequential execution (no concurrency,
same semantics).

### New runtime file: `prove_coro.c` / `prove_coro.h`

```c
typedef enum {
    PROVE_CORO_CREATED,
    PROVE_CORO_RUNNING,
    PROVE_CORO_SUSPENDED,
    PROVE_CORO_DONE
} Prove_CoroState;

typedef struct Prove_Coro {
    ucontext_t  ctx;           /* coroutine context */
    ucontext_t  caller_ctx;    /* context to yield back to */
    void       *stack;         /* allocated stack */
    size_t      stack_size;
    Prove_CoroState state;
    void       *result;        /* result slot for attached */
    void       *arg;           /* argument passed on start */
    int         cancelled;     /* cancellation flag */
} Prove_Coro;

#define PROVE_CORO_STACK_DEFAULT (64 * 1024)

Prove_Coro *prove_coro_new(void (*fn)(Prove_Coro *), size_t stack_size);
void  prove_coro_start(Prove_Coro *coro, void *arg);  /* first resume */
void  prove_coro_resume(Prove_Coro *coro);             /* subsequent */
void  prove_coro_yield(Prove_Coro *coro);              /* yield to caller */
void  prove_coro_cancel(Prove_Coro *coro);             /* signal cancel */
bool  prove_coro_done(Prove_Coro *coro);
bool  prove_coro_cancelled(Prove_Coro *coro);
void  prove_coro_free(Prove_Coro *coro);
```

### C Emission per Verb

#### `detached` — fire and forget

```prove
detached log(event Event)
from
    send(event)&
```

Emits:
```c
/* arg struct */
typedef struct { Event *event; } _log_args;

/* coroutine body */
static void _log_body(Prove_Coro *_coro) {
    _log_args *_a = (_log_args *)_coro->arg;
    send_detached(_a->event);   /* & call → calls detached variant */
    /* implicit yield at end = done */
    prove_coro_yield(_coro);
}

/* public entry point — spawns coro, returns immediately */
void log(Event *event) {
    _log_args *_a = malloc(sizeof(_log_args));
    _a->event = event;
    Prove_Coro *_c = prove_coro_new(_log_body, PROVE_CORO_STACK_DEFAULT);
    prove_coro_start(_c, _a);
    /* detached: no join, coro runs independently */
}
```

#### `attached` — spawn and await

```prove
attached fetch(url String) String
from
    request(url)&
```

Emits:
```c
typedef struct { Prove_String *url; } _fetch_args;

static void _fetch_body(Prove_Coro *_coro) {
    _fetch_args *_a = (_fetch_args *)_coro->arg;
    Prove_String *_r = request(_coro, _a->url);  /* & call passes _coro */
    _coro->result = _r;
    prove_coro_yield(_coro);   /* signals done */
}

/* caller passes its own coro so attached can yield upward */
Prove_String *fetch(Prove_Coro *_caller, Prove_String *url) {
    _fetch_args *_a = malloc(sizeof(_fetch_args));
    _a->url = url;
    Prove_Coro *_c = prove_coro_new(_fetch_body, PROVE_CORO_STACK_DEFAULT);
    prove_coro_start(_c, _a);
    while (!prove_coro_done(_c)) {
        prove_coro_yield(_caller);   /* yield our turn while inner runs */
        prove_coro_resume(_c);
    }
    Prove_String *result = (Prove_String *)_c->result;
    prove_coro_free(_c);
    return result;
}
```

#### `listens` — cooperative loop

```prove
listens event(source EventSource) Event
from
    Exit() => _
    Data(payload) => process(payload)&
```

The `from` block is a **match expression** evaluated on each item pulled from `source`.
`Exit()` is the mandatory termination arm — compiler enforces its presence.

Emits:
```c
void event(Prove_Coro *_coro, EventSource *source) {
    while (1) {
        if (prove_coro_cancelled(_coro)) break;
        prove_coro_yield(_coro);              /* cooperative yield per iteration */
        if (prove_coro_cancelled(_coro)) break;

        /* item is delivered via coro->arg by the resume caller */
        Event *_item = (Event *)_coro->arg;

        /* dispatch match arms */
        if (_item->tag == EVENT_EXIT) {
            break;                            /* Exit() arm — terminate */
        } else if (_item->tag == EVENT_DATA) {
            process(_coro, _item->payload);   /* & call */
        }
    }
}
```

### `&` Call Sites in C

`result = fetch(url)&` in an async body compiles to:
```c
Prove_String *result = fetch(_coro, url);
```

The `_coro` is the implicit first parameter threaded through all async bodies.
So `&` desugars to "pass my coroutine context as first arg".

For `detached` calls (fire-and-forget `send(event)&`):
```c
send(event);   /* no _coro — detached spawn, no awaiting */
```

---

## AST Changes

### New AST node: `AsyncCallExpr`

Mirrors `FailPropExpr` (for `!`):

```python
@dataclass(frozen=True)
class AsyncCallExpr:
    """Async call: expr& — desugars to passing caller's coro context."""
    expr: Expr
    span: Span
```

Add to `Expr` union and `__all__`.

### `FunctionDef` — no changes needed

`verb` is already a plain string. `detached`/`attached`/`listens` are just new
verb values. The checker uses `verb in ASYNC_VERBS` where:

```python
ASYNC_VERBS = {"detached", "attached", "listens"}
IO_VERBS    = {"inputs", "outputs"}   # blocking — forbidden in async bodies
```

---

## Lexer Changes

Add to `TokenKind`:
```python
DETACHED  = auto()
ATTACHED  = auto()
LISTENS   = auto()
AMPERSAND = auto()   # & (postfix async marker)
```

Add to `KEYWORDS`:
```python
"detached": TokenKind.DETACHED,
"attached": TokenKind.ATTACHED,
"listens":  TokenKind.LISTENS,
```

`&` is a single-character punctuation token, lexed like `!` (BANG).

---

## Parser Changes

### Function definition

Extend verb dispatch to include `DETACHED`, `ATTACHED`, `LISTENS` alongside
`TRANSFORMS`, `INPUTS`, etc.

### `&` postfix (AsyncCallExpr)

In `_parse_postfix()`, after `!` (FailPropExpr), add:
```python
if self._match(TokenKind.AMPERSAND):
    expr = AsyncCallExpr(expr=expr, span=tok.span)
```

### `listens` body: mandatory `Exit()` arm

Parser validation: `listens` function body must be a single `MatchExpr` with at
least one arm whose pattern is `Exit()`. Emit a parse error otherwise.

---

## Checker Changes

New rules in `checker.py`:

```python
ASYNC_VERBS = {"detached", "attached", "listens"}
BLOCKING_VERBS = {"inputs", "outputs"}

def _check_function(self, fd: FunctionDef) -> None:
    ...
    if fd.verb in ASYNC_VERBS:
        self._check_async_body(fd)

def _check_async_body(self, fd: FunctionDef) -> None:
    # Walk body for:
    # 1. Bare CallExpr to async function without & → error
    # 2. CallExpr to inputs/outputs function → error (blocking)
    # 3. listens: validate Exit() arm present (also in parser)
```

`AsyncCallExpr` resolves to the return type of the inner call — same as a plain
`CallExpr` but tagged for emission.

`attached` functions get an implicit `Prove_Coro *_coro` first parameter in C
emission — invisible to user code.

---

## Emitter Changes

### `_emit_types.py` / `_emit_stmts.py`

- `detached` function: emit `_args` struct + `_body` coro function + public entry
  (no `Prove_Coro *_caller` param — fire-and-forget)
- `attached` function: emit `_args` struct + `_body` coro function + public entry
  with `Prove_Coro *_caller` param
- `listens` function: emit loop with cooperative yield + cancellation check

### `_emit_exprs.py`

Handle `AsyncCallExpr`:
```python
case AsyncCallExpr():
    # Pass _coro as first arg if callee is attached
    # Emit bare call if callee is detached
```

### `c_runtime.py`

Add `prove_coro.c` to `_CORE_FILES`. Add `prove_coro.h` to include list.

---

## Implementation Phases

### Phase 1: Lexer + Tokens
- Add `DETACHED`, `ATTACHED`, `LISTENS`, `AMPERSAND` tokens
- Add keywords to `KEYWORDS` dict
- Lex `&` as `AMPERSAND`

### Phase 2: AST + Parser
- Add `AsyncCallExpr` to `ast_nodes.py`
- Parse `detached`/`attached`/`listens` as verb in function definitions
- Parse `&` postfix as `AsyncCallExpr`
- Validate `listens` body has `Exit()` arm

### Phase 3: Checker
- Add async body validation (blocking call errors, missing `&` errors)
- Type-check `AsyncCallExpr` (same type as inner call)
- Validate `attached` return type is non-void

### Phase 4: C Runtime (`prove_coro.c`)
- Implement `ucontext_t`-based coroutine primitives
- Windows fallback: sequential execution
- Add to `_CORE_FILES` in `c_runtime.py`

### Phase 5: C Emitter
- Emit `detached` functions (fire-and-forget coro spawn)
- Emit `attached` functions (spawn + cooperative await)
- Emit `listens` functions (cooperative loop with `Exit()` termination)
- Emit `AsyncCallExpr` (pass `_coro` context or bare call)

### Phase 6: Tests + Docs
- Unit tests: checker async safety rules
- E2e test: `detached` log, `attached` fetch, `listens` event loop
- Docs: `syntax.md` (async verb family, `&` marker)

---

## Exit Criteria

- [x] `detached`, `attached`, `listens` verbs parsed
- [x] `&` marker parsed as `AsyncCallExpr`
- [x] `prove_coro.c` implements stackful coroutines via `ucontext_t`
- [x] Windows: sequential fallback compiles and runs
- [x] `detached` emits fire-and-forget coro spawn
- [x] `attached` emits spawn + cooperative await with `_coro` threading
- [x] `listens` emits cooperative loop with mandatory `Exit()` arm
- [x] Checker: blocking IO call in async body → error (E371)
- [x] Checker: missing `&` on async call in async body → error (E372/E373)
- [x] E2e tests pass (no regressions)
- [x] Docs updated: `syntax.md` (async verb family, `&` marker), `types.md` (effect types)
- [ ] `streams` (IO loop verb) deferred — mirrors `listens` when built
