# `prove build` — Complete Flow

Step-by-step description of what happens from CLI invocation to final output.

---

## CLI Entry Point

**Command:** `prove build [path] [--mutate] [--debug]`

| Argument / Flag | Type | Default | Description |
|-----------------|------|---------|-------------|
| `path` | positional | `.` | Path to project directory (must exist) |
| `--mutate` | flag | off | Run mutation testing after successful build |
| `--debug` | flag | off | Compile with debug symbols (`-g`) and no optimization |

**Source:** `cli.py` → `build()` function

---

## Step 1 — Find and load configuration

```
cli.py → find_config(Path(path)) → load_config(config_path)
```

### 1a. `find_config(start_path)`

- If `start_path` is a file, uses its parent directory
- Walks up the directory tree looking for `prove.toml`
- **If not found:** raises `FileNotFoundError` → CLI prints `"error: no prove.toml found"` → exit 1

### 1b. `load_config(config_path)`

Parses `prove.toml` via `tomllib`. Sections:

| Section | Field | Default | Description |
|---------|-------|---------|-------------|
| `[package]` | `name` | `"untitled"` | Binary output name |
| `[package]` | `version` | `"0.0.0"` | Project version |
| `[package]` | `authors` | `[]` | Author list |
| `[package]` | `license` | `""` | License identifier |
| `[build]` | `target` | `"native"` | Compilation target |
| `[build]` | `optimize` | `false` | Enable AST optimizer + `-O2 -flto` |
| `[build]` | `c_flags` | `[]` | Extra C compiler flags |
| `[build]` | `link_flags` | `[]` | Extra linker flags |
| `[test]` | `property_rounds` | `1000` | Property-based test iterations |
| `[style]` | `line_length` | `90` | Formatter line length |

### 1c. CLI output

```
building <package_name>...
```

---

## Step 2 — Call `build_project()`

```
cli.py → build_project(project_dir, config, debug=debug)
```

**Source:** `builder.py` → `build_project()`

Returns a `BuildResult`:

```python
@dataclass
class BuildResult:
    ok: bool
    binary: Path | None = None
    diagnostics: list[Diagnostic] = ...
    c_error: str | None = None
```

---

## Step 3 — Discover source files

```
builder.py lines 37-43
```

1. Check if `project_dir/src/` exists
   - **If yes:** `src_dir = project_dir / "src"`
   - **If no:** `src_dir = project_dir`
2. Find all `.prv` files: `sorted(src_dir.rglob("*.prv"))`
3. **If no .prv files found:** return `BuildResult(ok=False, c_error="no .prv files found")`

---

## Step 4 — Build module registry (multi-file projects)

```
builder.py lines 48-51 → module_resolver.py → build_module_registry()
```

- **If only 1 `.prv` file:** `local_modules = None` (skip registry)
- **If multiple `.prv` files:** build a cross-file import registry

### `build_module_registry(prv_files)` does:

For each `.prv` file:

1. Read file content
2. Lex + parse (skip file silently on error)
3. Find `ModuleDecl` → extract module name
4. Build type registry: start with builtins (`Integer`, `String`, `Boolean`, etc.) + generics (`List<Value>`, `Option<Value>`, `Result<Value, Error>`, `Error`)
5. Resolve all type definitions from the module's `ModuleDecl`
   - Record types → `RecordType`
   - Algebraic types → `AlgebraicType` + variant constructor signatures
   - Refinement types → `RefinementType`
   - Binary types → `PrimitiveType`
6. Extract function signatures (verb, name, param types, return type, can_fail)
   - `validates` without explicit return type → `Boolean`
   - Other verbs without explicit return type → `Unit`
7. Store as `LocalModuleInfo(name, types, functions)` keyed by module name

**Returns:** `dict[str, LocalModuleInfo]` — one entry per module

---

## Step 5 — Process each `.prv` file

```
builder.py lines 53-91 — main loop
```

For each `prv_file` in sorted order:

### 5a. Read source

```python
source = prv_file.read_text()
filename = str(prv_file)
```

