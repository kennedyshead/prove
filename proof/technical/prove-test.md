# `prove test` — Complete Flow

Step-by-step description of what happens from CLI invocation to final output.

---

## CLI Entry Point

**Command:** `prove test [path] [--property-rounds N]`

| Argument / Flag | Type | Default | Description |
|-----------------|------|---------|-------------|
| `path` | positional | `.` | Path to project directory (must exist) |
| `--property-rounds` | integer | `None` | Override property test iteration count (falls back to `prove.toml [test] property_rounds`, then `1000`) |

**Source:** `cli.py` → `test()` function

---

## Step 1 — Find and load configuration

```
cli.py → find_config(Path(path)) → load_config(config_path)
```

- Walks up directories looking for `prove.toml`
- **If not found:** prints `"error: no prove.toml found"` → exit 1

### Determine property rounds

```python
rounds = property_rounds or config.test.property_rounds
```

- CLI flag `--property-rounds` takes priority
- Falls back to `prove.toml [test] property_rounds`
- Default: `1000`

### Echo status

```
testing <package_name> (property rounds: <rounds>)...
```

---

## Step 2 — Discover source files

```
cli.py lines 411-416
```

1. Check if `project_dir/src/` exists
   - **If yes:** `src_dir = project_dir / "src"`
   - **If no:** `src_dir = project_dir`
2. Find all `.prv` files: `sorted(src_dir.rglob("*.prv"))`
3. **If no files:** prints `"warning: no .prv files found"` → returns (no exit code)

---

## Step 3 — Build module registry

```
cli.py lines 421-423
```

```python
local_modules = build_module_registry(prv_files) if len(prv_files) > 1 else None
```

- Same cross-file registry as `prove build` (see `prove-build.md` Step 4)

---

## Step 4 — Parse and check all modules

```
cli.py lines 429-449
```

For each `.prv` file:

### 4a. Lex + Parse

```python
tokens = Lexer(source, filename).lex()
module = Parser(tokens, filename).parse()
```

- **On `CompileError`:** sets `had_errors = True`, renders diagnostics, `continue`

### 4b. Type check

```python
checker = Checker(local_modules=local_modules)
symbols = checker.check(module)
```

- Renders all diagnostics to stderr
- If any `Severity.ERROR`: sets `had_errors = True`
- **If no checker errors:** appends `(module, symbols)` to `modules` list

### 4c. Error gate

```python
if had_errors:
    raise SystemExit(1)
```

- **If any file had errors:** exits immediately without running tests
- Tests only run on code that passes all checks

---

## Step 5 — Run tests

```
cli.py → testing.py → run_tests(project_dir, modules, property_rounds=rounds)
```

Returns a `TestResult`:

```python
@dataclass
class TestResult:
    ok: bool
    tests_run: int = 0
    tests_passed: int = 0
    tests_failed: int = 0
    output: str = ""
    c_error: str | None = None
    test_details: list[TestCase] = []
```

### 5a. Generate test cases

For each `(module, symbols)`:

1. Create `TestGenerator(module, symbols, property_rounds=rounds)`
2. Call `gen.generate()` → `TestSuite`

#### Test generation per function

For each `FunctionDef` in the module:

1. Look up function signature in symbol table
2. Skip if return type is `ErrorType` or `GenericInstance` (Result — hard to test)

**Near-miss tests** (from `near_miss:` annotations):
- For each `near_miss` annotation, generates a test that verifies the function does NOT produce the expected output for the given input
- Test name: `_test_nearmiss_<funcname>_<counter>`

**Property tests** (from `ensures:` postconditions):
- **Only if:** verb is not `validates` AND function has `ensures` AND all param types are testable
- Testable types: `Integer`, `Decimal`, `Float`, `Boolean`, `String`, `Option<Value>`, `Result<Value, Error>`, `List<Value>`
- Generates a loop running `rounds` iterations:
  1. Generate random inputs for each parameter
  2. Skip if `requires` preconditions are violated
  3. Call the function
  4. Check each `ensures` condition against the result
  5. Fail on first violation
- Test name: `_test_prop_<funcname>_<counter>`

**Boundary tests** (auto-generated alongside property tests):
- Tests with extreme values: `0`, `1`, `-1`, `INT64_MAX`, `INT64_MIN`
- Only for functions with all-Integer parameters
- Calls the function with boundary values; passes if no crash
- Test name: `_test_boundary_<funcname>_<counter>`

**Believe tests** (from `believe:` annotations — adversarial):
- **Only if:** function has `believe` AND all param types are testable
- Runs 3x the normal rounds (adversarial bias)
- Same structure as property tests but with `believe` conditions
- Test name: `_test_believe_<funcname>_<counter>`

### 5b. Generate preamble (module C code)

```python
emitter = CEmitter(module, symbols)
full_c = emitter.emit()
preamble = self._strip_main(full_c)
```

- Emits the full module's C code
- Strips the `main()` function so the test harness can provide its own

### 5c. Emit complete test C program

```python
gen.emit_test_c(combined_suite)
```

The test program includes:

