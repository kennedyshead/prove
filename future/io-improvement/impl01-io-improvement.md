# IO Improvement — `streams` Verb

## Overview

Add a `streams` verb to the IO verb family for looping IO consumption with
exit-via-match-arm semantics. Mirrors the `listens` verb in the async family.

## Module Rename

`InputOutput` → `System` — reflects the full scope of the module (files, processes,
stdin/stdout, environment). Contrasts cleanly with `Network` for remote IO.

## Verb Family (updated)

| Pattern | IO | Async |
|---------|-----|-------|
| Push, move on | `outputs` | `detached` |
| Pull, await | `inputs` | `attach` |
| Loop until exit | `streams` | `listens` |

## Syntax

```prove
/// Stream from IO source, exit via match arm
streams file(file FileHandle) Line
from
    EOF => _
    Content(text) => handle(text)
```

The `streams` verb loops over an IO source until a match arm exits (`=> _`).
Same pattern as `listens` in the async family.

## Design Rationale

- Completes the IO verb family with a looping consumer
- Same exit-via-match-arm pattern as `listens` — no new control flow needed
- Makes streaming IO intent explicit at the call site
- Fits the existing verb family symmetry: each IO verb has an async counterpart
- `System` name covers files, processes, stdin/stdout — all local/OS-level IO

## Finishing Requirements

- Ensure all relevant documentation is up to date.