### 5b. Lex

```
Lexer(source, filename).lex() → list[Token]
```

The lexer:

1. Iterates through source character-by-character
2. At each line start, processes indentation → emits `INDENT`/`DEDENT` tokens (Python-style)
3. Tabs count as 4 spaces (silently accepted)
4. Skips line comments (`//`), preserves doc comments (`///`) as `DOC_COMMENT` tokens
5. Lexes string literals (plain `"..."`, triple `"""..."""`, raw `r"..."`, f-strings `f"...{expr}..."`)
6. Lexes character literals (`'x'`), regex literals (`/pattern/`), path literals (`/path/to/file`)
7. Lexes numbers (decimal, `0x` hex, `0b` binary, `0o` octal, with `_` separators)
8. Classifies identifiers:
   - lowercase/snake_case → `IDENTIFIER`
   - PascalCase → `TYPE_IDENTIFIER`
   - ALL_CAPS → `CONSTANT_IDENTIFIER`
   - Keywords → their specific `TokenKind`
9. Lexes operators and punctuation (single-char and two-char like `|>`, `=>`, `->`, `==`, `!=`, `<=`, `>=`, `&&`, `||`, `..`)
10. Suppresses newlines inside brackets and after certain tokens (`,`, operators, `=>`, `|>`)
11. Emits remaining `DEDENT` tokens + `EOF`
12. **If any errors collected:** raises `CompileError` with diagnostics

**On `CompileError`:** diagnostics accumulated, file skipped → `continue`

### 5c. Parse

```
Parser(tokens, filename).parse() → Module
```

The parser:

1. Skips leading newlines
2. Main loop — parses declarations until EOF:
   - `module` → `ModuleDecl` (with narrative, imports, type definitions, constants, foreign blocks)
   - Verb keywords (`transforms`, `validates`, `inputs`, `outputs`, `reads`, `creates`, `matches`) → `FunctionDef`
   - `main` → `MainDef`
   - `///` doc comments → attached to next declaration
   - `//` comments → `CommentDecl`
3. For function definitions:
   - Parses signature: `verb name(param Type, ...) ReturnType[!]`
   - Parses annotations (any order): `ensures`, `requires`, `explain`, `terminates`, `trusted`, `why_not`, `chosen`, `near_miss`, `know`, `assume`, `believe`, `intent`, `satisfies`, `invariant_network`
   - Parses body: `from` + indented statements, or `binary` keyword
4. For imports inside module: `ModuleName verb name name, verb name, ...`
5. Expression parsing uses Pratt parser with binding powers for operator precedence
6. Pattern matching in `match` arms: variant names, literals, bindings, wildcards
7. Error recovery: on parse error, skips to next statement boundary and continues
8. **If no `module` declaration found:** emits E200 and raises `CompileError`

**On `CompileError`:** diagnostics accumulated, file skipped → `continue`

### 5d. Format (first pass — canonicalize source)

```
Checker(local_modules).check(module) → symbols
ProveFormatter(symbols=symbols).format(module) → formatted_source
```

#### Type check (for formatting context):

1. Registers built-in types and functions
2. **Pass 1 — Registration:** walks all declarations, registers:
   - Type definitions in symbol table
   - Function signatures (including variant constructors)
   - Constants with type annotations
   - Imports from stdlib or local modules
   - Foreign function blocks
3. **Pass 2 — Checking:** type-checks all function bodies:
   - Infers expression types
   - Validates function call signatures
   - Checks field access against type definitions
   - Validates contracts (ensures/requires/know/assume/believe)
   - Calls `ProofVerifier.verify()` for explain block consistency
   - Tracks ownership (moved variables)
   - Reports unused items (I-level diagnostics)
4. Returns `SymbolTable` with all resolved type information

#### Formatting:

1. Walks module AST in declaration order
2. Emits canonical source:
   - Consistent indentation (2 spaces)
   - Merges duplicate verb groups in imports
   - Prefixes unused variables with `_`
   - Removes unreachable match arms
   - Removes unused imports/types
   - Adds inferred type annotations to untyped variables
   - Strips redundant `Boolean` return on `validates`
