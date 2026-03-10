---
title: Error & Log - Prove Standard Library
description: Error Result/Option utilities and Log structured logging in the Prove standard library.
keywords: Prove Error, Prove Log, Result, Option, logging, ANSI colors
---

# Error & Log

## Error

**Module:** `Error` — utilities for [`Result<Value, Error>`](../types.md#option-and-result) and [`Option<Value>`](../types.md#option-and-result).

Validators for inspecting Result and Option values, plus `unwrap_or` for
providing defaults.

### Result Validators

| Verb | Signature | Description |
|------|-----------|-------------|
| `validates` | `ok(result Result<Value, Error>)` | True if Result is Ok |
| `validates` | `err(result Result<Value, Error>)` | True if Result is Err |

### Option Validators

| Verb | Signature | Description |
|------|-----------|-------------|
| `validates` | `some(option Option<Value>)` | True if Option has a value |
| `validates` | `none(option Option<Value>)` | True if Option is empty |

### Unwrap with Default

| Verb | Signature | Description |
|------|-----------|-------------|
| `reads` | `unwrap_or(o Option<Integer>, default Integer) Integer` | Extract integer or use default |
| `reads` | `unwrap_or(o Option<String>, default String) String` | Extract string or use default |

```prove
Error validates ok some, reads unwrap_or

reads safe_first(items List<Integer>) Integer
from
    Error.unwrap_or(List.first(items), 0)
```

---

## Log

**Module:** `Log` — console color constants and structured logging.

A pure-Prove module providing ANSI terminal color constants and logging functions. The constants are available immediately; the logging functions use the [`detached`](../functions.md#async-verbs) verb for fire-and-forget output.

### Constants

| Name | Value | Description |
|------|-------|-------------|
| `RESET` | `\033[0m` | Reset terminal formatting |
| `BOLD` | `\033[1m` | Bold text |
| `DIM` | `\033[2m` | Dim text |
| `RED` | `\033[31m` | Red text |
| `GREEN` | `\033[32m` | Green text |
| `YELLOW` | `\033[33m` | Yellow text |
| `BLUE` | `\033[34m` | Blue text |
| `MAGENTA` | `\033[35m` | Magenta text |
| `CYAN` | `\033[36m` | Cyan text |
| `WHITE` | `\033[37m` | White text |

### Logging

| Verb | Signature | Description |
|------|-----------|-------------|
| `detached` | `debug(string String)` | Log a debug message (white) |
| `detached` | `info(string String)` | Log an info message (green) |
| `detached` | `warning(string String)` | Log a warning message (yellow) |
| `detached` | `error(string String)` | Log an error message (red) |

```prove
Log types RESET RED GREEN, detached info error

detached log_status(ok Boolean)
from
    match ok
        true => Log.info("System healthy")
        false => Log.error("System degraded")
```
