---
title: Async Verbs - Prove Programming Language
description: Complete reference for Prove's async verbs — detached, attached, listens, and streams.
keywords: Prove async, detached, attached, listens, streams, structured concurrency
---

# Async Verbs

Prove provides structured concurrency via cooperative coroutines. Async verbs form a third family alongside pure and IO verbs.

| Verb | Purpose | Compiler enforces |
|------|---------|-------------------|
| `detached` | Spawn and move on — fire-and-forget | No return type. Body runs concurrently; caller does not wait |
| `attached` | Spawn and await — caller blocks until result is ready | Must declare a return type. May call blocking IO (runs in its own coroutine stack) |
| `listens` | Cooperative loop — processes items until `Exit` | `from` block must be a single implicit match with an `Exit` arm. No return type |
| `renders` | Event-driven UI loop — like `listens` with mutable state | `event_type` + `state_init` annotations. `List<Attached>` first param. Match with `Exit` arm |

**Key rules:**
- `listens`/`renders` bodies must not call blocking `inputs`/`outputs` functions directly — they run cooperatively and blocking would stall the yield cycle
- `listens`/`renders` arms can call `attached` functions via `&` to perform IO safely in a child coroutine
- `detached` and `attached` may call blocking IO freely since they have their own coroutine stacks
- Concurrency is cooperative — no threads, no data races
- Runtime backed by `prove_coro` stackful coroutines (`ucontext_t` on POSIX, sequential fallback on Windows)

## The `&` Marker

`&` marks an async call at the call site. It mirrors `!` for failable calls:

| Marker | Meaning | Example |
|--------|---------|---------|
| `!` | can fail — propagate error | `result = parse(input)!` |
| `&` | async invocation — dispatch to coroutine | `data = fetch(url)&` |

The verb (`detached`, `attached`, `listens`) declares intent at the function level. `&` only appears at call sites inside async bodies where work is dispatched to another async function.

---

## `detached` — Fire and Forget