3. **If formatted != original:** writes formatted source back to the `.prv` file

### 5e. Re-lex + Re-parse (from formatted source)

```
Lexer(formatted, filename).lex() → tokens
Parser(tokens, filename).parse() → module
```

Repeats lexing and parsing on the **formatted** source to get a clean AST from canonical input.

**On `CompileError`:** diagnostics accumulated, file skipped → `continue`

### 5f. Final type check

```
Checker(local_modules).check(module) → symbols
```

Full semantic analysis on the re-parsed AST:

1. Same two-pass process as 5d
2. All diagnostics (errors + warnings) accumulated into `all_diags`
3. **If `checker.has_errors()`:** file skipped → `continue`
4. **If no errors:** `(module, symbols)` added to `modules_and_symbols` list

---

## Step 6 — Check for errors across all files

```
builder.py lines 94-96
```

- If **any** diagnostic has `severity == ERROR`:
  - Return `BuildResult(ok=False, diagnostics=all_diags)` immediately
  - Never proceeds to C compilation

---

## Step 7 — C backend: `_build_c()`

```
builder.py lines 101-195
```

### 7a. Optimize (if `config.build.optimize` is true)

```
Optimizer(module, symbols).optimize() → optimized_module
```

For each module:

- **If `config.build.optimize`:**
  1. Create `Optimizer` instance
  2. Run optimization passes:
     - **Runtime dependency collection:** scans imports to track which C runtime libs are needed
     - **Tail call optimization:** rewrites self-recursive functions with `terminates:` into loop form
     - **Dead branch elimination:** removes unreachable match arms and unused assignments
     - **Function inlining:** inlines small pure functions (< 3 statements)
     - **Memoization identification:** marks pure functions for caching
     - **Match compilation:** flattens/optimizes pattern matching
     - **Copy elision:** eliminates unnecessary copies for immutable values
     - **Iterator fusion:** combines chained List operations into single loops
  3. Extract `memo_info` (memoization metadata)
  4. Extract `runtime_deps` (which stdlib C runtime libs are used)
- **If optimize is off:** no optimization, `memo_info = None`, `runtime_deps = None`

### 7b. Emit C code

```
CEmitter(module, symbols, memo_info).emit() → c_source_string
```

For each module:

1. Emit `#include` directives for standard C headers and runtime headers
2. Emit foreign library includes (from `foreign` blocks)
3. Emit type forward declarations (all struct types)
4. Emit type definitions:
   - Record types → C structs
   - Algebraic types → tagged unions (enum + union of structs)
   - Lookup types → lookup tables
5. Emit record-to-value converter functions
6. **If memo_info:** emit memoization hash tables
7. Emit module constants as `static const`
8. Emit function forward declarations (for mutual recursion)
9. Emit hoisted lambda functions (lifted from inline to module scope)
10. Emit function bodies:
    - Variable declarations with C types
    - Expression evaluation
    - Control flow (loops from tail-call optimization, branches from match)
    - Contract assertions (requires/ensures as runtime checks)
    - Return statements
11. **If module has `main`:** emit C `main()` entry point
12. Collect all C source strings

### 7c. Write generated C files

```
builder.py lines 128-137
```

1. Create `build/` and `build/gen/` directories
2. For each module's C source: write to `build/gen/module_0.c`, `build/gen/module_1.c`, etc.

### 7d. Copy runtime files (with stripping)

```
c_runtime.py → copy_runtime(build_dir, c_sources, stdlib_libs)
```

1. Create `build/runtime/` directory
2. Scan all generated C source strings with regex to extract `prove_*` function calls
3. Map function calls → runtime library names (via `_RUNTIME_FUNCTIONS` table)
4. Add libraries needed by stdlib modules (from `stdlib_libs` set, via `STDLIB_RUNTIME_LIBS` table)
5. **Always include core files:** `prove_runtime`, `prove_arena`, `prove_region`, `prove_string`, `prove_hash`, `prove_intern`, `prove_list`, `prove_option`, `prove_result`, `prove_text`
6. Copy selected `.c` and `.h` files from bundled `prove.runtime` package to `build/runtime/`
7. Return list of `.c` file paths needed for compilation

