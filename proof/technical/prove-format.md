# `prove format` — Complete Flow

Step-by-step description of what happens from CLI invocation to final output.

---

## CLI Entry Point

**Command:** `prove format [path] [--check] [--stdin] [--md]`

| Argument / Flag | Type | Default | Description |
|-----------------|------|---------|-------------|
| `path` | positional | `.` | Path to project directory or single file |
| `--check` | flag | off | Check formatting without modifying files (exit 1 if changes needed) |
| `--stdin` | flag | off | Read from stdin, write formatted output to stdout |
| `--md` | flag | off | Also format `` ```prove `` blocks in `.md` files |

**Source:** `cli.py` → `format_cmd()` function

---

## Dispatch — Three modes

| Flag | Mode | Description |
|------|------|-------------|
| `--stdin` | Stdin mode | Read stdin → format → write stdout |
| none | File mode | Format `.prv` files in `path` |
| `--md` | Markdown mode | Also format `` ```prove `` blocks in `.md` files (combined with file mode) |

---

## Mode 1 — Stdin (`--stdin`)

```
cli.py lines 607-625
```

### 1a. Read from stdin

```python
source = sys.stdin.read()
```

### 1b. Lex + Parse

```python
tokens = Lexer(source, "<stdin>").lex()
module = Parser(tokens, "<stdin>").parse()
```

- **On `CompileError`:** renders diagnostics to stderr → exit 1

### 1c. Type check (for inference)

```python
symbols, diagnostics = _try_check(source, "<stdin>")
```

`_try_check()` runs Lexer → Parser → Checker and returns `(SymbolTable, diagnostics)`. Returns `(None, [])` if parsing fails. The symbol table is used by the formatter for type inference.

### 1d. Format

```python
formatter = ProveFormatter(symbols=symbols, diagnostics=diagnostics)
formatted = formatter.format(module)
```

### 1e. Output

- **If `--check`:** compares `formatted` vs `source`
  - **If different:** exit 1 (silent — no output)
  - **If same:** exit 0
- **If not `--check`:** writes `formatted` to stdout

---

## Mode 2 — File mode (default)

```
cli.py lines 627-693
```

### 2a. Discover `.prv` files

```python
prv_files = sorted(target.rglob("*.prv")) if target.is_dir() else [target]
```

- **If `path` is a directory:** finds all `.prv` files recursively
- **If `path` is a file:** formats just that one file

### 2b. Build module registry (for type inference)

```python
if target.is_dir() and len(prv_files) > 1:
    local_modules = build_module_registry(prv_files)
```

- Only builds cross-file registry for multi-file directories
- Provides type information across modules for accurate inference

### 2c. Process each `.prv` file

For each `prv_file`:

#### Phase 1: Lex + Parse

```python
tokens = Lexer(source, filename).lex()
module = Parser(tokens, filename).parse()
```

- **On `CompileError`:** increments `skipped`, renders diagnostics, `continue`

#### Phase 2: Type check (for inference)

```python
symbols, diagnostics = _try_check(source, filename, local_modules=local_modules)
```

- Runs the full checker to get symbol table and diagnostics
- Symbol table enables: type inference for untyped variables, unused import detection
- Diagnostics enable: auto-fix of I300 (unused vars), I302 (unused imports), I303 (unused types), I314 (unknown modules)

#### Phase 3: Format

```python
formatter = ProveFormatter(symbols=symbols, diagnostics=diagnostics)
formatted = formatter.format(module)
```

The formatter walks the AST and emits canonical source:

| Feature | Description |
|---------|-------------|
| Consistent indentation | 2-space module indent, 4-space body indent |
| Import merging | Duplicate verb groups merged into one line |
| Unused variable prefix | `_` added to unreferenced variables (I300) |
| Unreachable arm removal | Match arms after `_` wildcard removed (I301) |
| Unused import removal | Unreferenced imports stripped (I302) |
| Unused type removal | Unreferenced type definitions removed (I303) |
| Unknown module removal | Imports from non-existent modules removed (I314) |
| Type inference | `x = expr` → `x as Type = expr` when inferable (I310) |
| `validates` return strip | Redundant `Boolean` return type removed (I360) |
| Operator precedence | Minimal parentheses based on precedence table |
| Import line wrapping | Lines over 90 characters wrapped with continuation |
| Lookup stacking | Multi-value lookup entries formatted with alignment |

#### Phase 4: Write or report

- **If `formatted != source`:** file needs formatting
  - **If `--check`:** prints `"would reformat <filename>"`, increments `changed`
  - **If not `--check`:** writes `formatted` back to the file, prints `"formatted <filename>"`, increments `changed`

### 2d. Process `.md` files (if `--md`)

```
cli.py lines 668-680
```

- **Only if** `--md` flag is set **and** target is a directory
- Finds all `.md` files: `sorted(target.rglob("*.md"))`

For each `.md` file:

#### Block extraction and formatting

