---
title: Standard Library Overview - Prove Programming Language
description: Overview of the Prove standard library — 18 modules with consistent design patterns, verb families, and channel dispatch.
keywords: Prove stdlib, standard library, design pattern, verb families, channel dispatch
---

# Standard Library

The Prove standard library is a set of 18 modules that ship with the compiler. Each module is a `.prv` file declaring types and function signatures, backed by a C implementation that the compiler links into the final binary.

---

## Design Pattern

Stdlib modules follow a consistent pattern:

1. **One cohesive domain per module** — don't mix unrelated concerns.
2. **Function name = the noun** — the thing being operated on.
3. **Verb = the action** — what you do with it.
4. **Same name + different verb = channel dispatch** — the compiler resolves which function to call based on the verb at the call site.

### Verb Families

Verbs fall into two families. **Pure verbs** have no side effects — the compiler enforces this. See [Functions & Verbs](../functions.md#intent-verbs) for the full verb reference.

| Verb | Intent | Example |
|------|--------|---------|
| `transforms` | Convert data from one form to another | `transforms trim(s String) String` |
| `validates` | Check a condition, return Boolean | `validates has(key String, table Table<Value>)` |
| `reads` | Extract or query data without changing it | `reads get(key String, table Table<Value>) Option<Value>` |
| `creates` | Construct a new value from scratch | `creates builder() StringBuilder` |
| `matches` | Algebraic dispatch (first param must be algebraic) | `matches area(s Shape) Decimal` |

**IO verbs** interact with the outside world:

| Verb | Intent | Example |
|------|--------|---------|
| `inputs` | Read from an external source | `inputs file(path String) String!` |
| `outputs` | Write to an external destination | `outputs file(path String, content String)!` |

The distinction matters: pure verbs cannot call IO functions, cannot use `!`, and are safe to memoize, inline, or reorder. IO verbs make side effects explicit in the function signature.

### Channel Dispatch

For example, `System` is organized by *channels*. The `file` channel has three verbs:

```prove
inputs file(path String) String!          // read a file
outputs file(path String, content String)! // write a file
validates file(path String)               // check if file exists
```

The caller's verb determines which function is invoked. This is channel dispatch — one name, multiple intents. See [Functions & Verbs](../functions.md#verb-dispatched-identity) for how verb-dispatched identity works.

---

## Module Summary

| Module | Status | Purpose |
|--------|--------|---------|
| **[Character](character-text.md#character)** | Complete | Character classification (`alpha`, `digit`, `space`, etc.) and string-to-char access |
| **[Text](character-text.md#text)** | Complete | String operations (`slice`, `contains`, `split`, `join`, `trim`, `replace`) and `StringBuilder` for efficient string construction |
| **[Table](table-list-store.md#table)** | Complete | Hash map `Table<Value>` with `creates new`, `reads get`, `transforms add`, `validates has` |
| **[List](table-list-store.md#list)** | Complete | Operations on `List<Value>`: length, first, last, contains, sort, reverse, range |
| **[System](io-path.md#system)** | Complete | Channels: `console`, `file`, `system`, `dir`, `process` with `validates` verbs |
| **[Parse](parse-format-pattern.md#parse)** | Complete | JSON, TOML, URL, Base64, and CSV codecs with `Value` and `Url` types |
| **[Math](math-types.md#math)** | Complete | Numeric functions: abs, min, max, floor, ceil, pow, clamp, sqrt, log |
| **[Types](math-types.md#types)** | Complete | Type validation and conversion: String ↔ Integer, String ↔ Float, Character ↔ Integer |
| **[Path](io-path.md#path)** | Complete | File path manipulation: join, parent, stem, extension, normalize |
| **[Pattern](parse-format-pattern.md#pattern)** | Complete | Regex operations: test, search, replace, split with `Match` type |
| **[Format](parse-format-pattern.md#format)** | Complete | String/number formatting (pad, hex, bin) and time/date formatting |
| **[Error](error-log.md#error)** | Complete | Result/Option utilities: ok, err, some, none, unwrap_or |
| **[Bytes](bytes-hash.md#bytes)** | Complete | Byte sequence manipulation: create, slice, hex encode/decode, index access |
| **[Hash](bytes-hash.md#hash)** | Complete | Cryptographic hashing: SHA-256, SHA-512, BLAKE3, HMAC-SHA256 |
| **[Random](time-random.md#random)** | Complete | Random value generation: integer, decimal, boolean, choice, shuffle |
| **[Time](time-random.md#time)** | Complete | Time, Date, Clock, Duration, DateTime, Weekday with calendar operations |
| **[Log](error-log.md#log)** | Complete | ANSI color constants and structured logging with `detached` verb |
| **[Network](network.md)** | Complete | TCP/UDP sockets: connect, listen, accept, send, recv with Address/Socket types |