### 7e. Find C compiler

```
c_compiler.py → find_c_compiler()
```

- Searches `PATH` in order: `gcc`, `cc`, `clang`
- Returns first found, or `None`
- **If not found:** return `BuildResult(ok=False, c_error="no C compiler found (install gcc or clang)")`

### 7f. Collect compiler and linker flags

Starting flags:

```
extra_flags = config.build.c_flags    (from prove.toml [build] c_flags)
link_flags  = config.build.link_flags (from prove.toml [build] link_flags)
link_flags += ["-lm"]                 (math library, always needed)
```

Then for each module's `ModuleDecl`:

1. **Foreign blocks:** for each `foreign` block with a library name:
   - `"libcurl"` → `-lcurl` (strip `lib` prefix)
   - `"curl"` → `-lcurl` (add `-l` prefix)
2. **Stdlib imports:** for each imported module, query `stdlib_link_flags()`:
   - Add returned flags (e.g., `-lpthread`) if not already present

### 7g. Determine output paths

```python
runtime_dir = build_dir / "runtime"
binary_name = config.package.name or "a.out"
binary_path = build_dir / binary_name
```

### 7h. Compile C to native binary

```
c_compiler.py → compile_c(c_files, output, compiler, optimize, debug, include_dirs, extra_flags)
```

**Compiler flags constructed (in order):**

| Flag | Condition | Description |
|------|-----------|-------------|
| `<compiler>` | always | `gcc`, `cc`, or `clang` |
| `-O2 -flto` | if `optimize=True` and `debug=False` | Level 2 optimization + link-time optimization |
| `-O0` | if `optimize=False` or `debug=True` | No optimization |
| `-g -rdynamic` | if `debug=True` | Debug symbols + export symbols for backtraces |
| `-Wall -Wextra -Wno-unused-parameter` | always | Warnings |
| `-fno-strict-aliasing` | always | Allow `void*` casts for `Prove_Header*` |
| `-I build/runtime` | always | Include path for runtime headers |
| `build/runtime/prove_*.c` | always | All selected runtime C files |
| `build/gen/module_*.c` | always | All generated module C files |
| `-o build/<binary_name>` | always | Output binary path |
| `<config.build.c_flags>` | if configured | Extra compiler flags from prove.toml |
| `<link_flags>` | always | `-lm` + foreign libs + stdlib libs + config link_flags |

**Optimization logic:**

```
optimize = config.build.optimize AND (NOT debug)
```

- `--debug` flag disables optimization even if `[build] optimize = true` in config
- Debug mode adds `-g -rdynamic` regardless of optimization setting

**Timeout:** 60 seconds

**On compiler error:** return `BuildResult(ok=False, c_error=<error + stderr>)`

**On success:** return `BuildResult(ok=True, binary=binary_path, diagnostics=all_diags)`

---

## Step 8 — Render diagnostics

```
cli.py lines after build_project() returns
```

1. Create `DiagnosticRenderer(color=True)`
2. For each diagnostic in `result.diagnostics`:
   - Render in Rust-style format: `severity[CODE]: message` + source location + source line + carets
   - Print to stderr
3. **If `result.ok == False`:**
   - If `result.c_error`: print C compiler error to stderr
   - Exit with code 1

---

## Step 9 — Mutation testing (if `--mutate`)

```
cli.py lines 148-194
```

Only runs if build succeeded **and** `--mutate` flag was passed.

```
running mutation testing...
```

### 9a. Re-parse all source files

1. Find all `.prv` files again (same discovery as step 3)
2. Build module registry if multiple files
3. For each file: lex → parse → check (skip on error)
4. Collect `(module, symbols)` pairs

### 9b. Generate and test mutants

```
mutator.py → run_mutation_tests(project_dir, modules, max_mutants=50, property_rounds=100)
```

