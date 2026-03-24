# Releases

## v1.1.1 — March 2026

Bug fixes, stdlib improvements, and better ANSI support.

**Changes:**

- **ANSI colors & TextStyle** — new `TextStyle:[Lookup]` type in UI module (`Bold`, `Dim`, `Italic`, `Underline`, `Inverse`, `Strikethrough`) and `Terminal.ansi()` function for Color/TextStyle → ANSI escape sequences
- **Stdlib fixes** — fixed `prove_store.c` infinite recursion in `_get_current_dat()` causing SIGSEGV; registered missing runtime functions (`prove_array_free`, `prove_terminal_check_resize`, `prove_text_write_bytes`)
- **Time-to-string bug fixes** — corrected formatting issues in Time module string conversion
- **Streamlined stdlib modules** — cleaned up module definitions and registrations
- **Tree-sitter grammar updates** — improved syntax highlighting for async verbs, imports, and constants
- **HOF cleanup** — clarified that `map`, `filter`, `each`, `reduce` are compiler builtins, not stdlib declarations

---

## v1.1.0 — March 2026

Structured concurrency, terminal UI, GUI, and the `proof` CLI wrapper.

**Highlights:**

- **Structured concurrency** — `attached`, `detached`, `listens`, and `renders` async verbs backed by `prove_coro` stackful coroutines and `prove_event` runtime
- **Terminal, UI & Graphic stdlib modules** — TUI via ANSI escape codes (zero deps), GUI via SDL2 + Nuklear immediate-mode rendering with windows, buttons, labels, text inputs, checkboxes, sliders, and progress bars
- **`proof` CLI** — unified binary wrapping the compiler: `proof check`, `proof build`, `proof test`, `proof format`, `proof new`
- **Compound assignment operators** — `+=`, `-=`, `*=`, `/=` for mutable state in `renders`/`listens` arms
- **`constants` import verb** — import named constants from modules (`constants PI TAU`)
- **`LookupPattern` matching** — `Key:Escape`, `Key:"k"`, `Color:Red` patterns in match arms
- **Install script** — `curl -sSf .../install.sh | sh` binary installer with platform detection and `--version`/`--prefix` options
- **Go-to-definition** — LSP resolves local variables, function parameters, imported constants, types, and cross-file symbols
- **Cross-platform release pipeline** — Linux x86_64 and macOS aarch64 binaries published automatically with wheel uploads
- **Benchmark examples** — base64, brainfuck, JSON, matrix multiplication, and primes with Python and Rust comparisons
- **Tree-sitter & Pygments updates** — async verbs, import verbs, and constants support in editor grammars
- **Dead code cleanup** — removed 23 unused functions/methods (~378 LOC)
- **Optimizer fixes** — skip memoization for struct/Option/Result parameters; track HOF references in runtime dependency analysis

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
