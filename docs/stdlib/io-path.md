---
title: System & Path - Prove Standard Library
description: System channels and Path manipulation in the Prove standard library.
keywords: Prove System, Prove Path, file IO, console IO, path manipulation
---

# System & Path

## System

**Module:** `System` — handles IO operations across console, file, system, dir, and process channels.

All System functions use IO verbs (`inputs`, `outputs`, `validates`) — see [Functions & Verbs](../functions.md) for how IO and fallibility work together.

### Console Channel

Console input, output, and availability check.

| Verb | Signature | Description |
|------|-----------|-------------|
| `outputs` | `console(text String)` | Print text to stdout |
| `inputs` | `console() String` | Read a line from stdin (strips `\r\n`) |
| `inputs` | `console(count Integer) Bytes` | Read exactly `count` bytes from stdin |
| `validates` | `console()` | Check if stdin is a terminal |

```prove
System outputs console inputs console

outputs greet()
from
    System.console("What is your name?")
    name as String = System.console()
    System.console(f"Hello, {name}!")
```

The two-verb pair mirrors the LSP stdio transport pattern: use `console() String` for reading header lines and `console(count Integer) Bytes` for reading the raw body.

```prove
System inputs console

inputs read_lsp_message() Bytes
from
    header as String = System.console()          // "Content-Length: 512"
    length as Integer = Parse.integer(header[16..])
    System.console(length)                       // exactly 512 raw bytes
```

### File Channel

Read, write, and check files. File operations are failable — use [`!`](../types.md#error-propagation) to propagate errors.

| Verb | Signature | Description |
|------|-----------|-------------|
| `inputs` | `file(path String) Result<String, Error>!` | Read file contents |
| `outputs` | `file(path String, content String) Result<Unit, Error>!` | Write file contents |
| `validates` | `file(path String)` | Check if file exists |

```prove
System inputs file outputs file validates file

inputs load_config(path String) String!
from
    System.file(path)!
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

### File Streaming Channel

Open file handles for line-by-line streaming — for use with the [`streams` verb](../async.md). Type: `File` (binary handle).

| Verb | Signature | Description |
|------|-----------|-------------|
| `creates` | `reader(path String) File!` | Open a file for reading (line by line) |
| `inputs` | `line(handle File) String` | Read the next line from an open file; loop exits on EOF |
| `creates` | `writer(path String) File!` | Open a file for appending |
| `outputs` | `line(handle File, data String)` | Write a line to an open file |
| `outputs` | `close(handle File)` | Close an open file handle |

```prove
System outputs console close line inputs line creates reader writer types File

type ChunkIO is Streaming(handle File)
  | Exit

/// Read a file line by line.
streams read_file(state ChunkIO)
from
    Exit              => state
    Streaming(handle) =>
        data as String = line(handle)
        console(f"line: {data}")

main() Result<Unit, Error>!
from
    rh as File = reader("/tmp/data.txt")!
    read_file(Streaming(rh))
    close(rh)
```

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
