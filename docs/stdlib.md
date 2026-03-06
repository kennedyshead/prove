---
title: Standard Library - Prove Programming Language
description: Complete reference for the Prove standard library including List, Option, Result, Text, String, and more.
keywords: Prove stdlib, standard library, List, Option, Result, Text, String
---

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
| `matches` | Algebraic dispatch (first param must be algebraic) | `matches area(s Shape) Decimal` |

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

## Character

**Module:** `Character` — character classification and string-to-character access.

All classification functions take a single `Character` and return `Boolean`.

### Classification

| Verb | Signature | Description |
|------|-----------|-------------|
| `validates` | `alpha(c Character)` | True if alphabetic (a–z, A–Z) |
| `validates` | `digit(c Character)` | True if numeric digit (0–9) |
| `validates` | `alnum(c Character)` | True if alphanumeric |
| `validates` | `upper(c Character)` | True if uppercase letter |
| `validates` | `lower(c Character)` | True if lowercase letter |
| `validates` | `space(c Character)` | True if whitespace |

### Access

| Verb | Signature | Description |
|------|-----------|-------------|
| `reads` | `at(s String, i Integer) Character` | Character at index (0-based, bounds-checked) |

```prove
Character validates alpha digit space, reads at

validates is_identifier_start(c Character)
from
    Character.alpha(c)
```

---

## Text

**Module:** `Text` — string operations and construction.

Defines a binary `Builder` type for efficient incremental string building.

### Query

| Verb | Signature | Description |
|------|-----------|-------------|
| `reads` | `length(s String) Integer` | Number of bytes in string |
| `reads` | `index(s String, sub String) Option<Integer>` | Find position of substring |

### Validation

| Verb | Signature | Description |
|------|-----------|-------------|
| `validates` | `starts(s String, prefix String)` | True if string begins with prefix |
| `validates` | `ends(s String, suffix String)` | True if string ends with suffix |
| `validates` | `contains(s String, sub String)` | True if substring is present |

### Transform

| Verb | Signature | Description |
|------|-----------|-------------|
| `transforms` | `slice(s String, start Integer, end Integer) String` | Extract substring [start, end) |
| `transforms` | `split(s String, sep String) List<String>` | Split by delimiter |
| `transforms` | `join(parts List<String>, sep String) String` | Join strings with separator |
| `transforms` | `trim(s String) String` | Remove leading and trailing whitespace |
| `transforms` | `lower(s String) String` | Convert to lowercase |
| `transforms` | `upper(s String) String` | Convert to uppercase |
| `transforms` | `replace(s String, old String, new String) String` | Replace all occurrences |
| `transforms` | `repeat(s String, n Integer) String` | Repeat string n times |

### Builder

The `Builder` type allows efficient incremental string construction.

| Verb | Signature | Description |
|------|-----------|-------------|
| `creates` | `builder() Builder` | Create an empty builder |
| `transforms` | `string(b Builder, s String) Builder` | Append a string |
| `transforms` | `char(b Builder, c Character) Builder` | Append a character |
| `reads` | `build(b Builder) String` | Finalize to string |
| `reads` | `length(b Builder) Integer` | Current builder length |

```prove
Text reads length index, validates contains starts, transforms split join trim replace
Text creates builder, transforms string, reads build

reads word_count(s String) Integer
from
    parts as List<String> = Text.split(Text.trim(s), " ")
    Text.length(parts)
```

---

## Table

**Module:** `Table` — hash map from `String` keys to generic values.

Defines two binary types: `V` (generic value) and `Table<V>` (the hash map).

| Verb | Signature | Description |
|------|-----------|-------------|
| `creates` | `new() Table<V>` | Create an empty table |
| `validates` | `has(key String, table Table<V>)` | True if key exists |
| `transforms` | `add(key String, value V, table Table<V>) Table<V>` | Insert or update a key-value pair |
| `reads` | `get(key String, table Table<V>) Option<V>` | Look up value by key |
| `transforms` | `remove(key String, table Table<V>) Table<V>` | Delete a key from the table |
| `reads` | `keys(table Table<V>) List<String>` | Get all keys |
| `reads` | `values(table Table<V>) List<V>` | Get all values |
| `reads` | `length(table Table<V>) Integer` | Number of entries |

```prove
Table creates new, validates has, transforms add, reads get keys

reads lookup(name String, db Table<String>) String
from
    Error.unwrap_or(Table.get(name, db), "unknown")
```

---

## InputOutput

**Module:** `InputOutput` — handles IO operations.

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

Read, write, and check files. File operations are failable — use `!` to propagate errors.

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

Execute system commands and exit with a status code. Types: `ProcessResult` (binary), `ExitCode` (binary).

| Verb | Signature | Description |
|------|-----------|-------------|
| `inputs` | `system(cmd String, args List<String>) ProcessResult` | Run a command |
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

## Parse

**Module:** `Parse` — encoding and decoding of structured data formats.

Parse uses a universal `Value` type (binary) that represents any parsed value. The same two-function pattern applies to each format: `creates` to decode, `reads` to encode, `validates` to check syntax.

