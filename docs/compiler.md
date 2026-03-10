---
title: Compiler Features - Prove Programming Language
description: Learn about the Prove compiler pipeline, optimization passes, binary AST format, and runtime generation.
keywords: Prove compiler, compiler pipeline, optimization, binary AST, code generation
---

# Compiler Features

## Pipeline

Prove compiles `.prv` source files to native binaries through a seven-stage pipeline:

```
Source (.prv) → Lexer → Parser → Checker → Prover → Optimizer → C Emitter → gcc/clang → Native Binary
```

| Stage | Input | Output | Key responsibility |
|-------|-------|--------|--------------------|
| **Lexer** | Source text | Token stream | Indent/dedent tracking, string interpolation, regex disambiguation |
| **Parser** | Token stream | AST | Pratt expression parsing, recursive descent for declarations |
| **Checker** | AST | Typed AST + symbol table | Type inference, verb enforcement, match exhaustiveness |
| **Prover** | AST + contracts | Diagnostics | Explain entry verification, contract consistency |
| **Optimizer** | Typed AST | Optimized AST | Tail call optimization, inlining, dead branch elimination, runtime dependency tracking |
| **C Emitter** | Optimized AST | C source | Type mapping, name mangling, lambda hoisting, reference counting |
| **gcc/clang** | C source | Native binary | Optimization, linking with C runtime |

The build system performs **runtime stripping** — only the C runtime modules actually used by the program are compiled and linked. A CLI that parses JSON, reads/writes console, and saves a file with guarded contracts produces a **37 KB** binary.

---

## `prove.toml` Configuration

Every Prove project has a `prove.toml` at its root. The `prove new` command generates one with sensible defaults.

```toml
[package]
name = "hello"
version = "0.1.0"
authors = []
license = ""

[build]
target = "native"
optimize = true
c_flags = []
link_flags = []

[test]
property_rounds = 1000

[style]
line_length = 90
```

| Section | Key | Default | Effect |
|---------|-----|---------|--------|
| `[package]` | `name` | `"untitled"` | Package name, used for the output binary |
| | `version` | `"0.0.0"` | Semantic version |
| | `authors` | `[]` | Author names |
| | `license` | `""` | License identifier |
| `[build]` | `target` | `"native"` | Build target |
| | `optimize` | `false` | Enable compiler optimizations |
| | `c_flags` | `[]` | Extra flags passed to the C compiler (e.g., `["-I/usr/local/include"]`) |
| | `link_flags` | `[]` | Extra flags passed to the linker (e.g., `["-L/usr/local/lib", "-lm"]`) |
| `[test]` | `property_rounds` | `1000` | Number of random inputs per property test (overridable with `--property-rounds`) |
| `[style]` | `line_length` | `90` | Maximum line length for the formatter |

---

## Conversational Errors

Diagnostics are suggestions, not walls. Every error includes the source location, an explanation, and often a concrete fix:

```
error[E042]: `port` may exceed type bound
  --> server.prv:12:5
   |
12 |   port as Port = get_integer(config, "port")
   |                   ^^^^^^^^^^^^^^^^^^^^^^^^^^^^
   = note: `get_integer` returns Integer, but Port requires 1..65535

   try: port as Port = clamp(get_integer(config, "port"), 1, 65535)
    or: port as Port = check(get_integer(config, "port"))!
```

The compiler uses Rust-style diagnostic rendering with ANSI colors, span highlighting, and multi-line context.

See [Diagnostic Codes](diagnostics.md) for the full list of error and warning codes.

---

## Diagnostic Philosophy

Prove is designed to be read and understood by humans. Error messages are not afterthoughts — they are part of the language's user interface. Every diagnostic follows these rules.

### Rule 1: Natural English

Messages are complete sentences. They start with a capital letter, end with a period, and read like something a colleague would say.

```
Bad:  "undefined type 'Foo'"
Good: "Type 'Foo' is not defined."
```

### Rule 2: Show the Fix

Where possible, include a code suggestion or tell the user exactly what to do. Don't just say what's wrong — say how to fix it.

```
"Cannot use '!' in 'parse' because it is not declared as failable.
 Add '!' after the return type."
```

### Rule 3: One Error at a Time

When the parser encounters a catastrophic failure, report only the first error. Cascading errors from a single root cause are noise. Fix the first problem, re-compile, and the cascading errors disappear.

### Rule 4: Three Severity Tiers

| Tier | Meaning | Action |
|------|---------|--------|
| **Error** | Won't compile | Must be fixed by hand |
| **Warning** | Compiles but should be improved | Should be fixed by hand |
| **Info** | Compiles and `prove format` can fix it | Run `prove format` |

Strict mode (`--strict`) promotes warnings to errors. Info stays info.

### Rule 5: Every Code Has Documentation

Every diagnostic code links to `prove.botwork.se/diagnostics/#CODE` with a full explanation, before/after examples, and fix guidance. Codes are clickable in editors via LSP.

### Rule 6: Errors for Broken, Warnings for Improvable

If the code compiles and runs correctly, it is not an error. Errors are reserved for code that genuinely cannot be compiled. Style issues, missing documentation, and code quality improvements are warnings or info.

