# Changelog

## v1.3.0 — April 2026

### Features

- Tree-sitter as sole parser — the legacy recursive-descent parser is removed; tree-sitter is now the only parser, with syntax and lint combined into a single `check` pass
- `reads` renamed to `derives` — the `reads` verb is renamed to `derives` across the language, stdlib, and docs to better reflect its semantics
- `dispatches` verb — new verb for dispatch-style functions
- Verb name mangling — verb names are now mangled in generated C output for cleaner symbol names
- Linting infrastructure — new lint pass integrated into the compiler check pipeline
- Lookup table static checks — compile-time validation of lookup table entries
- `Option<T>` match arm coercion — match arms mixing Unit and value returns now correctly produce `Option<T>`
- Input/Output runtime requires guards — runtime guards inserted for IO verb `requires` contracts

### Fixes

- Improved diagnostics — better E210/E100 error messages for missing types and modules; reliable diagnostic messages with AST error origin tracking

### Other

- CI improvements — tree-sitter v0.25.4 built from source for ABI 15 compatibility; linker and warning fixes for test command

---

## v1.2.0 — March 2026

### Features

- Verb consistency overhaul — enforced strict verb rules across all 22 stdlib modules (~105 corrections): `derives` = same type, never allocates, never fails; `creates` = different type, always allocates, never fails; `transforms` = failable, may allocate
- Verb-aware optimizer — `derives`/`validates` functions inline up to 3 statements (previously 1); region scope analysis skips scalar `derives`/`validates` calls; new `_is_eliminable_call` helper for dead expression elimination
- Recursive variant types — algebraic types can reference themselves (`type Tree is Leaf(Integer) | Branch(Tree, Tree)`), with mutual recursion support
- `Value<T>` phantom types — `Value<Json>`, `Value<Toml>`, `Value<Csv>`, `Value<Tree>` track data format at the type level; usage-based linking only pulls in runtime code for formats actually used
- Failable record deserialization — `creates` from structured data (`Value`, `Value<Json>`) now returns `Result` when fields may be missing; `transforms` enables `!` propagation
- `Decimal` type parity — Decimal now has full parity with Float across Math, Sequence, Array, and Types modules
- Generic tokenization — `Parse.rule()` + `Parse.tokens()` for building custom tokenizers with regex rules and kind tags
- Prove AST module — `Parse.tree()` + `Prove.root/kind/children/line/column` for programmatic access to Prove syntax trees via tree-sitter
- Tree-sitter grammar unification — grammar.js is now the single source of truth for Prove syntax; `sync_tree_sitter.sh` regenerates, vendors, and rebuilds
- Unified `parse()` facade — single entry point replacing direct Lexer+Parser usage across the compiler

---

## v1.1.1 — March 2026

### Fixes

- Fixed `prove_store.c` infinite recursion in `_get_current_dat()` causing SIGSEGV
- Registered missing runtime functions (`prove_array_free`, `prove_terminal_check_resize`, `prove_text_write_bytes`)
- Time-to-string formatting bug fixes

### Features

- ANSI colors & TextStyle — new `TextStyle:[Lookup]` type in UI module (`Bold`, `Dim`, `Italic`, `Underline`, `Inverse`, `Strikethrough`) and `Terminal.ansi()` function for Color/TextStyle → ANSI escape sequences

### Other

- Streamlined stdlib modules — cleaned up module definitions and registrations
- Tree-sitter grammar updates — improved syntax highlighting for async verbs, imports, and constants
- HOF cleanup — clarified that `map`, `filter`, `each`, `reduce` are compiler builtins, not stdlib declarations

---

## v1.1.0 — March 2026

### Features

- Structured concurrency — `attached`, `detached`, `listens`, and `renders` async verbs backed by `prove_coro` stackful coroutines and `prove_event` runtime
- Terminal, UI & Graphic stdlib modules — TUI via ANSI escape codes (zero deps), GUI via SDL2 + Nuklear immediate-mode rendering
- `proof` CLI — unified binary wrapping the compiler: `proof check`, `proof build`, `proof test`, `proof format`, `proof new`
- Compound assignment operators — `+=`, `-=`, `*=`, `/=` for mutable state in `renders`/`listens` arms
- `constants` import verb — import named constants from modules
- `LookupPattern` matching — `Key:Escape`, `Key:"k"`, `Color:Red` patterns in match arms
- Install script — `curl -sSf .../install.sh | sh` binary installer with platform detection
- Go-to-definition — LSP resolves local variables, function parameters, imported constants, types, and cross-file symbols
- Cross-platform release pipeline — Linux x86_64 and macOS aarch64 binaries published automatically with wheel uploads

### Other

- Benchmark examples — base64, brainfuck, JSON, matrix multiplication, and primes with Python and Rust comparisons
- Tree-sitter & Pygments updates — async verbs, import verbs, and constants support in editor grammars
- Dead code cleanup — removed 23 unused functions/methods (~378 LOC)
- Optimizer fixes — skip memoization for struct/Option/Result parameters; track HOF references in runtime dependency analysis

---

## v1.0.0

The first stable release of Prove — a fully bootstrapped compiler, standard library, and toolchain.

### Features

- 22-module standard library — Character, Text, Table, Array, List, System, Parse, Math, Types, Path, Pattern, Format, Random, Time, Bytes, Hash, Log, Network, Language and more
- Intent-driven compiler — verb enforcement, contracts (`requires`, `ensures`, `know`, `assume`, `believe`), refinement types, and failable error propagation
- C code generation with region-based memory, PGO builds, and 13-pass optimizer (TCO, dead code elimination, iterator fusion, copy elision, escape analysis, and more)
- ML-powered LSP — n-gram completions, shadow-writing, intent-aware stub generation
- CI/CD pipeline — automated builds, linting, type checking, unit and e2e tests
- Documentation site with full language reference, stdlib docs, and tutorials
