# Releases

## v1.1.0 (upcoming)

Structured concurrency, terminal UI, and the `proof` CLI wrapper.

**Highlights:**

- **Terminal & UI stdlib modules** — new `Terminal` and `UI` modules with `renders` verb for reactive terminal and GUI applications
- **Structured concurrency** — `attached`, `detached`, and `listens` async verbs backed by `prove_coro` and `prove_event` runtime
- **`proof` CLI** — unified binary wrapping the compiler: `proof check`, `proof build`, `proof test`, `proof format`, `proof new`
- **Go-to-definition** for local files in the LSP
- **Cross-platform release pipeline** — Linux x86_64 and macOS aarch64 binaries published automatically

[:octicons-tag-16: Full release notes](https://code.botwork.se/Botwork/prove/releases/tag/v1.1.0){ .md-button }

---

## v1.0.0

The first stable release of Prove — a fully bootstrapped compiler, standard library, and toolchain.

**Highlights:**

- **22-module standard library** — Character, Text, Table, Array, List, System, Parse, Math, Types, Path, Pattern, Format, Random, Time, Bytes, Hash, Log, Network, Language and more
- **Intent-driven compiler** — verb enforcement, contracts (`requires`, `ensures`, `know`, `assume`, `believe`), refinement types, and failable error propagation
- **C code generation** with region-based memory, PGO builds, and 13-pass optimizer (TCO, dead code elimination, iterator fusion, copy elision, escape analysis, and more)
- **ML-powered LSP** — n-gram completions, shadow-writing, intent-aware stub generation
- **CI/CD pipeline** — automated builds, linting, type checking, unit and e2e tests
- **Documentation site** with full language reference, stdlib docs, and tutorials

[:octicons-tag-16: Full release notes](https://code.botwork.se/Botwork/prove/releases/tag/v1.0.0){ .md-button }
