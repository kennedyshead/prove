# CLI Reference

Prove ships a single `prove` command with subcommands for building, checking, testing, formatting, and debugging.

**Requirements:** Python 3.11+, gcc or clang

---

## `prove new <name>`

Create a new Prove project with scaffolding.

```bash
prove new hello
```

Creates a directory with `prove.toml`, `src/main.prv`, and a `.gitignore`.

---

## `prove build [path]`

Compile a Prove project to a native binary.

```bash
prove build
prove build path/to/project
prove build --mutate
```

Runs the full pipeline: lex, parse, check, prove, emit C, compile with gcc/clang.

| Flag | Description |
|------|-------------|
| `--mutate` | Enable mutation testing after build |

The project directory must contain a `prove.toml`. Output binary is placed in `build/`.

---

## `prove check [path]`

Type-check and lint Prove source without compiling.

```bash
prove check
prove check src/main.prv
prove check docs/tutorial.md --md
```

| Flag | Description |
|------|-------------|
| `--md` | Also check ` ```prove ` code blocks in Markdown files |

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
prove format --check
prove format --stdin < src/main.prv
prove format docs/ --md
```

| Flag | Description |
|------|-------------|
| `--check` | Check formatting without modifying files (exit 1 if changes needed) |
| `--stdin` | Read from stdin, write formatted output to stdout |
| `--md` | Also format ` ```prove ` blocks in Markdown files |

Reformats all `.prv` files recursively under the given path. Files with parse errors are skipped.

---

## `prove view <file>`

Display the AST of a `.prv` file for debugging.

```bash
prove view src/main.prv
```

Prints a human-readable, indented representation of the parsed AST.

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
| `1` | Error (compilation failed, check failed, tests failed, or formatting mismatch with `--check`) |