1. **Preamble** — all module C code (types, functions, constants) minus `main()`
2. **Test infrastructure** — pass/fail counters and tracking functions
3. **PRNG** — xorshift64 random number generator for property tests
   - `_rng_int()` — random 64-bit integer
   - `_rng_int_range(lo, hi)` — random integer in range
   - `_rng_double()` — random double in [-100, 100]
4. **Test functions** — each `TestCase` as a `static void` function
5. **`main()`** — calls all test functions, prints summary, returns 1 if any failed

### 5d. Write test files

```
build/test/test_main.c
```

### 5e. Copy runtime

```python
runtime_c_files = copy_runtime(build_dir)
```

- Copies all C runtime files (no stripping — tests may need any runtime function)

### 5f. Find C compiler

```python
cc = find_c_compiler()
```

- Searches `PATH`: `gcc`, `cc`, `clang`
- **If not found:** returns `TestResult(ok=False, c_error="no C compiler found...")`

### 5g. Compile test binary

```python
compile_c(
    c_files=runtime_c_files + [test_c_path],
    output=test_binary,      # build/test/test_runner
    compiler=cc,
    include_dirs=[runtime_dir],
    extra_flags=["-lm"],
)
```

- No optimization (default `-O0`)
- **On compile error:** returns `TestResult(ok=False, c_error=<error>)`

### 5h. Run test binary

```python
proc = subprocess.run([str(test_binary)], capture_output=True, text=True, timeout=30)
```

- **Timeout:** 30 seconds
- **On timeout:** returns `TestResult(ok=False, output="test runner timed out")`

### 5i. Parse results

Parses stdout + stderr for the summary line:

```
<N> tests, <P> passed, <F> failed
```

Extracts `tests_run`, `tests_passed`, `tests_failed` from the output.

---

## Step 6 — Display results

```
cli.py lines 460-493
```

### 6a. Raw output

```python
if result.output:
    click.echo(result.output)
```

Prints the test runner's stdout/stderr output.

### 6b. C compilation error

```python
if result.c_error:
    click.echo(f"error: {result.c_error}", err=True)
    raise SystemExit(1)
```

### 6c. Tested functions detail

```
Tested functions:
  • [transforms] add (property-based)
  • [transforms] add (boundary values)
  • [validates] is_positive (near-miss case)
  • [transforms] factorial (adversarial)
  rounds per test: 1000
```

Type labels:
| `test_type` | Display |
|-------------|---------|
| `property` | `property-based` |
| `near_miss` | `near-miss case` |
| `boundary` | `boundary values` |
| `believe` | `adversarial` |

### 6d. Final summary

**Success:**

```
tested <package_name> — 5 tests, 5 passed
```

**Failure:**

```
tested <package_name> — 2 FAILED
```

- Exit 1 on failure

### 6e. No testable functions

```
no testable functions found
```

- Returns success (exit 0) — no tests means no failures

---

## Complete Pipeline Diagram

```
prove test [path] [--property-rounds N]
│
├─ find_config() → prove.toml
├─ load_config() → ProveConfig
├─ Determine rounds (CLI flag > config > 1000)
│
├─ Discover src_dir and *.prv files
├─ build_module_registry() [if multiple files]
│
├─ FOR EACH .prv file:
│  ├─ Lexer.lex() → tokens
│  ├─ Parser.parse() → Module
│  ├─ Checker.check() → SymbolTable
│  └─ [skip if errors]
│
├─ [if any errors] → exit 1
│
├─ run_tests(project_dir, modules, rounds)
│  │
│  ├─ FOR EACH (module, symbols):
│  │  ├─ TestGenerator.generate()
│  │  │  ├─ CEmitter.emit() → C preamble (without main)
│  │  │  └─ FOR EACH FunctionDef:
│  │  │     ├─ [if near_miss] → _gen_near_miss_test()
│  │  │     ├─ [if ensures && testable] → _gen_property_tests()
│  │  │     │  └─ _gen_boundary_tests() (auto-added)
│  │  │     └─ [if believe && testable] → _gen_believe_tests()
│  │  └─ Collect all TestCases
│  │
│  ├─ [if no test cases] → "no testable functions found"
│  │
│  ├─ emit_test_c() → build/test/test_main.c
│  ├─ copy_runtime() → build/runtime/*
│  ├─ find_c_compiler() → gcc/cc/clang
│  ├─ compile_c() → build/test/test_runner
│  └─ subprocess.run(test_runner, timeout=30)
│
├─ Print test output
├─ Print tested functions detail
└─ Print summary + exit
```

---

## File Map

| File | Role |
|------|------|
| `cli.py` | CLI entry point, flag handling, result display |
| `config.py` | `prove.toml` discovery and parsing |
| `module_resolver.py` | Cross-file import registry |
| `lexer.py` | Source → token stream |
| `parser.py` | Token stream → Module AST |
| `checker.py` | Semantic analysis, type checking |
| `testing.py` | Test generation, compilation, and execution |
| `c_emitter.py` | Module AST → C source (preamble for tests) |
| `c_runtime.py` | Runtime file copying |
| `c_compiler.py` | C compiler discovery and invocation |
| `errors.py` | Diagnostic types and rendering |
