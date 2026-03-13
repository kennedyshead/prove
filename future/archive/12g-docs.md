# 12g — Documentation Updates

**Parent:** [`12-listens-event-dispatcher.md`](12-listens-event-dispatcher.md)
**Status:** Planned
**Depends on:** 12c (checker rules define the documented behavior)
**Files:** `docs/functions.md`, `docs/contracts.md`, `docs/syntax.md`, `docs/diagnostics.md`, `docs/AGENTS.md` (new), `CLAUDE.md`, `mkdocs.yml`

## Context

The reworked `listens` verb changes the entire async event pattern. The old design had `listens` taking an algebraic type value as a parameter. The new design has `listens` as an event dispatcher with:
- `List<Attached>` first parameter (registered worker functions)
- `event_type` block-level annotation (the algebraic message protocol)
- Runtime event queue for worker→dispatcher communication
- New builtin type `Attached`
- New error codes E399–E404

All user-facing and contributor-facing docs must be updated to reflect this.

## Overview

All user-facing documentation must reflect the new `listens` event dispatcher design. This includes the language reference, diagnostics, and agent/contributor docs.

## `docs/functions.md` — Async Verbs Section

### Rewrite `listens` subsection (lines 133–201)

The current content at `docs/functions.md` lines 133–201 describes the old `listens` pattern with `listens dispatcher(source Command)`. Replace entirely with the new event dispatcher model:

**Key changes:**

1. **Description** — "The `listens` verb declares an event dispatcher that receives typed events from registered `attached` worker coroutines and dispatches them to match arms."

2. **Signature pattern:**
```prove
listens name(workers List<Attached>)
    event_type AlgebraicType
from
    VariantA        => ...
    VariantB(data)  => ...
    Exit            => name
```

3. **Key rules — updated:**
   - First parameter must be `List<Attached>` — the registered worker functions
   - `event_type` annotation declares the algebraic type for dispatch (required)
   - Each registered attached function's return type must be a variant of the `event_type`
   - Match arms exhaust the `event_type` variants
   - One arm must match `Exit` (terminates the dispatcher)
   - Cannot declare a return type (E374)
   - Cannot call blocking IO directly (E371) — use `&` in match arms

4. **Full example — event processor:**
```prove
module EventProcessor
  narrative: """Process events using all three async verbs."""
  System outputs console

  type Event is Data(payload String)
    | Exit

/// Fire and forget — log without blocking.
detached fire(msg String)
from
    console(msg)

/// Produce data events for the dispatcher.
attached producer() Event
from
    Data("hello from worker")

/// Event dispatcher — receives events from workers.
listens handler(workers List<Attached>)
    event_type Event
from
    Exit           => handler
    Data(payload)  => fire(payload)&

main() Unit
from
    handler([producer])&
```

5. **Safety rules table** — add E399–E404:

| Code | Trigger | Severity |
|------|---------|----------|
| E399 | `event_type` on non-`listens` verb | Error |
| E400 | `listens` missing `event_type` | Error |
| E401 | `event_type` references non-algebraic type | Error |
| E402 | `listens` first param not `List<Attached>` | Error |
| E403 | Registered function not `attached` verb | Error |
| E404 | Attached return type doesn't match event variant | Error |

Keep existing E370, E371, E372, E374, E398, E151, I375, I376, I377, I378.

### Update streams comparison table (line ~209–213)

Update the pattern table to clarify the distinction:

| Pattern | IO | Async |
|---------|-----|-------|
| Push, move on | `outputs` | `detached` |
| Pull, await | `inputs` | `attached` |
| Loop until exit | `streams` (blocking, parameter-based) | `listens` (event dispatcher, queue-based) |

## `docs/contracts.md` — Annotation Ordering

### Update canonical ordering (lines 379–389)

The current ordering at `docs/contracts.md` lines 379–389 lists 9 annotations. Add `event_type` as number 9 (shifting `explain` to 10):

```
1. requires
2. ensures
3. terminates
4. trusted
5. know / assume / believe
6. why_not / chosen
7. near_miss
8. satisfies
9. event_type          ← NEW
10. explain
```

## `docs/syntax.md` — Keyword Exclusivity Table

### Add `event_type` keyword (lines 186–214)

The keyword exclusivity table at `docs/syntax.md` lists all keywords. Add `event_type`:

| Keyword | What it does |
|---------|-------------|
| `event_type` | Declares the algebraic type for a `listens` dispatcher. See [Functions & Verbs](functions.md#async-verbs) |

### Add `Attached` to type documentation

In the types section or in a reference to `types.md`, mention `Attached` as a builtin type:

> `Attached` — a reference to an `attached` verb function. Used in `List<Attached>` as the worker parameter for `listens` dispatchers.

## `docs/diagnostics.md` — New Error Codes

Add entries for E399–E404 following the existing format:

### E399 — `event_type` on non-listens verb
### E400 — `listens` missing `event_type` annotation
### E401 — `event_type` must reference an algebraic type
### E402 — `listens` first parameter must be `List<Attached>`
### E403 — Registered function is not an `attached` verb
### E404 — Attached return type doesn't match event variant

Each entry should include:
- Error message
- Example code that triggers it
- Explanation of why it's an error
- How to fix it

## `docs/AGENTS.md` — Agent/Contributor Reference (new file)

Create `docs/AGENTS.md` as a contributor-facing reference for AI agents and human contributors working on the Prove compiler. This should document:

1. **Listens event dispatcher architecture** — full picture of how workers → event queue → dispatcher → match arms works
2. **New AST field** — `FunctionDef.event_type: TypeExpr | None` in `src/prove/ast_nodes.py`
3. **New builtin type** — `Attached` in `src/prove/types.py`, registered in `checker.py`
4. **New error codes** — E399–E404 with triggers and examples
5. **New runtime files** — `src/prove/runtime/prove_event.h`, `prove_event.c`
6. **New C type** — `Prove_CoroFn` typedef in `prove_coro.h`
7. **Test file locations** — `tests/test_event_runtime_c.py` for queue tests
8. **Migration notes** — what changed from the old listens parameter-based model

This file is the central reference that other sub-plans reference when they say "update AGENTS.md." Every sub-plan (12a–12f) has an AGENTS.md checklist item — the idea is that as each sub-plan is implemented, its section in AGENTS.md gets written/updated.

## `CLAUDE.md` — Workspace Instructions

Update the keyword exclusivity reference and the async verbs section to mention `event_type` and `Attached`.

## `mkdocs.yml`

If `AGENTS.md` is a new page in the docs site, add it to the nav configuration. If it's a contributor-only file not published to the site, place it at `docs/AGENTS.md` but omit from nav.

## Checklist

- [ ] Rewrite `listens` subsection in `docs/functions.md`
- [ ] Update streams comparison table in `docs/functions.md`
- [ ] Add `event_type` to annotation ordering in `docs/contracts.md`
- [ ] Add `event_type` and `Attached` to `docs/syntax.md`
- [ ] Add E399–E404 to `docs/diagnostics.md`
- [ ] Create `docs/AGENTS.md` with architecture reference
- [ ] Update `CLAUDE.md` with new keywords and types
- [ ] Run `mkdocs build --strict` to verify no broken links
