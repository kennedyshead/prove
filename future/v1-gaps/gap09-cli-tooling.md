# CLI & Tooling — V1.0 Gap 09

## Overview

The CLI has 7 working commands (`new`, `build`, `check`, `test`, `format`, `view`,
`lsp`). Two gaps exist: `export.py` is not wired as a CLI command, and `prove lint`
was planned but never implemented as a separate command.

## Current State

Working CLI commands in `cli.py`:

| Command | Line | Description |
|---------|------|-------------|
| `build` | 120 | Compile to native binary |
| `check` | 331 | Type-check and lint |
| `test` | 399 | Run contract tests |
| `new` | 504 | Create project |
| `format` | 605 | Format source |
| `lsp` | 705 | Start language server |
| `view` | 713 | Dump AST |

`export.py` exists as a library module with three public functions:
- `generate_treesitter()` (`export.py:227`) — tree-sitter grammar keyword lists
- `generate_pygments()` (`export.py:404`) — Pygments lexer keyword lists
- `generate_chroma()` (`export.py:465`) — Chroma lexer keyword lists

These are called from scripts, not from the CLI.

## What's Missing

1. **`prove export`** — `export.py` should be accessible as a CLI command for
   generating syntax highlighting data.

2. **`prove lint`** — mentioned in `archive/v0.4.2-PLAN.md` but never implemented.
   Currently linting is integrated into `prove check`.

## Implementation

### `prove export` command

1. Add a new Click command `export_cmd` in `cli.py` (following the existing pattern
   of `format_cmd` at line 605).

2. Arguments:
   - `--format` / `-f`: one of `treesitter`, `pygments`, `chroma` (required)
   - `--output` / `-o`: output file path (optional, defaults to stdout)

3. Implementation:
   ```python
   @main.command("export")
   @click.option("-f", "--format", "fmt",
                 type=click.Choice(["treesitter", "pygments", "chroma"]),
                 required=True)
   @click.option("-o", "--output", type=click.Path())
   def export_cmd(fmt, output):
       """Export syntax highlighting data."""
       from prove.export import generate_treesitter, generate_pygments, generate_chroma
       generators = {
           "treesitter": generate_treesitter,
           "pygments": generate_pygments,
           "chroma": generate_chroma,
       }
       result = generators[fmt]()
       if output:
           Path(output).write_text(result)
       else:
           click.echo(result)
   ```

### `prove lint` evaluation

The question is whether `prove lint` should exist as a separate command from
`prove check`.

**Current state**: `prove check` performs both type-checking AND linting (style
warnings, unused imports, etc.). Users cannot run linting without type-checking.

**Decision**: `prove lint` will NOT be added. `prove check` is sufficient.

Rationale:
- Lint checks depend on type information (e.g., unused variable warnings require
  type resolution to know if a variable is actually used)
- Separating lint from check would require either duplicating type-check work or
  adding a "lint-only" mode that skips error reporting
- Users who want lint-only can use `prove check` and filter by warning codes
- Other languages (Rust, Go) integrate linting into their check commands

## Files to Modify

| File | Change |
|------|--------|
| `cli.py` | Add `export_cmd` command |
| `export.py` | Ensure functions return strings (not write to files directly) |

## Exit Criteria

- [ ] `prove export -f treesitter` outputs tree-sitter keyword data
- [ ] `prove export -f pygments` outputs Pygments keyword data
- [ ] `prove export -f chroma` outputs Chroma keyword data
- [ ] `prove export -f treesitter -o keywords.js` writes to file
- [ ] `prove export --help` shows usage
- [ ] Tests: CLI test for export command
- [ ] Decision documented: `prove lint` not added (rationale in this plan)
