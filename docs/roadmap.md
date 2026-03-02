# Roadmap

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
| v0.9 | Planned | Lexer export tool (`prove export`) |
| v1.0 | Planned | Self-hosting compiler |
| v1.1 | Planned | Formatter + View (native) |
| v1.2 | Planned | Language server (native) |
| v1.3 | Planned | Scaffolding + Highlights (native) |

---

## Planned Versions

### v0.9 — Lexer Export Tool

A `prove export` command that generates syntax highlighting definitions for
the three companion lexer projects from the compiler's canonical token and
type lists. This eliminates keyword drift between the compiler and the
lexers.

```
prove export treesitter [--build]    # generate tree-sitter grammar keywords
prove export pygments [--build]      # generate Pygments lexer
prove export chroma [--build]        # generate Chroma lexer
prove export all [--build]           # all three
```

The export tool reads from `tokens.py` (keywords, operators), `types.py`
(built-in types), and `checker.py` (built-in functions) and replaces
sentinel-marked sections in each target file. The `--build` flag also runs
the target's build step (e.g., `tree-sitter generate`, `pip install`,
`go build`).

### v1.0 — Self-Hosting

Rewrite the Prove compiler in Prove and compile it with the Python bootstrap
compiler:

1. Python compiler compiles compiler `.prv` source to a native binary.
2. That binary compiles the same source again.
3. If both produce identical output, the compiler is self-hosting.

The Python compiler remains as the bootstrap. Estimated at ~6,200 lines of
Prove (vs ~12,400 lines of Python) thanks to algebraic types and pattern
matching replacing `isinstance` dispatch.

The self-hosted v1.0 compiler includes `prove build`, `prove check`, and
`prove test`. Other commands are deferred to post-1.0 releases.

### v1.1 — Formatter + View (Native)

Port `formatter.py` and the `prove view` command to the self-hosted compiler.
After this release, `prove format` and `prove view` work as native commands
without Python.

- **`prove format`** — full parity with Python version including `--check`,
  `--stdin`, and `--md` flags.
- **`prove view`** — AST dump for debugging.

Parity confirmed by formatting every `.prv` file with both compilers and
diffing the output.

### v1.2 — Language Server (Native)

Port the LSP server to the self-hosted compiler. After this release,
`prove lsp` runs as a native binary without Python or pygls.

- JSON-RPC protocol implemented directly in Prove (no external dependencies).
- Provides diagnostics, go-to-definition, hover, and code actions.

Parity confirmed by sending identical LSP requests to both servers and
comparing responses.

### v1.3 — Scaffolding + Highlights (Native)

Port project scaffolding and add a new `prove highlights` command:

- **`prove new`** — scaffold new projects (same output as Python version).
- **`prove highlights`** — dump canonical keyword/type/operator lists as
  JSON or TOML for editor plugins, CI pipelines, and the export tool.

---

## Ecosystem

| Project | Description |
|---------|-------------|
| [tree-sitter-prove](https://code.botwork.se/Botwork/tree-sitter-prove) | Tree-sitter grammar for editor syntax highlighting |
| [pygments-prove](https://code.botwork.se/Botwork/pygments-prove) | Pygments lexer for MkDocs and Sphinx code rendering |
| [chroma-lexer-prove](https://code.botwork.se/Botwork/chroma-lexer-prove) | Chroma lexer for Gitea and Hugo code rendering |

Starting with v0.9, the `prove export` command keeps all three lexer projects
in sync with the compiler's canonical keyword lists automatically.