For each module:

1. `Mutator(module).generate_mutants(max_mutants=50)` — generates mutations:
   - **Operator mutations:** `+` ↔ `-` ↔ `*` ↔ `/`, comparison swaps, boolean flips
   - Each mutation creates a modified copy of the AST
2. For each mutant:
   - Generate test suite from the **mutated** module's contracts (ensures/requires/near_miss/believe)
   - Run tests: compile mutant C code + test harness → execute
   - **If any test fails:** mutant is **killed** (contracts caught the mutation)
   - **If all tests pass:** mutant **survived** (contracts are too weak)
   - On any exception: count as error

### 9c. Save survivors

```
mutator.py → save_survivors(project_dir, result)
```

- Saves to `project_dir/.prove/mutation-survivors.json`
- These survivors are read by the checker on next build to emit W330 warnings

### 9d. Output results

```
mutation score: 85.0% (17/20 killed)

surviving mutants (3):
  mut_1: replaced + with - at 12:5
    suggestion: add contract to kill this mutant
  ...
```

---

## Step 10 — Final output

```
cli.py final line
```

```
built <package_name> -> build/<binary_name>
```

---

## Complete Pipeline Diagram

```
prove build [path] [--mutate] [--debug]
│
├─ find_config() → prove.toml
├─ load_config() → ProveConfig
│
├─ build_project(project_dir, config, debug)
│  │
│  ├─ Discover src_dir and *.prv files
│  ├─ build_module_registry() [if multiple files]
│  │
│  ├─ FOR EACH .prv file:
│  │  ├─ Lexer.lex()           → list[Token]
│  │  ├─ Parser.parse()        → Module AST
│  │  ├─ Checker.check()       → SymbolTable (for formatting)
│  │  ├─ ProveFormatter.format() → canonical source
│  │  ├─ [write back if changed]
│  │  ├─ Lexer.lex()           → list[Token] (re-lex formatted)
│  │  ├─ Parser.parse()        → Module AST (re-parse)
│  │  ├─ Checker.check()       → SymbolTable (final)
│  │  │  └─ ProofVerifier.verify() (explain block validation)
│  │  └─ [skip file if errors]
│  │
│  ├─ [abort if any file has errors]
│  │
│  └─ _build_c()
│     ├─ FOR EACH module:
│     │  ├─ [if optimize] Optimizer.optimize() → optimized Module
│     │  └─ CEmitter.emit()                   → C source string
│     ├─ Write build/gen/module_*.c files
│     ├─ copy_runtime() → build/runtime/*.{c,h}
│     ├─ find_c_compiler() → gcc/cc/clang
│     ├─ Collect compiler + linker flags
│     └─ compile_c() → build/<binary_name>
│
├─ Render diagnostics to stderr
│
├─ [if --mutate]
│  ├─ Re-parse all .prv files
│  ├─ run_mutation_tests() → MutationTestResult
│  ├─ save_survivors() → .prove/mutation-survivors.json
│  └─ Print mutation score + surviving mutants
│
└─ Print: built <name> -> build/<binary>
```

---

## File Map

| File | Role |
|------|------|
| `cli.py` | CLI entry point, flag handling, output |
| `config.py` | `prove.toml` discovery and parsing |
| `builder.py` | Build orchestration (`build_project`, `_build_c`) |
| `module_resolver.py` | Cross-file import registry |
| `lexer.py` | Source → token stream |
| `parser.py` | Token stream → Module AST |
| `checker.py` | Semantic analysis, type checking |
| `prover.py` | Explain block / contract verification |
| `optimizer.py` | AST optimization passes |
| `c_emitter.py` | Module AST → C source code |
| `c_runtime.py` | Runtime file selection and copying |
| `c_compiler.py` | C compiler discovery and invocation |
| `formatter.py` | AST → canonical Prove source |
| `mutator.py` | Mutation generation and testing |
| `testing.py` | Contract-based test generation |
| `errors.py` | Diagnostic types and rendering |
| `stdlib_loader.py` | Stdlib module signatures and link flags |
