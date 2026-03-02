# Standard Library

The Prove standard library is a set of modules that ship with the compiler. Each module is a `.prv` file declaring types and function signatures, backed by a C implementation that the compiler links into the final binary.

---

## Design Pattern

Stdlib modules follow a consistent pattern:

1. **One cohesive domain per module** — don't mix unrelated concerns.
2. **Function name = the noun** — the thing being operated on.
3. **Verb = the action** — what you do with it.
4. **Same name + different verb = channel dispatch** — the compiler resolves which function to call based on the verb at the call site.

### Verb Families

Verbs fall into two families. **Pure verbs** have no side effects — the compiler enforces this:

| Verb | Intent | Example |
|------|--------|---------|
| `transforms` | Convert data from one form to another | `transforms trim(s String) String` |
| `validates` | Check a condition, return Boolean | `validates has(key String, table Table<V>)` |
| `reads` | Extract or query data without changing it | `reads get(key String, table Table<V>) Option<V>` |
| `creates` | Construct a new value from scratch | `creates builder() Builder` |
**IO verbs** interact with the outside world:

| Verb | Intent | Example |
|------|--------|---------|
| `inputs` | Read from an external source | `inputs file(path String) String!` |
| `outputs` | Write to an external destination | `outputs file(path String, content String)!` |

The distinction matters: pure verbs cannot call IO functions, cannot use `!`, and are safe to memoize, inline, or reorder. IO verbs make side effects explicit in the function signature.

### Channel Dispatch

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

### Console Channel

Console input, output, and availability check.

| Verb | Signature | Description |
|------|-----------|-------------|
| `outputs` | `console(text String)` | Print text to stdout |
| `inputs` | `console() String` | Read a line from stdin |
| `validates` | `console() Boolean` | Check if stdin is a terminal |

```prove
InputOutput outputs console, inputs console

outputs greet()
from
    InputOutput.console("What is your name?")
    name as String = InputOutput.console()
    InputOutput.console(f"Hello, {name}!")
```

### File Channel

Read, write, and check files. File operations are failable — use `!` to propagate errors.

| Verb | Signature | Description |
|------|-----------|-------------|
| `inputs` | `file(path String) String!` | Read file contents |
| `outputs` | `file(path String, content String)!` | Write file contents |
| `validates` | `file(path String) Boolean` | Check if file exists |

```prove
InputOutput inputs file, outputs file, validates file

inputs load_config(path String) String!
from
    InputOutput.file(path)!
```

### System Channel

Execute system commands and exit with a status code. Types: `ProcessResult` (binary), `ExitCode` (binary).

| Verb | Signature | Description |
|------|-----------|-------------|
| `inputs` | `system(cmd String, args List<String>) ProcessResult` | Run a command |
| `outputs` | `system(code Integer)` | Exit with status code |
| `validates` | `system(cmd String) Boolean` | Check if command exists |

### Dir Channel

List and create directories. Type: `DirEntry` (binary).

| Verb | Signature | Description |
|------|-----------|-------------|
| `inputs` | `dir(path String) List<DirEntry>` | List directory contents |
| `outputs` | `dir(path String)!` | Create a directory |
| `validates` | `dir(path String) Boolean` | Check if directory exists |

### Process Channel

Access command-line arguments.

| Verb | Signature | Description |
|------|-----------|-------------|
| `inputs` | `process() List<String>` | Get command-line arguments |
| `validates` | `process(value String) Boolean` | Check if argument is present |

---

## Parse

**Module:** `Parse` — encoding and decoding of structured data formats.

Parse uses a universal `Value` type (binary) that represents any parsed value. The same two-function pattern applies to each format: `creates` to decode, `reads` to encode.

### Formats

| Verb | Signature | Description |
|------|-----------|-------------|
| `creates` | `toml(source String) Result<Value, String>` | Decode TOML to Value |
| `reads` | `toml(value Value) String` | Encode Value to TOML |
| `creates` | `json(source String) Result<Value, String>` | Decode JSON to Value |
| `reads` | `json(value Value) String` | Encode Value to JSON |

### Value Accessors

Extract typed data from a `Value`. Each accessor has a corresponding validator.

| Verb | Signature | Description |
|------|-----------|-------------|
| `reads` | `tag(v Value) String` | Get the type tag (`"string"`, `"number"`, etc.) |
| `reads` | `text(v Value) String` | Extract string content |
| `reads` | `number(v Value) Integer` | Extract integer content |
| `reads` | `decimal(v Value) Float` | Extract floating-point content |
| `reads` | `bool(v Value) Boolean` | Extract boolean content |
| `reads` | `array(v Value) List<Value>` | Extract array content |
| `reads` | `object(v Value) Table<Value>` | Extract object/table content |

### Value Validators

| Verb | Signature | Description |
|------|-----------|-------------|
| `validates` | `text(v Value) Boolean` | Check if Value is a string |
| `validates` | `number(v Value) Boolean` | Check if Value is an integer |
| `validates` | `decimal(v Value) Boolean` | Check if Value is a float |
| `validates` | `bool(v Value) Boolean` | Check if Value is a boolean |
| `validates` | `array(v Value) Boolean` | Check if Value is an array |
| `validates` | `object(v Value) Boolean` | Check if Value is an object/table |
| `validates` | `null(v Value) Boolean` | Check if Value is null |

```prove
Parse creates toml, reads text object, types Value
Table reads keys get, types Table

main() Result<Unit, Error>!
from
    source as String = InputOutput.file("config.toml")!
    doc as Value = Parse.toml(source)!
    root as Table<Value> = Parse.object(doc)
    names as List<String> = Table.keys(root)
    InputOutput.console("Keys: " + join(names, ", "))
```

---

## Module Summary

| Version | Module | Status | Purpose |
|---------|--------|--------|---------|
| v0.6 | **Character** | Complete | Character classification (`alpha`, `digit`, `space`, etc.) and string-to-char access |
| v0.6 | **Text** | Complete | String operations (`slice`, `contains`, `split`, `join`, `trim`, `replace`) and `Builder` for efficient string construction |
| v0.6 | **Table** | Complete | Hash map `Table<V>` with `creates new`, `reads get`, `transforms add`, `validates has` |
| v0.7 | **InputOutput** (ext) | Complete | New channels: `system`, `dir`, `process` with `validates` verbs for existence checks |
| v0.7 | **Parse** | Complete | Format codecs for TOML and JSON with `Value` type and accessors |
