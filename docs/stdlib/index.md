---
title: Standard Library Overview - Prove Programming Language
description: Overview of the Prove standard library — 21 modules with consistent design patterns, verb families, and channel dispatch.
keywords: Prove stdlib, standard library, design pattern, verb families, channel dispatch
---

# Standard Library

The Prove standard library is a set of 21 modules (plus aliases) that ship with the compiler. Each module is a `.prv` file declaring types and function signatures, backed by a C implementation that the compiler links into the final binary.

---

## Core Concepts

### Verb Families

Verbs define what a function does. The compiler enforces their guarantees:

| Family | Verbs | Guarantees |
|--------|-------|------------|
| **Pure** | `transforms`, `validates`, `reads`, `creates`, `matches` | No IO, no side effects. Safe to memoize, parallelize |
| **IO** | `inputs`, `outputs`, `streams` | Reads/writes to external world |
| **Async** | `detached`, `attached`, `listens`, `renders` | Concurrent execution via coroutines |

See [Functions & Verbs](../verbs.md) for the full reference.

### Channel Dispatch

Many modules organize functions by **channel** — the same name with different verbs:

```prove
# Three operations on "file", resolved by verb at call site
inputs file(path String) String!      // read file
outputs file(path String, content String)!  // write file
validates file(path String)           // check if exists
```

The caller's context determines which function is invoked. This is **verb-dispatched identity** — see [Functions & Verbs](../verbs.md).

### Always-Available Types

These types need no import:

- **Primitives:** `Integer`, `Decimal`, `Float`, `Boolean`, `String`, `Character`, `Byte`, `Unit`
- **Containers:** `List<Value>`, `Option<Value>`, `Result<Value, Error>`, `Table<Value>`
- **Special:** `Value`, `Error`, `Source`

### Builtin Functions

These functions are always available without import — they are compiler builtins, not part of any stdlib module:

- **Iteration:** `map`, `filter`, `reduce`, `each` — work on any iterable (`List`, `Array`)
- **Parallel:** `par_map`, `par_filter`, `par_reduce`, `par_each` — parallel variants (pure functions only)
- **Utility:** `len`, `clamp`

See [Lambdas & Iteration](../lambdas.md#builtin-higher-order-functions) for the full reference.

---

## Module Summary

| Module | Status | Purpose |
|--------|--------|---------|
| **[Character](character-text.md#character)** | Complete | Character classification (`alpha`, `digit`, `space`, etc.) and string-to-char access |
| **[Text](character-text.md#text)** | Complete | String operations (`slice`, `contains`, `split`, `join`, `trim`, `replace`) and `StringBuilder` for efficient string construction |
| **[Table](table-list-store.md#table)** | Complete | Hash map `Table<Value>` with `creates new`, `reads get`, `transforms add`, `validates has` |
| **[List](table-list-store.md#list)** | Complete | Operations on `List<Value>`: length, first, last, contains, sort, reverse, range |
| **[Array](table-list-store.md#array)** | Complete | Fixed-size contiguous arrays `Array<T>` with typed elements; supports copy-on-write and `:[Mutable]` in-place variants |
| **[System](io-path.md#system)** | Complete | Channels: `console`, `file`, `system`, `dir`, `process` with `validates` verbs |
| **[Parse](parse-format-pattern.md#parse)** | Complete | JSON, TOML, URL, Base64, CSV codecs with `Value`/`Url` types, and generic tokenization with `Token`/`Rule` types |
| **[Math](math-types.md#math)** | Complete | Numeric functions: abs, min, max, floor, ceil, pow, clamp, sqrt, log |
| **[Types](math-types.md#types)** | Complete | Type validation and conversion: String ↔ Integer, String ↔ Float, String ↔ Decimal, Character ↔ Integer; Result/Option validators and unwrap |
| **[Path](io-path.md#path)** | Complete | File path manipulation: join, parent, stem, extension, normalize |
| **[Pattern](parse-format-pattern.md#pattern)** | Complete | Regex operations: test, search, replace, split with `Match` type |
| **[Format](parse-format-pattern.md#format)** | Complete | String/number formatting (pad, hex, bin) and time/date formatting |
| **[Bytes](bytes-hash.md#bytes)** | Complete | Byte sequence manipulation: create, slice, hex encode/decode, index access |
| **[Hash](bytes-hash.md#hash)** | Complete | Cryptographic hashing: SHA-256, SHA-512, BLAKE3, HMAC-SHA256 |
| **[Random](time-random.md#random)** | Complete | Random value generation: integer, decimal, boolean, choice, shuffle |
| **[Time](time-random.md#time)** | Complete | Time, Date, Clock, Duration, DateTime, Weekday with calendar operations |
| **[Log](log.md)** | Complete | ANSI color constants and structured logging with `detached` verb |
| **[Network](network.md)** | Complete | TCP sockets: `socket`, `server`, `accept`, `message` channels with `Socket` type; pairs with `streams` for accept loops |
| **[Language](language.md)** | Complete | Natural language processing: word/sentence extraction, stemming, edit distance, phonetic codes, n-grams, stopwords, frequency analysis |
| **[UI](ui-terminal.md#ui)** | Complete | Base UI types: `AppEvent` algebraic event type, `Key:[Lookup]`, `Color:[Lookup]`, `Position` struct |
| **[Terminal](ui-terminal.md#terminal)** | Complete | TUI primitives via ANSI escape codes: raw/cooked mode, cursor control, clear, terminal size, `TerminalAppEvent` |
| **[Graphic](ui-terminal.md#graphic)** | Complete | GUI primitives via SDL2 + Nuklear: window, button, label, checkbox, slider, progress, text input. Requires [SDL2](ui-terminal.md#graphic) |
