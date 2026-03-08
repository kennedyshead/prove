# Async Plan — Ticket #20

## Overview

Add async/concurrency support to Prove via three new verbs: `detached`, `attached`,
and `listens`. These form a new **async verb family**, following the same syntax
patterns as the IO verb family (`inputs`/`outputs`/`streams`).

## Verb Families

| Pattern | Async | IO |
|---------|-------|----|
| Push, move on | `detached` | `outputs` |
| Pull, await | `attached` | `inputs` |
| Loop until exit | `listens` | `streams` |
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
Same pattern as `streams` in the IO family.

## The Algebraic Type

The result of `attached` is an **Algebraic** type. `listens` enforces an `Exit()` arm
automatically (like exhaustive `match`), so the result type doesn't need to define it:

```prove
// attached returns an algebraic - Exit() is enforced by listens, not the type
attached fetch(url String) String
from
  request(url)&

// listens requires Exit() arm - enforced by the verb, not the result type
listens serve(port Integer) Response
from
    Exit() => stop_server()&
    Request(req) => handle(req)&
```

Like `match`, the compiler enforces that `Exit()` is handled. User code doesn't need
to define the Exit variant in their return type — `listens` adds it implicitly.

## The `&` Marker

The `&` suffix marks an async invocation at the **call site**, analogous to `!`
for failable calls:

| Marker | Meaning | Example |
|--------|---------|---------|
| `!` | can fail | `result = parse(input)!` |
| `&` | async invocation | `data = fetch(url)&` |

The verb (`detached`, `attached`, `listens`) already declares async intent at the
function level — no marker needed on the signature. `&` only appears at call
sites within async bodies where work is dispatched asynchronously.

Calling a blocking (non-`&`) function without `&` from inside an async body
is a **compiler error**.

Forgetting `&` when calling an async function from an async body is also a
**compiler error** — this is unsafe and the compiler must block it.

## Safety Model

- **Blocking calls** → compiler error (calling non-`&` from async context)
- **Error handling** → part of the verb contract, all paths defined (like `matches`)
- **Await** → implicit within async body, automatic
- **Cancellation** → implicit via signals, no explicit handling needed in user code
- **No shared mutable state** → functional approach, pass data explicitly through call chain

## Cancellation

Cancellation is handled implicitly by the runtime via signals:

- `detached`: if the spawner dies, cancellation is signaled automatically
- `attached`: cancellation propagates up since the caller is actively waiting for the result
- `listens`: cancellation breaks the loop, handled implicitly

## Design Rationale

- `detached`, `attached`, `listens` mirror `outputs`, `inputs`, `streams` — same syntax,
  same patterns, different domain (async instead of IO)
- The `&` marker is contagion-based, just like `!` — the compiler enforces boundaries
- No shared mutable state keeps the concurrency model simple and safe
- Explicit verbs make async intent visible at every call site
- Loop exit via match arm reuses existing `match` semantics — no new control flow
- Exit handling mirrors exhaustive match — compiler enforces coverage

## Exit Criteria

- [ ] `detached`, `attached`, `listens` verbs parsed
- [ ] `&` marker parsed at call sites
- [ ] Checker enforces async safety (blocking call errors, missing `&` errors)
- [ ] Cancellation semantics implemented
- [ ] Tests pass
- [ ] Docs updated: `syntax.md` (async verb family, `&` marker), `types.md` (effect types)