Spawns a coroutine and returns immediately. The caller does not wait for completion. Cannot declare a return type ([E374](diagnostics.md#e374-detached-or-listens-declared-with-a-return-type)). May call blocking IO freely since it runs independently.

```prove

/// Log an event — fire and forget, caller moves on immediately.
detached log(message String)
from
    console(event.message)
```

---

## `attached` — Spawn and Await

Spawns a coroutine and blocks the caller until the result is ready. Must declare a return type ([E370](diagnostics.md#e370-unknown-variant-attached-without-return-type)). May call blocking IO (`inputs`/`outputs`) since it runs in its own coroutine stack. When an IO-bearing `attached` function is called via `&`, it must be from a `listens` or another `attached` body ([E398](diagnostics.md#e398-io-bearing-attached-called-outside-async-context)).

```prove
/// Read a file — attached does the IO in its own coroutine.
attached load(path String) String
from
    file(path)!

/// Fetch and parse data — caller waits for the result.
attached fetch(url String) String
from
    load(url)&
```

---

## `listens` — Event Dispatcher

The `listens` verb declares an event dispatcher that receives typed events from registered `attached` worker coroutines and dispatches them to match arms.

**Signature pattern:**

```prove
listens name(workers List<Attached>)
    event_type AlgebraicType
from
    VariantA        => ...
    VariantB(data)  => ...
    Exit            => Unit
```

**Key rules:**

- First parameter must be `List<Attached>` — the registered worker functions
- `event_type` annotation declares the algebraic type for dispatch (required)
- Each registered attached function's return type must be a variant of the `event_type`
- Match arms exhaust the `event_type` variants
- One arm must match `Exit` (terminates the dispatcher)
- Cannot declare a return type ([E374](diagnostics.md#e374-detached-or-listens-declared-with-a-return-type))
- Cannot call blocking IO directly ([E371](diagnostics.md#e371-non-exhaustive-match-blocking-io-in-async-body)) — use `&` in match arms
- Attached functions in the worker list can have arguments: `[worker(arg)]`

The `from` block uses implicit match — bare arms dispatch on events received from the internal event queue. Workers are spawned as coroutines and send events back to the dispatcher. When the `Exit` variant is matched, the loop terminates.

### Full Example — Event Processor

```prove
module EventProcessor
  narrative: """Process events using all three async verbs."""
  System outputs console
  Log detached debug

  type Event is Data(payload Integer)
    | Exit

/// Fire and forget — log without blocking.
detached fire(msg String)
from
    console(msg)

/// Produce data events for the dispatcher.
attached double(x Integer) Data<Integer>
from
    Data(x * 2)

/// Event dispatcher — receives events from workers.
listens handler(workers List<Attached>)
    event_type Event
from
    Data(payload) =>
        debug(f"got: {string(payload)}")&
        Exit()
    Exit => Unit

main()
from
    fire("hello from detached")&
    handler([double(2)])&
```

---

## Streams — Blocking IO Loop

The `streams` verb declares a **blocking loop** over an IO context. It runs until an `Exit` arm is matched, an error propagates via `!`, or the IO source is exhausted (e.g. stdin EOF). It is the synchronous counterpart to `listens` in the async family.

| Pattern | IO | Async |
|---------|-----|-------|
| Push, move on | `outputs` | `detached` |
| Pull, await | `inputs` | `attached` |
| Loop until exit | `streams` (blocking, parameter-based) | `listens` (event dispatcher, queue-based) |

**How it works:**

The parameter carries the **loop context** — a value that holds whatever the loop needs each iteration (a file handle, a socket, a prompt string). The match arms execute IO using the context on every iteration. The `Exit` arm terminates the loop; all other arms loop back.

```prove
streams read_and_write(ctx Context)
from
    Exit     => ctx                   // terminates loop
    Active(…) =>                      // IO arm — runs each iteration
        data = read_from(ctx.source)  // blocking read using context
        write_to(ctx.dest, data)      // blocking write
```

**Key rules:**

- The `from` block must be a single implicit match with an `Exit` arm
- The match subject is the first parameter type
- `streams` is a blocking IO verb — it cannot be called from `listens` bodies
- `streams` bodies may use `&` to fire-and-forget `detached` calls (e.g. logging)
- On EOF from an `inputs` read, the loop exits automatically

### REPL Example — Read stdin line by line

```prove
System outputs console inputs console

type Session is Active(prompt String)
  | Exit

/// Echo stdin lines with a prompt. Exits on EOF.
streams repl(session Session)
from
    Exit           => session
    Active(prompt) =>
        console(prompt)               // write: print prompt
        line as String = console()    // read: next stdin chunk
        console(f"< {line}")          // write: echo it

main()
from
    repl(Active("> "))
```

Each iteration the `Active(prompt)` arm performs a blocking `console()` read. When stdin is exhausted the loop exits cleanly.

### Network Server Example — Accept connections in a loop

```prove
// conn is the loop context; Accept(listener) arm calls accept() each iteration
streams serve(conn Connection)!
from
    Exit              => conn
    Accept(listener)  =>
        client as Socket = accept(listener)!
        data as ByteArray = message(client, 1024)!
        message(client, data)!
        socket(client)
```

---

## Safety Rules

| Code | Trigger | Severity |
|------|---------|----------|
| [E370](diagnostics.md#e370-unknown-variant-attached-without-return-type) | `attached` declared without a return type | Error |
| [E371](diagnostics.md#e371-non-exhaustive-match-blocking-io-in-async-body) | Blocking `inputs`/`outputs`/`streams` call in `listens` body | Error |
| [E372](diagnostics.md#e372-unknown-variant-for-generic-type-async-call-without) | `attached` or `listens` called without `&` | Error |
| [E374](diagnostics.md#e374-detached-or-listens-declared-with-a-return-type) | `detached` or `listens` declared with a return type | Error |
| [E398](diagnostics.md#e398-io-bearing-attached-called-outside-async-context) | IO-bearing `attached` called outside `listens`/`attached` body | Error |
| E401 | `event_type` must reference an algebraic type | Error |
| E402 | `listens` first parameter must be `List<Attached>` | Error |
| E403 | Registered function is not an `attached` verb | Error |
| E404 | Attached return type doesn't match event variant | Error |
| E405 | `event_type` on non-`listens` verb | Error |
| E406 | `listens` missing `event_type` annotation | Error |
| [E151](diagnostics.md#e151-listens-body-missing-exit-arm) | `listens` body missing an `Exit` arm | Error |
| [I375](diagnostics.md#i375-on-a-non-async-callee) | `&` on a non-async callee | Info |
| [I377](diagnostics.md#i377-attached-call-runs-synchronously-outside-listens) | `attached&` outside `listens` — runs synchronously | Info |
| [I378](diagnostics.md#i378-detached-function-called-without) | `detached` called without `&` | Info |
| [I601](diagnostics.md#i601-incomplete-implementation-todo) | Function body contains `todo` | Info |