### Rule 7: Suggestions Are Concrete

The `Suggestion` system provides machine-applicable fixes. When a diagnostic includes a suggestion, the LSP can offer a one-click fix. Suggestions must be syntactically valid Prove code.

---

## Optimizer

When `optimize = true` in `prove.toml`, the compiler runs optimization passes on the AST before C emission. All passes are structure-preserving — they transform the AST without changing program semantics.

| Pass | What it does |
|------|-------------|
| **Runtime dependency collection** | Scans stdlib imports to track which C runtime libraries are needed. Feeds the build system's runtime stripping. |
| **Tail call optimization** | Rewrites self-recursive tail calls into loops. Only applies to functions with a [`terminates`](contracts.md#terminates) annotation where the recursive call is in tail position. Eliminates stack growth for eligible recursion. |
| **Dead branch elimination** | Removes match arms with statically-known-false patterns. When the match subject is a literal, only the matching arm (and wildcards) survive. |
| **Compile-time evaluation** | Evaluates pure functions with constant arguments at compile time. For example, `double(21)` becomes `42` during compilation. Recursive functions are not evaluated to avoid infinite loops. |
| **Small function inlining** | Inlines pure single-expression functions at call sites. Targets functions with pure verbs that have no `terminates`, no recursion, and a single-expression body. Parameters are substituted with arguments. |
| **Dead code elimination** | Removes pure functions that are never called. After inlining, any function whose body was fully inlined is removed from the output. |
| **Memoization candidate identification** | Identifies pure functions eligible for memoization — small, non-recursive pure-verb functions with hashable parameter types. Feeds metadata to the C emitter for cache generation. |
| **Match compilation** | Merges consecutive match statements on the same subject into a single match expression, combining their arms. |

---

## Comptime (Compile-Time Computation)

The compiler includes a tree-walking interpreter that evaluates pure constant expressions at compile time. The optimizer calls this interpreter to fold pure function calls with constant arguments — for example, `double(21)` becomes `42` during compilation.

Comptime expressions execute at compile time and produce C constants. They work in any expression position — variable declarations, function bodies, etc. Available built-in functions: `read(path)` for file IO, `platform()` for target detection, `len()`, `contains()`. User-defined pure functions are also callable from comptime contexts.

```prove
// Compile-time constant folding
MAX_SIZE as Integer = double(512)       // folded to 1024 at compile time

// File reading at compile time
ROUTES as String = comptime
    read("routes.json")

// Conditional compilation via comptime match
MAX_CONNECTIONS as Integer = comptime
    match platform()
        "linux" => 4096
        "macos" => 2048
        _ => 1024
```

---

## Verb Enforcement

The compiler enforces purity rules based on the function's verb. Pure verbs (`transforms`, `validates`, `reads`, `creates`, `matches`) cannot perform side effects — see [Functions & Verbs](functions.md#intent-verbs) for the full verb reference:

- Cannot call built-in IO functions like `println` or `read_file` (E362)
- Cannot call user-defined functions with IO verbs `inputs` or `outputs` (E363)
- Cannot be failable with `!` (E361)

IO verbs (`inputs`, `outputs`) have no such restrictions.

See [Diagnostic Codes](diagnostics.md#e361-pure-function-cannot-be-failable) for details on each enforcement error.

---

## Runtime Modification

Prove supports a pattern for programs that modify their own lookup data at runtime using the **Store** stdlib and **subprocess compilation**.

### Store-Backed Table Management

The `Store` module provides persistent storage for lookup tables with versioning, diffs, and merges. Tables are stored in a directory-based format with optimistic concurrency control.

```prove
Store outputs store table, inputs table version
    validates store table merged, transforms diff patch merge
    reads integrity merged
    types Store StoreTable TableDiff MergeResult Version

// Create a store and load a table (creates empty table if missing)
db as Store = store("/tmp/my_store")!
colors as StoreTable = table(db, "colors")!

// Save a table (version checked — stale writes are rejected)
table(db, colors)!
```

The load → modify → save cycle uses optimistic concurrency: if the on-disk version has changed since the table was loaded, the save fails with a stale-version error. The caller must reload and retry, or use three-way merge.

### Three-Way Merge

When two writers modify the same table concurrently, compute diffs and merge them:

```prove
d1 as TableDiff = diff(base, local_table)
d2 as TableDiff = diff(base, remote_table)
result as MergeResult = merge(base, d1, d2)

match valid merged(result)
    True => table(db, merged(result))!
    False => console("Merge had conflicts")
```

### Subprocess Recompilation

A running Prove program can spawn `prove build` to recompile itself or a sibling module:

```prove
InputOutput inputs system, types ProcessResult

result as ProcessResult = system("prove", ["build", "path/to/project"])
```

### Self-Modifying Binary Pattern

Combining Store with subprocess compilation enables self-modifying binaries:

1. Load a lookup table from the store
2. Modify the table (add/remove/update entries)
3. Save the updated table back to the store
4. Spawn `prove build` to compile a new binary that includes the updated data
5. The new binary reads from the same store, picking up the changes

This pattern keeps data in persistent storage (the store) while allowing the compiled binary to be regenerated with updated lookup tables.
