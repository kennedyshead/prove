---
title: CLI Reference - Prove Programming Language
description: Complete CLI reference for the Prove compiler including commands for building, testing, checking, formatting, and debugging.
keywords: Prove CLI, prove command, compiler commands, build, test, format
---

# CLI Reference

Prove ships a single `prove` command with subcommands for building, checking, testing, formatting, and debugging.

**Requirements:** Python 3.11+, gcc or clang

---

## `prove new <name>`

Create a new Prove project with scaffolding.

```bash
prove new hello
```

Creates a directory with `prove.toml`, `src/main.prv`, and a `.gitignore`. Automatically builds the stdlib index and ML completion cache.

---

## `prove build [path]`

Compile a Prove project to a native binary.

```bash
prove build
prove build path/to/project
prove build --no-mutate
prove build --debug
```

Runs the full pipeline: lex, parse, check, prove, emit C, compile with gcc/clang. Mutation testing runs by default.

| Flag | Description |
|------|-------------|
| `--debug` | Compile with debug symbols (`-g`) and no optimization (`-O0`) |
| `--no-mutate` | Skip mutation testing |

The project directory must contain a `prove.toml`. The output binary and intermediate build artifacts (generated C, runtime files, PGO data) are placed in `build/`.

---

## `prove check [path]`

Type-check, lint, and verify a Prove project.

```bash
prove check
prove check src/main.prv
prove check docs/tutorial.md --md
prove check --no-intent          # skip intent coverage
prove check --no-challenges      # skip refutation challenges
```

By default, `check` runs **all** available analyses — coherence, refutation challenges, completeness status, and intent coverage. Each analysis auto-skips silently when its data is absent (no `project.intent`, no narrative, no `ensures` contracts, no `todo` stubs). Use `--no-*` flags to opt out explicitly.

| Flag | Description |
|------|-------------|
| `--md` | Also check ` ```prove ` code blocks in Markdown files |
| `--strict` | Promote warnings to errors (exit 1 on any warning) |
| `--no-coherence` | Skip vocabulary consistency check ([I340](diagnostics.md#i340-vocabulary-drift-from-narrative)) |
| `--no-challenges` | Skip refutation challenges from `ensures` contracts |
| `--no-status` | Skip per-module completeness report (todo count vs implemented) |
| `--no-intent` | Skip `project.intent` coverage verification |
| `--nlp-status` | Report NLP backend and data store availability, then exit |

When `path` is a `.prv` file, checks that single file. When `path` is a directory, finds `prove.toml` and checks all files in `src/`. When `path` is a `.md` file (with `--md`), checks all fenced Prove blocks.

Reports type errors, warnings, and formatting issues in a unified summary. Formatting mismatches show a diff-style context excerpt.

---

## `prove test [path]`

Run contract-based tests generated from `ensures`, `believe`, and `near_miss` annotations.

```bash
prove test
prove test --property-rounds 5000
```

| Flag | Description |
|------|-------------|
| `--property-rounds N` | Override the number of property-test iterations (default: from `prove.toml`, usually 1000) |

The compiler parses and checks the source, generates a C test harness from the contracts, compiles it, and executes the tests.

---

## `prove format [path]`

Format Prove source files.

```bash
prove format
prove format src/main.prv
prove format --status
prove format --stdin < src/main.prv
prove format docs/ --md
```

| Flag | Description |
|------|-------------|
| `--status` | Show formatting status without modifying files (exit 1 if changes needed) |
| `--stdin` | Read from stdin, write formatted output to stdout |
| `--md` | Also format ` ```prove ` blocks in Markdown files |

Reformats all `.prv` files recursively under the given path. Files with parse errors are skipped.

---

## Advanced Commands

These commands live under `prove advanced` and are intended for development, debugging, and tooling workflows.

### `prove advanced setup`

Re-download ML stores to `~/.prove/`.

```bash
prove advanced setup
```

ML stores are downloaded automatically to `~/.prove/` on first use — you do not need to run this command. Use it if your stores are corrupted or you want a clean reinstall.

