# `prove check` — Complete Flow

Step-by-step description of what happens from CLI invocation to final output.

---

## CLI Entry Point

**Command:** `prove check [path] [--md] [--strict]`

| Argument / Flag | Type | Default | Description |
|-----------------|------|---------|-------------|
| `path` | positional | `.` | Path to project directory, single `.prv` file, or single `.md` file |
| `--md` | flag | off | Also check `` ```prove `` blocks in `.md` files |
| `--strict` | flag | off | Treat warnings as errors (exit 1 on warnings) |

**Source:** `cli.py` → `check()` function

---

## Dispatch — Three modes based on `path`

The command dispatches to one of three modes depending on the target:

| Condition | Mode | Handler |
|-----------|------|---------|
| `path` is a file with `.prv` suffix | Single-file check | `_check_file()` |
| `path` is a file with `.md` suffix | Markdown check | `_check_md_prove_blocks()` |
| Otherwise (directory or project) | Project check | `_compile_project()` |

---

## Mode 1 — Single `.prv` file

```
cli.py lines 336-345
```

### 1a. Echo status

```
checking <filename>...
```

### 1b. Call `_check_file(filepath)`

```
cli.py → _check_file(target)
```

Returns `(errors, warnings, format_issues)`.

#### Phase 1: Lex

```python
tokens = Lexer(source, filename).lex()
```

- **On `CompileError`:** renders all diagnostics to stderr, returns `(len(diagnostics), 0, 0)`

#### Phase 2: Parse

```python
module = Parser(tokens, filename).parse()
```

- **On `CompileError`:** renders all diagnostics to stderr, returns `(len(diagnostics), 0, 0)`

#### Phase 3: Check

```python
checker = Checker()
symbols = checker.check(module)
```

- No `local_modules` passed (single-file mode — no cross-file imports)
- Iterates `checker.diagnostics`:
  - `Severity.ERROR` → increments error count
  - `Severity.WARNING` → increments warning count
- All diagnostics rendered to stderr

#### Phase 4: Format check

```python
formatter = ProveFormatter(symbols=symbols)
formatted = formatter.format(module)
```

- Compares `formatted` against original `source`
- **If different:** increments `format_issues`, prints filename + excerpt showing first difference

### 1c. Apply `--strict`

```python
if strict:
    errors += warnings
    warnings = 0
```

### 1d. Print summary and exit

```
checked <filename> — 1 file(s), no issues
```

or

```
checked <filename> — 1 file(s), 2 error(s), 1 warning(s), 1 formatting issue(s)
```

- **If errors > 0:** exit 1

---

## Mode 2 — Single `.md` file

```
cli.py lines 347-356
```

### 2a. Echo status

```
checking <filename>...
```

### 2b. Call `_check_md_prove_blocks(md_file)`

```
cli.py → _check_md_prove_blocks(target)
```

Returns `(blocks, errors, warnings)`.

#### Block extraction

```python
fence_re = re.compile(r"```prove\s*\n(.*?)```", re.DOTALL)
```

- Finds all `` ```prove `` fenced code blocks in the markdown file
- Calculates the line number of each block for diagnostics

#### For each block:

1. **Lex:** `Lexer(code, filename).lex()`
   - Filename includes block line: `"<md-file>:<line-number>"`
   - **On `CompileError`:** counts errors, renders diagnostics, continues to next block
2. **Parse:** `Parser(tokens, filename).parse()`
   - **On `CompileError`:** counts errors, renders diagnostics, continues to next block
3. **Check:** `Checker().check(module)`
   - No `local_modules` (each block is independent)
   - Counts errors and warnings from `checker.diagnostics`

### 2c. Apply `--strict` and print summary

Same as Mode 1, with block count included:

```
checked <filename> — 1 file(s), 5 md block(s), no issues
```

- **If errors > 0:** exit 1

---

## Mode 3 — Project check

```
cli.py lines 358-393
```

### 3a. Find and load configuration

```
find_config(target) → config_path
load_config(config_path) → config
```

- **If no `prove.toml` found:** prints `"error: no prove.toml found"` → exit 1

### 3b. Echo status

```
checking <package_name>...
```

### 3c. Call `_compile_project(project_dir)`

```
cli.py → _compile_project(project_dir)
```

Returns `(ok, checked, errors, warnings, format_issues, stats)`.

#### Source discovery

