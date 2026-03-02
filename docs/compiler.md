# Compiler Features

## Pipeline

Prove compiles `.prv` source files to native binaries through a six-stage pipeline:

```
Source (.prv) → Lexer → Parser → Checker → Prover → C Emitter → gcc/clang → Native Binary
```

| Stage | Input | Output | Key responsibility |
|-------|-------|--------|--------------------|
| **Lexer** | Source text | Token stream | Indent/dedent tracking, string interpolation, regex disambiguation |
| **Parser** | Token stream | AST | Pratt expression parsing, recursive descent for declarations |
| **Checker** | AST | Typed AST + symbol table | Type inference, verb enforcement, match exhaustiveness |
| **Prover** | AST + contracts | Diagnostics | Proof obligation verification, contract consistency |
| **C Emitter** | Typed AST | C source | Type mapping, name mangling, lambda hoisting, reference counting |
| **gcc/clang** | C source | Native binary | Optimization, linking with C runtime |

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
optimize = false
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

## Comptime (Compile-Time Computation)

Inspired by Zig. Arbitrary computation at compile time, including IO. Files read during comptime become build dependencies — if the file changes, the module is recompiled.

```prove
MAX_CONNECTIONS as Integer = comptime
  match cfg.target
    "embedded" => 16
    _ => 1024

LOOKUP_TABLE as List<Integer:[32 Unsigned]> = comptime
  collect(map(0..256, crc32_step))

ROUTES as List<Route> = comptime
  decode(read("routes.json"))         // IO allowed — routes.json becomes a build dep
```

---

## Verb Enforcement

The compiler enforces purity rules based on the function's verb. Pure verbs (`transforms`, `validates`, `reads`, `creates`, `matches`) cannot perform side effects:

- Cannot call built-in IO functions like `println` or `read_file` (E362)
- Cannot call user-defined functions with IO verbs `inputs` or `outputs` (E363)
- Cannot be failable with `!` (E361)

IO verbs (`inputs`, `outputs`) have no such restrictions.

See [Diagnostic Codes](diagnostics.md#verb-enforcement-e360-e364) for details on each enforcement error.
