---
title: InputOutput & Path - Prove Standard Library
description: InputOutput channels and Path manipulation in the Prove standard library.
keywords: Prove InputOutput, Prove Path, file IO, console IO, path manipulation
---

# InputOutput & Path

## InputOutput

**Module:** `InputOutput` — handles IO operations.

All InputOutput functions use IO verbs (`inputs`, `outputs`, `validates`) — see [Functions & Verbs](../functions.md#io-and-fallibility) for how IO and fallibility work together.

### Console Channel

Console input, output, and availability check.

| Verb | Signature | Description |
|------|-----------|-------------|
| `outputs` | `console(text String)` | Print text to stdout |
| `inputs` | `console() String` | Read a line from stdin |
| `validates` | `console()` | Check if stdin is a terminal |

```prove
InputOutput outputs console, inputs console

outputs greet()
from
    InputOutput.console("What is your name?")
    name as String = InputOutput.console()
    InputOutput.console(f"Hello, {name}!")
```

### File Channel

Read, write, and check files. File operations are failable — use [`!`](../types.md#error-propagation) to propagate errors.

| Verb | Signature | Description |
|------|-----------|-------------|
| `inputs` | `file(path String) Result<String, Error>!` | Read file contents |
| `outputs` | `file(path String, content String) Result<Unit, Error>!` | Write file contents |
| `validates` | `file(path String)` | Check if file exists |

```prove
InputOutput inputs file, outputs file, validates file

inputs load_config(path String) String!
from
    InputOutput.file(path)!
```

### System Channel

Execute system commands and exit with a status code. Type: `ProcessResult` (binary).

| Verb | Signature | Description |
|------|-----------|-------------|
| `inputs` | `system(command String, arguments List<String>) ProcessResult` | Run a command |
| `outputs` | `system(code Integer)` | Exit with status code |
| `validates` | `system(cmd String)` | Check if command exists |

### Dir Channel

List and create directories. Type: `DirEntry` (binary).

| Verb | Signature | Description |
|------|-----------|-------------|
| `inputs` | `dir(path String) List<DirEntry>` | List directory contents |
| `outputs` | `dir(path String) Result<Unit, Error>!` | Create a directory |
| `validates` | `dir(path String)` | Check if directory exists |

### Process Channel

Access command-line arguments.

| Verb | Signature | Description |
|------|-----------|-------------|
| `inputs` | `process() List<String>` | Get command-line arguments |
| `validates` | `process(value String)` | Check if argument is present |

---

## Path

**Module:** `Path` — file path manipulation (pure string operations).

All functions operate on path strings using `/` as the separator. No filesystem
access — these are pure string transformations.

| Verb | Signature | Description |
|------|-----------|-------------|
| `transforms` | `join(base String, part String) String` | Join two path segments |
| `reads` | `parent(path String) String` | Directory containing the path |
| `reads` | `name(path String) String` | Final component (file name) |
| `reads` | `stem(path String) String` | File name without extension |
| `reads` | `extension(path String) String` | File extension (without dot) |
| `validates` | `absolute(path String)` | True if path starts with `/` |
| `transforms` | `normalize(path String) String` | Resolve `.` and `..` segments |

```prove
Path reads parent stem extension

reads describe(path String) String
from
    f"{Path.stem(path)}.{Path.extension(path)} in {Path.parent(path)}"
```