### Value Construction

| Verb | Signature | Description |
|------|-----------|-------------|
| `creates` | `value(source V) Value` | Wrap any value as a Value |
| `validates` | `value(source V)` | True if source can be wrapped as a Value |

### Formats

| Verb | Signature | Description |
|------|-----------|-------------|
| `creates` | `toml(source String) Result<Value, String>` | Decode TOML to Value |
| `reads` | `toml(value Value) String` | Encode Value to TOML |
| `validates` | `toml(source String)` | True if source is valid TOML |
| `creates` | `json(source String) Result<Value, String>` | Decode JSON to Value |
| `reads` | `json(value Value) String` | Encode Value to JSON |
| `validates` | `json(source String)` | True if source is valid JSON |

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

## Math

**Module:** `Math` — numeric operations on `Integer` and `Float`.

Functions with Integer/Float overloads dispatch based on argument type.

### Absolute Value, Min, Max

| Verb | Signature | Description |
|------|-----------|-------------|
| `reads` | `abs(n Integer) Integer` | Absolute value of integer |
| `reads` | `abs(x Float) Float` | Absolute value of float |
| `reads` | `min(a Integer, b Integer) Integer` | Smaller of two integers |
| `reads` | `min(a Float, b Float) Float` | Smaller of two floats |
| `reads` | `max(a Integer, b Integer) Integer` | Larger of two integers |
| `reads` | `max(a Float, b Float) Float` | Larger of two floats |

### Clamp

| Verb | Signature | Description |
|------|-----------|-------------|
| `transforms` | `clamp(val Integer, lo Integer, hi Integer) Integer` | Constrain integer to range |
| `transforms` | `clamp(val Float, lo Float, hi Float) Float` | Constrain float to range |

### Float Operations

| Verb | Signature | Description |
|------|-----------|-------------|
| `reads` | `sqrt(x Float) Float` | Square root |
| `reads` | `pow(base Float, exp Float) Float` | Exponentiation |
| `reads` | `floor(x Float) Integer` | Round down to integer |
| `reads` | `ceil(x Float) Integer` | Round up to integer |
| `reads` | `round(x Float) Integer` | Round to nearest integer |
| `reads` | `log(x Float) Float` | Natural logarithm |

```prove
Math reads abs min max sqrt floor

reads distance(x Integer, y Integer) Integer
from
    Math.abs(Math.min(x, y) - Math.max(x, y))
```

> **Note:** Math functions like `sqrt` and `floor` require `Float` arguments. Use the `f` suffix on literals: `16.0f` not `16.0` (which is `Decimal`).

---

## Types

**Module:** `Types` — type validation and conversion between primitive types.

The function name is the *target type*. Failable conversions from strings return `Result`. Validators check that a value is of the expected type.

### Type Validators

| Verb | Signature | Description |
|------|-----------|-------------|
| `validates` | `string(s String)` | True if value is a string |
| `validates` | `integer(n Integer)` | True if value is an integer |
| `validates` | `float(n Float)` | True if value is a float |
| `validates` | `decimal(n Float)` | True if value is a decimal |
| `validates` | `boolean(b Boolean)` | True if value is a boolean |
| `validates` | `character(c Character)` | True if value is a character |

### Integer Conversions

| Verb | Signature | Description |
|------|-----------|-------------|
| `creates` | `integer(s String) Result<Integer, String>` | Parse string to integer |
| `creates` | `integer(x Float) Integer` | Truncate float to integer |

### Float Conversions

| Verb | Signature | Description |
|------|-----------|-------------|
| `creates` | `float(s String) Result<Float, String>` | Parse string to float |
| `creates` | `float(n Integer) Float` | Promote integer to float |

### String Conversions

| Verb | Signature | Description |
|------|-----------|-------------|
| `reads` | `string(n Integer) String` | Integer to string |
| `reads` | `string(x Float) String` | Float to string |
| `reads` | `string(b Boolean) String` | Boolean to `"true"` or `"false"` |

### Character Conversions

| Verb | Signature | Description |
|------|-----------|-------------|
| `reads` | `code(c Character) Integer` | Character to code point |
| `creates` | `character(n Integer) Character` | Code point to character |

```prove
Types creates integer float, reads string code, validates integer string

reads format_pair(label String, n Integer) String
from
    label + ": " + Types.string(n)
```

---

## List

**Module:** `List` — operations on the built-in `List<T>` type.

Generic functions work on any `List<T>`. Some operations (contains, index, sort)
require concrete element types and have overloads for `List<Integer>` and
`List<String>`.

### Query

| Verb | Signature | Description |
|------|-----------|-------------|
| `reads` | `length(items List<T>) Integer` | Number of elements |
| `reads` | `first(items List<T>) Option<T>` | First element, or None |
| `reads` | `last(items List<T>) Option<T>` | Last element, or None |
| `validates` | `empty(items List<T>)` | True if list has no elements |

### Search