```python
result = _format_md_prove_blocks(original)
```

`_format_md_prove_blocks()` uses regex to find all `` ```prove `` code blocks:

```python
re.sub(r"(```prove\s*\n)(.*?)(```)", _replace_block, text, flags=re.DOTALL)
```

For each block:

1. Extract the Prove code between fences
2. Call `_format_source(code, "<md-block>")`:
   - Lex → Parse → Check → Format
   - **If parsing fails:** returns `None` → block left unchanged
3. Replace original block with formatted version (preserving fence markers)

#### Write or report

- Same as `.prv` files: `--check` reports, otherwise writes back

### 2e. Print summary

```
cli.py lines 683-693
```

**No changes needed:**

```
5 file(s) checked, all already formatted.
```

**With skipped files:**

```
5 file(s) checked, 1 skipped (parse errors), all already formatted.
```

**With changes:**

```
2 file(s) reformatted, 5 file(s) checked.
```

or in `--check` mode:

```
2 file(s) would reformat, 5 file(s) checked.
```

### 2f. Exit code

```python
if check and changed:
    raise SystemExit(1)
```

- **`--check` with changes:** exit 1
- **Otherwise:** exit 0

---

## Formatter Internals

### AST Walking

The `ProveFormatter` class walks the `Module` AST node-by-node:

1. **Module declarations** — blank line between each
2. **ModuleDecl** — `module Name`, narrative, imports, types, constants, invariants, body
3. **FunctionDef** — doc comment, signature, annotations, `binary` or `from` + body
4. **MainDef** — similar to FunctionDef but with `main()` syntax
5. **Expressions** — recursive dispatch with precedence-aware parenthesization
6. **Match expressions** — subject + arms (drops unreachable arms after `_`)
7. **Type expressions** — `SimpleType`, `GenericType<Args>`, `Type:[Modifiers]`

### Type Inference

When `SymbolTable` is available, the formatter infers types for untyped variable declarations:

| Expression | Inferred Type |
|------------|---------------|
| `42` | `Integer` |
| `3.14` | `Decimal` |
| `"hello"` | `String` |
| `true` | `Boolean` |
| `'a'` | `Character` |
| `x + y` (arithmetic) | Type of left operand |
| `x > y` (comparison) | `Boolean` |
| `func(args)` | Return type from symbol table |
| `Module.func(args)` | Return type from symbol table |
| `Constructor(args)` | Constructor's type |
| `expr!` (FailProp) | Unwrapped `Result<Value, Error>` → `Value` |
| `[1, 2, 3]` | `List<Integer>` (from first element) |

### Diagnostic-Driven Fixes

The formatter uses diagnostics from the checker to apply automatic fixes:

| Code | Fix |
|------|-----|
| I300 | Prefix unused variable name with `_` |
| I301 | Remove unreachable match arms after `_` wildcard |
| I302 | Remove unused import items (or entire import line) |
| I303 | Remove unused type definitions |
| I310 | Add inferred type annotation to untyped variable |
| I314 | Remove imports from unknown/non-existent modules |
| I360 | Strip redundant `Boolean` return type from `validates` |

---

## Complete Pipeline Diagram

```
prove format [path] [--check] [--stdin] [--md]
│
├─ [if --stdin]
│  ├─ Read from stdin
│  ├─ Lexer.lex() → tokens
│  ├─ Parser.parse() → Module
│  ├─ _try_check() → (symbols, diagnostics)
│  ├─ ProveFormatter.format() → formatted
│  ├─ [if --check] compare → exit 1 if different
│  └─ [else] write formatted to stdout
│
└─ [file mode]
   ├─ Discover *.prv files
   ├─ build_module_registry() [if multi-file directory]
   │
   ├─ FOR EACH .prv file:
   │  ├─ Lexer.lex() → tokens
   │  ├─ Parser.parse() → Module
   │  ├─ [on error] skip + count
   │  ├─ _try_check() → (symbols, diagnostics)
   │  ├─ ProveFormatter.format() → formatted
   │  └─ [if changed]
   │     ├─ [if --check] "would reformat"
   │     └─ [else] write back + "formatted"
   │
   ├─ [if --md AND directory]
   │  └─ FOR EACH *.md file:
   │     ├─ _format_md_prove_blocks(original)
   │     │  └─ FOR EACH ```prove block:
   │     │     └─ _format_source() → formatted block
   │     └─ [if changed] write back or report
   │
   ├─ Print summary
   └─ [if --check AND changed] exit 1
```

---

## File Map

| File | Role |
|------|------|
| `cli.py` | CLI entry point, file discovery, summary |
| `formatter.py` | AST → canonical Prove source |
| `lexer.py` | Source → token stream |
| `parser.py` | Token stream → Module AST |
| `checker.py` | Semantic analysis (for type inference + diagnostics) |
| `module_resolver.py` | Cross-file import registry (for type inference) |
| `errors.py` | Diagnostic types |