1. Check if `project_dir/src/` exists
   - **If yes:** `src_dir = project_dir / "src"`
   - **If no:** `src_dir = project_dir` (fallback)
2. Find all `.prv` files: `sorted(src_dir.rglob("*.prv"))`
3. **If no files:** prints warning, returns success with zero counts

#### Module registry

```python
local_modules = build_module_registry(prv_files) if len(prv_files) > 1 else None
```

- Only builds cross-file registry when there are 2+ `.prv` files
- See `prove-build.md` Step 4 for full registry details

#### For each `.prv` file:

1. **Lex:** `Lexer(source, filename).lex()`
   - **On `CompileError`:** errors++, renders diagnostics, `continue`
2. **Parse:** `Parser(tokens, filename).parse()`
   - **On `CompileError`:** errors++, renders diagnostics, `continue`
3. **Check:** `Checker(local_modules=local_modules, project_dir=project_dir).check(module)`
   - Counts errors and warnings from diagnostics
   - Collects verification stats (ensures, near_miss, trusted counts)
4. **Format check:** `ProveFormatter(symbols=symbols, diagnostics=checker.diagnostics).format(module)`
   - Compares against source, counts format issues
   - Shows excerpt of first difference if any

### 3d. Check markdown files (if `--md`)

```
cli.py lines 370-377
```

- **Only if** `--md` flag is set **and** target is a directory
- Finds all `.md` files: `sorted(target.rglob("*.md"))`
- For each `.md` file: calls `_check_md_prove_blocks(md_file)`
- Accumulates block count, errors, warnings into project totals

### 3e. Apply `--strict`

```python
if strict:
    errors += warnings
    warnings = 0
```

### 3f. Print summary

```
checked <package_name> — 5 file(s), no issues
```

or with markdown blocks:

```
checked <package_name> — 5 file(s), 12 md block(s), 2 error(s)
```

### 3g. Print verification stats

```
cli.py → _print_verification_stats(stats)
```

Only prints if any verification annotations are present:

```
Verification:
  ✓ 3 functions with ensures (property tests)
  ✓ 1 validators with near_miss (boundary tests)
  ⚠ 1 functions trusted
```

### 3h. Exit

- **If errors > 0:** exit 1

---

## Summary Line Format

Built by `_check_summary()`:

```
checked <name> — <N> file(s)[, <M> md block(s)][, <E> error(s)][, <W> warning(s)][, <F> formatting issue(s)]
```

or:

```
checked <name> — <N> file(s), no issues
```

---

## Complete Pipeline Diagram

```
prove check [path] [--md] [--strict]
│
├─ [if path is *.prv file]
│  ├─ Lexer.lex() → tokens
│  ├─ Parser.parse() → Module
│  ├─ Checker.check() → diagnostics
│  ├─ ProveFormatter.format() → format diff check
│  ├─ [if --strict] warnings → errors
│  └─ Print summary + exit
│
├─ [if path is *.md file]
│  ├─ Extract ```prove blocks
│  ├─ FOR EACH block:
│  │  ├─ Lexer.lex() → tokens
│  │  ├─ Parser.parse() → Module
│  │  └─ Checker.check() → diagnostics
│  ├─ [if --strict] warnings → errors
│  └─ Print summary + exit
│
└─ [if path is directory/project]
   ├─ find_config() → prove.toml
   ├─ load_config() → ProveConfig
   ├─ Discover src_dir and *.prv files
   ├─ build_module_registry() [if multiple files]
   ├─ FOR EACH .prv file:
   │  ├─ Lexer.lex() → tokens
   │  ├─ Parser.parse() → Module
   │  ├─ Checker.check() → diagnostics + stats
   │  └─ ProveFormatter.format() → format diff check
   ├─ [if --md] FOR EACH *.md file:
   │  └─ _check_md_prove_blocks()
   ├─ [if --strict] warnings → errors
   ├─ Print summary
   ├─ Print verification stats
   └─ [if errors] exit 1
```

---

## File Map

| File | Role |
|------|------|
| `cli.py` | CLI entry point, dispatch, summary formatting |
| `config.py` | `prove.toml` discovery and parsing |
| `module_resolver.py` | Cross-file import registry |
| `lexer.py` | Source → token stream |
| `parser.py` | Token stream → Module AST |
| `checker.py` | Semantic analysis, type checking |
| `prover.py` | Explain block / contract verification |
| `formatter.py` | AST → canonical source (for format diffing) |
| `errors.py` | Diagnostic types and rendering |