| Verb | Signature | Description |
|------|-----------|-------------|
| `validates` | `contains(items List<Integer>, value Integer)` | Check if integer is in list |
| `validates` | `contains(items List<String>, value String)` | Check if string is in list |
| `reads` | `index(items List<Integer>, value Integer) Option<Integer>` | Find position of integer |
| `reads` | `index(items List<String>, value String) Option<Integer>` | Find position of string |

### Transform

| Verb | Signature | Description |
|------|-----------|-------------|
| `transforms` | `slice(items List<T>, start Integer, end Integer) List<T>` | Sub-list from start to end |
| `transforms` | `reverse(items List<T>) List<T>` | Reverse element order |
| `transforms` | `sort(items List<Integer>) List<Integer>` | Sort integers ascending |
| `transforms` | `sort(items List<String>) List<String>` | Sort strings lexicographically |

### Create

| Verb | Signature | Description |
|------|-----------|-------------|
| `creates` | `range(start Integer, end Integer) List<Integer>` | Integer sequence [start, end) |

```prove
List reads length first, transforms sort reverse, creates range

reads top_three() List<Integer>
from
    nums as List<Integer> = List.range(1, 100)
    List.reverse(List.sort(nums))
```

---

## Format

**Module:** `Format` — string formatting and numeric display.

### Padding

| Verb | Signature | Description |
|------|-----------|-------------|
| `transforms` | `pad_left(s String, width Integer, fill Character) String` | Left-pad to width |
| `transforms` | `pad_right(s String, width Integer, fill Character) String` | Right-pad to width |
| `transforms` | `center(s String, width Integer, fill Character) String` | Center within width |

### Number Formatting

| Verb | Signature | Description |
|------|-----------|-------------|
| `transforms` | `hex(n Integer) String` | Integer to hexadecimal string |
| `transforms` | `bin(n Integer) String` | Integer to binary string |
| `transforms` | `octal(n Integer) String` | Integer to octal string |
| `transforms` | `decimal(x Float, places Integer) String` | Float with fixed decimal places |

```prove
Format transforms pad_left hex decimal

reads format_address(addr Integer) String
from
    Format.pad_left(Format.hex(addr), 8, '0')
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

---

## Pattern

**Module:** `Pattern` — regular expression matching via POSIX regex.

Defines a binary `Match` type that holds the matched text, start offset, and
end offset.

### Matching

| Verb | Signature | Description |
|------|-----------|-------------|
| `validates` | `test(text String, pattern String)` | True if text fully matches pattern |
| `reads` | `search(text String, pattern String) Option<Match>` | Find first match |
| `reads` | `find_all(text String, pattern String) List<Match>` | Find all matches |

### Transform

| Verb | Signature | Description |
|------|-----------|-------------|
| `transforms` | `replace(text String, pattern String, replacement String) String` | Replace first match |
| `transforms` | `split(text String, pattern String) List<String>` | Split on pattern |

### Match Accessors

| Verb | Signature | Description |
|------|-----------|-------------|
| `reads` | `text(m Match) String` | Matched text |
| `reads` | `start(m Match) Integer` | Start offset in source string |
| `reads` | `end(m Match) Integer` | End offset in source string |

```prove
Pattern validates test, transforms replace, types Match

reads sanitize(input String) String
requires
    test(input, "[a-zA-Z0-9 ]+")
from
    Pattern.replace(input, " +", " ")
```

---

## Error

**Module:** `Error` — utilities for `Result<T, E>` and `Option<T>`.

Validators for inspecting Result and Option values, plus `unwrap_or` for
providing defaults.

### Result Validators

| Verb | Signature | Description |
|------|-----------|-------------|
| `validates` | `ok(r Result<T, E>)` | True if Result is Ok |
| `validates` | `err(r Result<T, E>)` | True if Result is Err |

### Option Validators

| Verb | Signature | Description |
|------|-----------|-------------|
| `validates` | `some(o Option<T>)` | True if Option has a value |
| `validates` | `none(o Option<T>)` | True if Option is empty |

### Unwrap with Default

| Verb | Signature | Description |
|------|-----------|-------------|
| `reads` | `unwrap_or(o Option<Integer>, default Integer) Integer` | Extract integer or use default |
| `reads` | `unwrap_or(o Option<String>, default String) String` | Extract string or use default |

```prove
Error validates ok some, reads unwrap_or

reads safe_first(items List<Integer>) Integer
from
    Error.unwrap_or(List.first(items), 0)
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
| v0.9.6 | **Math** | Complete | Numeric functions: abs, min, max, floor, ceil, pow, clamp, sqrt, log |
| v0.9.6 | **Types** | Complete | Type validation and conversion: String ↔ Integer, String ↔ Float, Character ↔ Integer |
| v0.9.6 | **List** | Complete | Operations on `List<T>`: length, first, last, contains, sort, reverse, range |
| v0.9.7 | **Path** | Complete | File path manipulation: join, parent, stem, extension, normalize |
| v0.9.7 | **Pattern** | Complete | Regex operations: test, search, replace, split with `Match` type |
| v0.9.8 | **Format** | Complete | String formatting: pad, center, number formatting (hex, bin, octal) |
| v0.9.8 | **Error** | Complete | Result/Option utilities: ok, err, some, none, unwrap_or |
