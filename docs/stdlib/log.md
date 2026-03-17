---
title: Log - Prove Standard Library
description: Log structured logging in the Prove standard library.
keywords: Prove Log, logging, ANSI colors
---

# Log

**Module:** `Log` — console color constants and structured logging.

A pure-Prove module providing ANSI terminal color constants and logging functions. The constants are available immediately; the logging functions use the [`detached`](../async) verb for fire-and-forget output.

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
