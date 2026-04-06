---
title: Log - Prove Standard Library
description: Log structured logging in the Prove standard library.
keywords: Prove Log, logging, ANSI colors
---

# Log

**Module:** `Log` — structured logging with UI Color support.

Logging functions use UI `Color` lookups (via `Terminal.ansi()`) for colorized output. The logging functions use the [`detached`](../async.md) verb for fire-and-forget output.

### Colors & Styles

Colors and text styles are provided by the `UI` module's `Color` and `TextStyle` lookup types. Use `Terminal.ansi("red")` or `Terminal.ansi("bold")` for ANSI escape sequences. The argument is a color or style name string — see `Color:[Lookup]` and `TextStyle:[Lookup]` in [UI](ui-terminal.md#ui).

### Logging

| Verb | Signature | Description |
|------|-----------|-------------|
| `detached` | `debug(string String)` | Log a debug message (blue) |
| `detached` | `info(string String)` | Log an info message (green) |
| `detached` | `warning(string String)` | Log a warning message (yellow) |
| `detached` | `error(string String)` | Log an error message (red) |

```prove
  Log detached info error

detached log_status(ok Boolean)
from
    match ok
        true => Log.info("System healthy")
        false => Log.error("System degraded")
```
