# Roadmap

## Versioning

- **V1.0** — Fully featured Python compiler. All language features specified and
  implemented, comprehensive standard library, complete tooling (formatter, LSP,
  testing, mutation testing). This is the reference implementation.
- **V2.0** — Self-hosted compiler. The exact same language and feature set, but
  the compiler is written in Prove and compiled by the V1.0 Python bootstrap.
  The V2.0 compiler will be fundamentally different in implementation from the
  Python version — Prove's algebraic types, pattern matching, and intent verbs
  produce a very different architecture than Python's `isinstance` dispatch and
  class hierarchies.

The Python compiler remains as the bootstrap for V2.0. V2.0 planning begins
after V1.0 is stable.

---

## Version History

| Version | Status | Description |
|---------|--------|-------------|
| v0.1 | Complete | Core pipeline — lexer, parser, checker, prover, C emitter, native binaries |
| v0.2 | Complete (archived) | ASM backend reference implementation (x86_64) |
| v0.3 | Complete | Legacy stdlib cleanup, `List` module |
| v0.4 | Complete | Pure verbs, binary types, namespaced calls, channel dispatch |
| v0.5 | Complete | Turbo runtime — arena allocator, fast hash, string intern |
| v0.6 | Complete | Core stdlib — Character, Text, Table — 440 tests |
| v0.7 | Complete | IO extensions, Parse, C FFI — 484 tests |
| v0.8 | Complete | Formatter type inference |
| v0.8.1 | Complete | Lint system overhaul — diagnostic code splits, doc links, Suggestions |
| v0.8.2 | Complete | `proof` → `explain` migration |
| v0.8.3 | Complete | Remaining lints (E316, E317, W302, W303, W323, W326) — 506 tests |
| v0.9 | Complete | Lexer export tool — 612 tests |
| v0.9.1 | Complete | Documentation parity — mark unimplemented features, add missing diagnostics |
| v0.9.6 | Complete | Stdlib: List, Math, Convert — 747 tests |
| v0.9.7 | Complete | Stdlib: Path, Pattern |
| v0.9.8 | Complete | Stdlib: Format, Error |

---

## Planned Versions

### v0.9.2 — Comptime Execution

Execute `comptime` blocks at compile time. Currently the keyword is parsed
but expressions are not evaluated during compilation. Adds a compile-time
interpreter, file dependency tracking, and constant embedding in emitted C.

### v0.9.3 — Linear Types + Ownership

Implement the `Own` type modifier and compiler-inferred borrows. Use-after-move
detection, the `Mutable` type modifier, and ownership-aware memory management
in the C emitter.

### v0.9.5 — Auto-Memoization + Memory Regions

Automatic memoization of eligible pure functions and region-based memory
allocation for short-lived values. Extends the optimizer with memoization
candidate analysis and adds region allocator support to the C runtime.

### v0.9.6 — Mutation Testing

Implement the `--mutate` flag. The compiler generates mutants (operator swaps,
branch removals, constant changes), runs the contract-based test suite against
each, and reports surviving mutants with suggested contracts to kill them.

### v0.9.6 — Stdlib: List, Math, Convert

Core stdlib expansion covering the most fundamental gaps identified from the
Python compiler's dependency analysis.

- **List** — Operations on `List<T>`: length, first, last, empty, contains,
  index, slice, reverse, sort, range. Type-specific overloads for
  `List<Integer>` and `List<String>` where element comparison is needed.
- **Math** — Numeric functions with Integer/Float overloads: abs, min, max,
  clamp, sqrt, pow, floor, ceil, round, log. Requires `-lm` at link time.
- **Convert** — Type conversions between primitives: `String` ↔ `Integer`,
  `String` ↔ `Float`, `Character` ↔ `Integer`, `Boolean` → `String`. Failable
  string-to-number conversions return `Result`.

### v0.9.7 — Stdlib: Path, Pattern

Extended stdlib modules for file system and text matching.

- **Path** — File path manipulation (pure string operations): join, parent,
  name, stem, extension, absolute, normalize. Uses `/` separator, no filesystem
  access.
- **Pattern** — Regex operations via POSIX `regex.h`: test, search, find_all,
  replace, split. Defines a binary `Match` type with text, start, and end
  accessors.

### v0.9.8 — Stdlib: Format, Error

Utility modules for output formatting and error handling patterns.

- **Format** — String formatting: pad_left, pad_right, center, hex, bin, octal,
  decimal. Number formatting via `snprintf`, manual padding.
- **Error** — Validators for `Result<T, E>` (ok, err) and `Option<T>` (some,
  none), plus `unwrap_or` with type-specific overloads for Integer and String.

### v0.9.9 — Stabilization

Final polish before v1.0. Fix remaining rough edges, ensure all diagnostic
codes are documented, all stdlib modules have complete C backing, and the full
test suite is green.

### v1.0 — Feature-Complete Python Compiler

The reference implementation of Prove. All language features specified and
implemented:

- All 7 intent verbs with full enforcement
- Comptime execution
- Linear types and ownership
- Auto-memoization and memory regions
- Mutation testing
- Complete standard library (10+ modules)
- Formatter, LSP, testing, export tools
- All diagnostic codes documented and tested

V1.0 is the stable foundation. The Python compiler continues to be maintained
as the bootstrap for V2.0.

### v2.0 — Self-Hosted Compiler

Rewrite the Prove compiler in Prove and compile it with the V1.0 Python
bootstrap:

1. Python compiler compiles compiler `.prv` source to a native binary.
2. That binary compiles the same source again.
3. If both produce identical output, the compiler is self-hosting.

V2.0 planning begins after V1.0 is stable. The self-hosted compiler will be
architecturally different from the Python version — Prove's algebraic types
and pattern matching naturally replace Python's class hierarchies and
`isinstance` dispatch, and the stdlib modules built for V1.0 replace Python's
standard library dependencies.

---

## Ecosystem

| Project | Description |
|---------|-------------|
| [tree-sitter-prove](https://code.botwork.se/Botwork/tree-sitter-prove) | Tree-sitter grammar for editor syntax highlighting |
| [pygments-prove](https://code.botwork.se/Botwork/pygments-prove) | Pygments lexer for MkDocs and Sphinx code rendering |
| [chroma-lexer-prove](https://code.botwork.se/Botwork/chroma-lexer-prove) | Chroma lexer for Gitea and Hugo code rendering |

Starting with v0.9, the `scripts/export-lexers.py` script keeps all three lexer projects
in sync with the compiler's canonical keyword lists automatically.
