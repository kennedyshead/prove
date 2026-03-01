# Standard Library

The Prove standard library is a set of modules that ship with the compiler. Each module is a `.prv` file declaring types and function signatures, backed by a C implementation that the compiler links into the final binary.

---

## Design Pattern

Stdlib modules follow a consistent pattern:

1. **One cohesive domain per module** — don't mix unrelated concerns.
2. **Function name = the noun** — the thing being operated on.
3. **Verb = the action** — what you do with it.
4. **Same name + different verb = channel dispatch** — the compiler resolves which function to call based on the verb at the call site.

For example, `InputOutput` is organized by *channels*. The `file` channel has three verbs:

```prove
inputs file(path String) String!          // read a file
outputs file(path String, content String)! // write a file
validates file(path String)               // check if file exists
```

The caller's verb determines which function is invoked. This is channel dispatch — one name, multiple intents.

---

## InputOutput

**Module:** `InputOutput` — handles IO operations.

### Standard Channel

Console input and output.

| Verb | Signature | Description |
|------|-----------|-------------|
| `outputs` | `standard(text String)` | Print text to stdout |
| `inputs` | `standard() String` | Read a line from stdin |

```prove
use InputOutput outputs standard, inputs standard

outputs greet()
from
    InputOutput.standard("What is your name?")
    name as String = InputOutput.standard()
    InputOutput.standard(f"Hello, {name}!")
```

### File Channel

Read and write files. File operations are failable — use `!` to propagate errors.

| Verb | Signature | Description |
|------|-----------|-------------|
| `inputs` | `file(path String) Result<String, Error>!` | Read file contents |
| `outputs` | `file(path String, content String) Result<Unit, Error>!` | Write file contents |

```prove
use InputOutput inputs file, outputs file

inputs load_config(path String) String!
from
    InputOutput.file(path)!
```

---

## Upcoming Modules

The standard library grows with each release. Modules are added when the self-hosted compiler needs them.

| Version | Module | Purpose |
|---------|--------|---------|
| v0.6 | **Character** | Character classification (`alpha`, `digit`, `space`, etc.) and string-to-char access |
| v0.6 | **Text** | String operations (`slice`, `contains`, `split`, `join`, `trim`, `replace`) and `Builder` for efficient string construction |
| v0.6 | **Table** | Hash map `Table<V>` with `creates new`, `reads get`, `saves add`, `validates has` |
| v0.7 | **InputOutput** (ext) | New channels: `system` (process execution), `dir` (directory operations), `process` (command-line arguments) |
| v0.7 | **Parse** | Format codecs — `creates toml(source)` to decode, `reads toml(value)` to encode. Same pattern for JSON |