For developers building stores from scratch (requires NLP deps): `pip install 'prove[nlp]'` then `python scripts/build_stores.py`.

---

### `prove advanced generate <file>`

Generate function stubs from narrative or intent. Auto-detects the file type:

- **`.prv`** — generate stubs from the module's `narrative:` block
- **`.intent`** — generate `.prv` files from a project intent file

```bash
prove advanced generate src/auth.prv              # generate stubs from narrative
prove advanced generate src/auth.prv --update     # re-generate @generated functions with todos
prove advanced generate project.intent            # generate .prv files from intent
prove advanced generate project.intent --dry-run  # preview without writing
```

| Flag | Description |
|------|-------------|
| `--update` | Regenerate `@generated` functions that still contain `todo` (`.prv` only) |
| `--dry-run` | Preview generated output without writing files |
| `--nlp` / `--no-nlp` | Force NLP backend on or off (default: auto-detect) |

For `.prv` files, the generator extracts verbs and nouns from the module's `narrative:` block, matches them against the stdlib knowledge base, and produces:

- **Full bodies** when a stdlib function matches with high confidence (includes `explain`, `chosen`, `why_not` prose annotations)
- **Todo stubs** when no stdlib match is found (the programmer fills these in)

Functions already present in the file are skipped.

### `prove advanced intent [file.intent]`

Work with `.intent` project declaration files.

```bash
prove advanced intent                             # show status of all declarations
prove advanced intent --drift                     # show only mismatches
prove advanced intent --generate                  # generate .prv files from intent
prove advanced intent --generate --dry-run        # preview without writing
```

| Flag | Description |
|------|-------------|
| `--status` | Show completeness report |
| `--drift` | Show only mismatches between intent and code |
| `--generate` | Generate `.prv` files from intent |
| `--dry-run` | Preview generated files without writing |
| `--nlp` / `--no-nlp` | Force NLP backend on or off (default: auto-detect) |

The `.intent` file is a human-readable project declaration that describes modules, vocabulary, data flow, and constraints. The toolchain generates `.prv` source files from it and verifies the code stays aligned.

Intent coverage is checked automatically by `prove check` (skip with `--no-intent`).

### `prove advanced view <file>`

Display the AST of a `.prv` file for debugging.

```bash
prove advanced view src/main.prv
```

Prints a human-readable, indented representation of the parsed AST.

### `prove advanced compiler <file>`

Convert between `.prv` lookup types and PDAT binary format.

```bash
prove advanced compiler --load src/data.prv
prove advanced compiler --dump Data.dat
prove advanced compiler --dump Data.dat -o data.prv
```

| Flag | Description |
|------|-------------|
| `--load` | Compile a `.prv` file containing a `:[Lookup]` type to a PDAT binary (`.dat`) |
| `--dump` | Read a PDAT binary and output `.prv` source |
| `--output`, `-o` | Override the output path (default: `<TypeName>.dat` for load, stdout for dump) |

When neither `--load` nor `--dump` is given, the mode is auto-detected from the file extension (`.prv` → load, `.dat`/`.bin` → dump).

The PDAT binary format matches the C runtime (`prove_store.c`) exactly — files produced by this command are interchangeable with the Store runtime at execution time.

### `prove advanced index [path]`

Rebuild the `.prove_cache` ML completion index.

```bash
prove advanced index
```

### `prove advanced export`

Export syntax highlighting data to companion lexer projects (tree-sitter, Pygments, Chroma).

```bash
prove advanced export
prove advanced export -f treesitter --build
```

---

---

## `prove lsp`

Start the Prove language server (LSP protocol).

```bash
prove lsp
```

Used by editor integrations (VS Code, Neovim, etc.) for diagnostics, completions, and hover information. Communicates over stdio.

---

## Exit Codes

| Code | Meaning |
|------|---------|
| `0` | Success |
| `1` | Error (compilation failed, check failed, tests failed, or formatting mismatch with `--status`) |
