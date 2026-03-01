# Roadmap

## Version History

| Version | Status | Description |
|---------|--------|-------------|
| v0.1 | Complete | Core pipeline — lexer, parser, checker, prover, C emitter, native binaries |
| v0.2 | Complete (archived) | ASM backend reference implementation (x86_64) |
| v0.3 | Complete | Legacy stdlib cleanup, `List` module |
| v0.4 | Complete | Pure verbs, binary types, namespaced calls, channel dispatch — 394 tests |
| v0.5 | Planned | Turbo runtime — arena allocator, fast hash, string intern |
| v0.6 | Planned | Core stdlib — Character, Text, Table |
| v0.7 | Planned | IO extensions and Parse |
| v1.0 | Planned | Self-hosting compiler |

---

## Planned Versions

### v0.5 — Turbo Runtime

High-performance C runtime primitives that the stdlib builds on:

- **Arena allocator** — bump-pointer allocation, eliminates per-object malloc and reference counting in hot paths.
- **Fast hash** — hardware CRC32 hash (x86_64 + ARM64 with software fallback) for hash tables and string interning.
- **String intern table** — string deduplication so that string comparisons become pointer equality.

### v0.6 — Core Stdlib

The three data modules the self-hosted compiler needs most:

- **Character** — character classification (`alpha`, `digit`, `space`, etc.) and indexed access into strings.
- **Text** — string querying (`contains`, `starts_with`, `index_of`), transformation (`split`, `join`, `trim`, `replace`), and `Builder` for efficient string construction.
- **Table** — hash map from `String` keys to values. Uses the turbo runtime's fast hash internally.

### v0.7 — IO Extensions and Parse

Extend `InputOutput` with the channels the compiler needs, and add structured format parsing:

- **InputOutput extensions** — `system` (process execution via fork/exec), `dir` (directory listing and creation), `process` (command-line arguments), and `validates` verbs for existence checks on all channels.
- **Parse** — format codecs with a two-function pattern: `creates toml(source)` decodes, `reads toml(value)` encodes. Same for JSON. Additional formats follow the same pattern.

### v1.0 — Self-Hosting

Rewrite the Prove compiler in Prove and compile it with the Python bootstrap compiler:

1. Python compiler compiles compiler `.prv` source to a native binary.
2. That binary compiles the same source again.
3. If both produce identical output, the compiler is self-hosting.

The Python compiler remains as the bootstrap. Estimated at ~5,900 lines of Prove (vs ~10,800 lines of Python) thanks to algebraic types and pattern matching replacing `isinstance` dispatch.

---

## Ecosystem

| Project | Description |
|---------|-------------|
| [tree-sitter-prove](https://code.botwork.se/Botwork/tree-sitter-prove) | Tree-sitter grammar for editor syntax highlighting |
| [chroma-lexer-prove](https://code.botwork.se/Botwork/chroma-lexer-prove) | Chroma lexer for Gitea and Hugo code rendering |
