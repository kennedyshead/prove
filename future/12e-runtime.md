# 12e — C Runtime: Event Queue

**Parent:** [`12-listens-event-dispatcher.md`](12-listens-event-dispatcher.md)
**Status:** Planned
**Depends on:** 12d (emitter defines what runtime primitives are needed)
**Files:** `src/prove/runtime/prove_event.h` (new), `src/prove/runtime/prove_event.c` (new), `c_runtime.py`

## Overview

Add event queue primitives to the C runtime. The event queue is the communication channel between registered `attached` worker coroutines and the `listens` dispatcher loop. Workers push events (algebraic type variants) onto the queue; the dispatcher receives them one at a time.

## Design Principles

Per the compiler-first principle:
- The queue is **not thread-safe** — Prove's concurrency is cooperative (single-threaded coroutines), no mutexes needed
- The queue does **not** validate event types — the checker already guarantees type safety
- OOM on queue allocation is a runtime panic (legitimate runtime-only concern)

## Data Structures

### `prove_event.h`

```c
#ifndef PROVE_EVENT_H
#define PROVE_EVENT_H

#include <stdbool.h>
#include <stddef.h>
#include "prove_coro.h"

/* ── Event node (intrusive linked list) ────────────────────── */
typedef struct Prove_Event {
    struct Prove_Event *next;
    int    tag;        /* algebraic variant tag */
    void  *payload;    /* variant payload (NULL for unit variants) */
} Prove_Event;

/* ── Event queue (FIFO, single-threaded) ───────────────────── */
typedef struct {
    Prove_Event *head;
    Prove_Event *tail;
    int  count;
    bool closed;       /* true after all workers finish */
} Prove_EventQueue;

/* ── API ───────────────────────────────────────────────────── */

/* Create a new empty event queue. */
Prove_EventQueue *prove_event_queue_new(void);

/* Push an event onto the queue (called by attached workers). */
void prove_event_queue_send(Prove_EventQueue *q, int tag, void *payload);

/* Receive the next event, yielding the coro until one is available.
 * Returns NULL if the queue is closed and empty. */
Prove_Event *prove_event_queue_recv(Prove_EventQueue *q, Prove_Coro *coro);

/* Close the queue (no more events will be sent). */
void prove_event_queue_close(Prove_EventQueue *q);

/* Free the queue and all remaining events. */
void prove_event_queue_free(Prove_EventQueue *q);

#endif /* PROVE_EVENT_H */
```

## Implementation

### `prove_event.c`

#### `prove_event_queue_new`

```c
Prove_EventQueue *prove_event_queue_new(void) {
    Prove_EventQueue *q = malloc(sizeof(Prove_EventQueue));
    if (!q) prove_panic("OOM: event queue allocation");
    q->head = NULL;
    q->tail = NULL;
    q->count = 0;
    q->closed = false;
    return q;
}
```

#### `prove_event_queue_send`

```c
void prove_event_queue_send(Prove_EventQueue *q, int tag, void *payload) {
    Prove_Event *ev = malloc(sizeof(Prove_Event));
    if (!ev) prove_panic("OOM: event allocation");
    ev->next = NULL;
    ev->tag = tag;
    ev->payload = payload;
    if (q->tail) {
        q->tail->next = ev;
    } else {
        q->head = ev;
    }
    q->tail = ev;
    q->count++;
}
```

#### `prove_event_queue_recv`

This is the key function — it yields the coroutine until an event is available:

```c
Prove_Event *prove_event_queue_recv(Prove_EventQueue *q, Prove_Coro *coro) {
    while (!q->head) {
        if (q->closed) return NULL;      /* all workers done, no more events */
        if (prove_coro_cancelled(coro)) return NULL;
        prove_coro_yield(coro);          /* cooperatively wait */
    }
    /* Dequeue head */
    Prove_Event *ev = q->head;
    q->head = ev->next;
    if (!q->head) q->tail = NULL;
    q->count--;
    return ev;
}
```

#### `prove_event_queue_close`

```c
void prove_event_queue_close(Prove_EventQueue *q) {
    q->closed = true;
}
```

#### `prove_event_queue_free`

```c
void prove_event_queue_free(Prove_EventQueue *q) {
    Prove_Event *ev = q->head;
    while (ev) {
        Prove_Event *next = ev->next;
        /* Note: payload is owned by the region/GC, not freed here */
        free(ev);
        ev = next;
    }
    free(q);
}
```

## Integration with Existing Runtime

### `src/prove/c_runtime.py`

This file contains all runtime metadata. Two key data structures need updating:

**`_CORE_FILES`** — list of .h and .c files that get copied to the build directory. Add:

```python
"prove_event.h",
"prove_event.c",
```

**`_RUNTIME_FUNCTIONS`** — dict of function signatures so the emitter knows what's available. Add:

```python
"prove_event_queue_new": RuntimeFunc("prove_event_queue_new", [], "Prove_EventQueue *"),
"prove_event_queue_send": RuntimeFunc("prove_event_queue_send", ["Prove_EventQueue *", "int", "void *"], "void"),
"prove_event_queue_recv": RuntimeFunc("prove_event_queue_recv", ["Prove_EventQueue *", "Prove_Coro *"], "Prove_Event *"),
"prove_event_queue_close": RuntimeFunc("prove_event_queue_close", ["Prove_EventQueue *"], "void"),
"prove_event_queue_free": RuntimeFunc("prove_event_queue_free", ["Prove_EventQueue *"], "void"),
```

Note: Check the exact `RuntimeFunc` constructor signature by reading the existing entries in `c_runtime.py`.

### Header inclusion

The emitter needs to add `#include "prove_event.h"` when a `listens` function is present. In `c_emitter.py` around line 302, there's already a loop that detects async verbs and adds `prove_coro.h`:

```python
if not found_coro and decl.verb in ("detached", "attached", "listens"):
    self._needed_headers.add("prove_coro.h")
    found_coro = True
```

Add `prove_event.h` specifically when `listens` is found:

```python
if decl.verb == "listens":
    self._needed_headers.add("prove_event.h")
```

## How Workers Send Events

When the emitter generates code for a registered `attached` worker, the worker's return value is converted to an event and sent to the queue:

```c
// At the end of the attached worker's coro body:
prove_event_queue_send(_queue, Event_Data, payload);
```

The emitter wraps the attached function's return expression in an event send. The `tag` is the algebraic variant's tag enum value (already generated by the type emitter). The `payload` is the variant's payload pointer.

This means registered attached workers need access to the queue pointer. The emitter passes it via the coro's arg struct.

## Queue Lifecycle

1. **Created** by the `listens` public entry point before spawning the dispatcher coro
2. **Shared** with all registered worker coros via their arg struct
3. **Workers send** events as they produce results
4. **Dispatcher receives** events in its `while(1)` loop
5. **Closed** when all workers have finished (the dispatcher detects this)
6. **Freed** by the public entry point after the dispatcher coro completes

## Checklist

- [ ] Create `prove_event.h` with queue struct and API declarations
- [ ] Create `prove_event.c` with queue implementation
- [ ] Add to `_CORE_FILES` in `c_runtime.py`
- [ ] Add to `_RUNTIME_FUNCTIONS` in `c_runtime.py`
- [ ] Update header detection in `c_emitter.py` for `prove_event.h`
- [ ] Document event send pattern for attached worker coro bodies
- [ ] Update `docs/AGENTS.md` with new runtime files
