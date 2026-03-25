---
title: Functions & Verbs - Prove Programming Language
description: Complete reference for Prove's function declarations, intent verbs, async verbs, verb dispatch, lambdas, and iteration.
keywords: Prove functions, intent verbs, async verbs, verb dispatch, lambdas, iteration, pure functions
---

# Functions & Verbs

Every Prove function declares its purpose with a **verb**. The verb IS the declaration — the compiler verifies the implementation matches the declared intent.

---

## Quick Reference

| Verb | Family | Purpose |
|------|--------|---------|
| `transforms` | Pure | Failable data computation/conversion |
| `validates` | Pure | Boolean check (returns `Boolean`) |
| `reads` | Pure | Non-mutating data access |
| `creates` | Pure | Construct new value |
| `matches` | Pure | Algebraic dispatch |
| `inputs` | IO | Read from external world |
| `outputs` | IO | Write to external world |
| `streams` | IO | Blocking IO loop |
| `detached` | Async | Fire-and-forget coroutine |
| `attached` | Async | Awaited coroutine |
| `listens` | Async | Event dispatcher |
| `renders` | Async | UI render loop with mutable state |

---

## Key Concepts

### Intent Verbs

Functions declare their purpose through verbs. The compiler enforces that implementations match declared intent:

```prove
reads double(n Integer) Integer
  ensures result == n * 2
from
    n * 2

validates is_positive(n Integer)
from
    n > 0
```

See [Intent Verbs](verbs.md) for detailed reference.

### Async Verbs

Structured concurrency via cooperative coroutines:

```prove
detached log(msg String)
from
    console(msg)

attached fetch(url String) String
from
    request(url)&
```

See [Async Verbs](async.md) for detailed reference.

### Verb Dispatch

The same name can have multiple verbs — the compiler resolves which to call from context:

```prove
validates email(String)
creates email(String) Email
inputs email(Integer) Email!
```

See [Call Resolution](verbs.md#context-aware-call-resolution) for how this works.

### Lambdas & Iteration

No loops — use `map`, `filter`, `reduce`:

```prove
names as List<String> = map(users, |u| u.name)
active as List<User> = filter(users, |u| u.active)
total as Decimal = reduce(prices, 0, |acc, p| acc + p)
```

See [Lambdas & Iteration](lambdas.md) for detailed reference.

---

## Examples

### Pure Function

```prove
creates area(s Shape) Decimal
from
    match s
        Circle(r) => pi * r * r
        Rect(w, h) => w * h
```

### IO Function

```prove
inputs users() List<User>!
from
    query(db, "SELECT * FROM users")!
```

### Async Function

```prove
detached log(event Event)
from
    console(event.message)

attached fetch(url String) String
from
    request(url)&
```

---

## Related

- [Contracts](contracts.md) — `requires`, `ensures`, `explain`
- [Type System](types.md) — Error propagation with `!`
