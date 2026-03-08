---
title: Standard Library - Prove Programming Language
description: Complete reference for the Prove standard library — 16 modules including Text, Parse, Math, Time, Hash, Bytes, Random, and more.
keywords: Prove stdlib, standard library, List, Text, Parse, Math, Time, Hash, Bytes, Random
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
| `validates` | Check a condition, return Boolean | `validates has(key String, table Table<Value>)` |
| `reads` | Extract or query data without changing it | `reads get(key String, table Table<Value>) Option<Value>` |
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
| `reads` | `at(string String, index Integer) Character` | Character at index (0-based, bounds-checked) |

```prove
Character validates alpha digit space, reads at

validates is_identifier_start(c Character)
from
    Character.alpha(c)
```

---

## Text

**Module:** `Text` — string operations and construction.

Defines a binary `StringBuilder` type for efficient incremental string building.

### Query

| Verb | Signature | Description |
|------|-----------|-------------|
| `reads` | `length(s String) Integer` | Number of bytes in string |
| `reads` | `index(text String, substring String) Option<Integer>` | Find position of substring |

### Validation

| Verb | Signature | Description |
|------|-----------|-------------|
| `validates` | `starts(s String, prefix String)` | True if string begins with prefix |
| `validates` | `ends(s String, suffix String)` | True if string ends with suffix |
| `validates` | `contains(s String, sub String)` | True if substring is present |

### Transform

| Verb | Signature | Description |
|------|-----------|-------------|
| `transforms` | `slice(text String, start Integer, end Integer) String` | Extract substring [start, end) |
| `transforms` | `split(text String, separator String) List<String>` | Split by delimiter |
| `transforms` | `join(parts List<String>, separator String) String` | Join strings with separator |
| `transforms` | `trim(text String) String` | Remove leading and trailing whitespace |
| `transforms` | `lower(text String) String` | Convert to lowercase |
| `transforms` | `upper(text String) String` | Convert to uppercase |
| `transforms` | `replace(text String, old String, new String) String` | Replace all occurrences |
| `transforms` | `repeat(text String, count Integer) String` | Repeat string count times |

### Builder

The `StringBuilder` type allows efficient incremental string construction.

| Verb | Signature | Description |
|------|-----------|-------------|
| `creates` | `builder() StringBuilder:[Mutable]` | Create an empty builder |
| `transforms` | `string(builder StringBuilder:[Mutable], text String) StringBuilder:[Mutable]` | Append a string |
| `transforms` | `char(builder StringBuilder:[Mutable], character Character) StringBuilder:[Mutable]` | Append a character |
| `reads` | `build(builder StringBuilder:[Mutable]) String` | Finalize to string |
| `reads` | `length(builder StringBuilder:[Mutable]) Integer` | Current builder length |

```prove
Text reads length index, validates contains starts, transforms split join trim replace
Text creates builder, transforms string, reads build

reads word_count(text String) Integer
from
    parts as List<String> = Text.split(Text.trim(text), " ")
    Text.length(parts)
```

---

## Table

**Module:** `Table` — hash map from `String` keys to values.

Defines a binary type: `Table<Value>` (the hash map).

| Verb | Signature | Description |
|------|-----------|-------------|
| `creates` | `new() Table<Value>` | Create an empty table |
| `validates` | `has(key String, table Table<Value>)` | True if key exists |
| `transforms` | `add(key String, value Value, table Table<Value>) Table<Value>` | Insert or update a key-value pair |
| `reads` | `get(key String, table Table<Value>) Option<Value>` | Look up value by key |
| `transforms` | `remove(key String, table Table<Value>) Table<Value>` | Delete a key from the table |
| `reads` | `keys(table Table<Value>) List<String>` | Get all keys |
| `reads` | `values(table Table<Value>) List<Value>` | Get all values |
| `reads` | `length(table Table<Value>) Integer` | Number of entries |

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

## Parse

**Module:** `Parse` — encoding and decoding of structured data formats.

Parse uses a universal `Value` type (binary) that represents any parsed value. The same two-function pattern applies to each format: `creates` to decode, `reads` to encode, `validates` to check syntax.

### Value Construction

| Verb | Signature | Description |
|------|-----------|-------------|
| `creates` | `value(source Value) Value` | Wrap any value as a Value |
| `validates` | `value(source Value)` | True if source can be wrapped as a Value |

### Formats

| Verb | Signature | Description |
|------|-----------|-------------|
| `creates` | `toml(source String) Result<Value, String>` | Decode TOML to Value |
| `reads` | `toml(value Value) String` | Encode Value to TOML |
| `validates` | `toml(source String)` | True if source is valid TOML |
| `validates` | `value(source Source)` | True if source can be wrapped as a Value |

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

### URL

Defines a binary `Url` type for parsed URL components.

| Verb | Signature | Description |
|------|-----------|-------------|
| `reads` | `url(raw String) Url` | Parse a URL string into components |
| `creates` | `url(scheme String, host String, path String) Url` | Construct a URL from parts |
| `validates` | `url(raw String)` | True if string is a valid URL |
| `transforms` | `url(source Url, params Table<Value>) Url` | Add query parameters to a URL |

### Base64

| Verb | Signature | Description |
|------|-----------|-------------|
| `reads` | `base64(encoded String) ByteArray` | Decode Base64 string to byte array |
| `creates` | `base64(data ByteArray) String` | Encode byte array as Base64 |
| `validates` | `base64(encoded String)` | True if string is valid Base64 |

### CSV

RFC 4180-compliant CSV parsing. Returns raw `List<List<String>>` — no type inference.

| Verb | Signature | Description |
|------|-----------|-------------|
| `creates` | `csv(source String) Result<List<List<String>>, String>` | Parse CSV string into rows of fields |
| `reads` | `csv(rows List<List<String>>) String` | Serialize rows of fields to CSV string |
| `validates` | `csv(source String)` | True if source is valid CSV |

```prove
Parse creates toml url, reads text object url, validates url base64, types Value Url
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
| `reads` | `min(first Integer, second Integer) Integer` | Smaller of two integers |
| `reads` | `min(first Float, second Float) Float` | Smaller of two floats |
| `reads` | `max(first Integer, second Integer) Integer` | Larger of two integers |
| `reads` | `max(first Float, second Float) Float` | Larger of two floats |

### Clamp

| Verb | Signature | Description |
|------|-----------|-------------|
| `transforms` | `clamp(value Integer, minimum Integer, maximum Integer) Integer` | Constrain integer to range |
| `transforms` | `clamp(value Float, minimum Float, maximum Float) Float` | Constrain float to range |

### Float Operations

| Verb | Signature | Description |
|------|-----------|-------------|
| `reads` | `sqrt(x Float) Float` | Square root |
| `reads` | `power(base Float, exponent Float) Float` | Exponentiation |
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
| `reads` | `code(character Character) Integer` | Character to code point |
| `creates` | `character(code Integer) Character` | Code point to character |

### Value Validators

| Verb | Signature | Description |
|------|-----------|-------------|
| `validates` | `text(value Value)` | Check if Value is text |
| `validates` | `number(value Value)` | Check if Value is a number |
| `validates` | `decimal(value Value)` | Check if Value is a decimal |
| `validates` | `bool(value Value)` | Check if Value is a boolean |
| `validates` | `array(value Value)` | Check if Value is an array |
| `validates` | `object(value Value)` | Check if Value is an object |
| `validates` | `null(value Value)` | Check if Value is null |

```prove
Types creates integer float, reads string code, validates integer string

reads format_pair(label String, n Integer) String
from
    label + ": " + Types.string(n)
```

---

## List

**Module:** `List` — operations on the built-in `List<Value>` type.

Some operations (contains, index, sort) require concrete element types and have
overloads for `List<Integer>` and `List<String>`.

### Query

| Verb | Signature | Description |
|------|-----------|-------------|
| `reads` | `length(items List<Value>) Integer` | Number of elements |
| `reads` | `first(items List<Value>) Option<Value>` | First element, or None |
| `reads` | `last(items List<Value>) Option<Value>` | Last element, or None |
| `validates` | `empty(items List<Value>)` | True if list has no elements |

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
| `transforms` | `slice(items List<Value>, start Integer, end Integer) List<Value>` | Sub-list from start to end |
| `transforms` | `reverse(items List<Value>) List<Value>` | Reverse element order |
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
| `transforms` | `pad_left(text String, width Integer, fill Character) String` | Left-pad to width |
| `transforms` | `pad_right(text String, width Integer, fill Character) String` | Right-pad to width |
| `transforms` | `center(text String, width Integer, fill Character) String` | Center within width |

### Number Formatting

| Verb | Signature | Description |
|------|-----------|-------------|
| `transforms` | `hex(number Integer) String` | Integer to hexadecimal string |
| `transforms` | `bin(number Integer) String` | Integer to binary string |
| `transforms` | `octal(number Integer) String` | Integer to octal string |
| `transforms` | `decimal(value Float, places Integer) String` | Float with fixed decimal places |

### Time & Date Formatting

Format time, date, datetime, and duration values using pattern strings.

Supported patterns: `"ISO8601"`, `"%Y-%m-%d"`, `"%H:%M:%S"`, `"%Y-%m-%d %H:%M:%S"`, `"%Hh %Mm %Ss"`, and other `strftime`-style patterns.

| Verb | Signature | Description |
|------|-----------|-------------|
| `transforms` | `time(time Time, pattern String) String` | Format a time as a string |
| `creates` | `time(source String, pattern String) Time` | Parse a string into a time |
| `validates` | `time(source String, pattern String)` | True if string matches time format |
| `transforms` | `date(date Date, pattern String) String` | Format a date as a string |
| `creates` | `date(source String, pattern String) Date` | Parse a string into a date |
| `validates` | `date(source String, pattern String)` | True if string matches date format |
| `transforms` | `datetime(datetime DateTime, pattern String) String` | Format a datetime as a string |
| `creates` | `datetime(source String, pattern String) DateTime` | Parse a string into a datetime |
| `validates` | `datetime(source String, pattern String)` | True if string matches datetime format |
| `transforms` | `duration(duration Duration, pattern String) String` | Format a duration as a string |
| `creates` | `duration(source String, pattern String) Duration` | Parse a string into a duration |

```prove
Format transforms pad_left hex decimal date, creates date
Time creates date, types Date

reads format_address(addr Integer) String
from
    Format.pad_left(Format.hex(addr), 8, '0')

reads format_date(date Date) String
from
    Format.date(date, "%Y-%m-%d")
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
| `reads` | `text(matched Match) String` | Matched text |
| `reads` | `start(matched Match) Integer` | Start offset in source string |
| `reads` | `end(matched Match) Integer` | End offset in source string |

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

**Module:** `Error` — utilities for `Result<Value, Error>` and `Option<Value>`.

Validators for inspecting Result and Option values, plus `unwrap_or` for
providing defaults.

### Result Validators

| Verb | Signature | Description |
|------|-----------|-------------|
| `validates` | `ok(result Result<Value, Error>)` | True if Result is Ok |
| `validates` | `err(result Result<Value, Error>)` | True if Result is Err |

### Option Validators

| Verb | Signature | Description |
|------|-----------|-------------|
| `validates` | `some(option Option<Value>)` | True if Option has a value |
| `validates` | `none(option Option<Value>)` | True if Option is empty |

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

## Random

**Module:** `Random` — random value generation.

All functions use the `inputs` verb because randomness requires external entropy — it is an IO operation.

### Generation

| Verb | Signature | Description |
|------|-----------|-------------|
| `inputs` | `integer() Integer` | Random integer |
| `inputs` | `integer(minimum Integer, maximum Integer) Integer` | Random integer within range (inclusive) |
| `inputs` | `decimal() Float` | Random decimal between 0.0 and 1.0 |
| `inputs` | `decimal(minimum Float, maximum Float) Float` | Random decimal within range |
| `inputs` | `boolean() Boolean` | Random boolean |

### Selection

| Verb | Signature | Description |
|------|-----------|-------------|
| `inputs` | `choice(items List<Integer>) Integer` | Pick a random element from integer list |
| `inputs` | `choice(items List<String>) String` | Pick a random element from string list |
| `inputs` | `shuffle(items List<Integer>) List<Integer>` | Randomly reorder integer list |
| `inputs` | `shuffle(items List<String>) List<String>` | Randomly reorder string list |

### Validation

| Verb | Signature | Description |
|------|-----------|-------------|
| `validates` | `integer(value Integer, minimum Integer, maximum Integer)` | True if value falls within range |

```prove
Random inputs integer boolean choice shuffle

inputs roll_dice(count Integer) List<Integer>
from
    results as List<Integer> = []
    repeat count
        results = results + [Random.integer(1, 6)]
    results
```

---

## Time

**Module:** `Time` — time representation, arithmetic, and calendar operations.

Defines six binary types: `Time` (epoch timestamp), `Duration` (time span), `Date` (calendar date), `Clock` (time of day), `DateTime` (date + time), and `Weekday` (day of week, 0=Monday through 6=Sunday).

Only `inputs time()` is an IO verb (reads the system clock). All other functions are pure.

### Time

| Verb | Signature | Description |
|------|-----------|-------------|
| `inputs` | `time() Time` | Get current time |
| `validates` | `time(time Time)` | True if time is in the past |

### Duration

| Verb | Signature | Description |
|------|-----------|-------------|
| `creates` | `duration(hours Integer, minutes Integer, seconds Integer) Duration` | Create duration from components |
| `reads` | `duration(duration Duration) Integer` | Total seconds in duration |
| `validates` | `duration(duration Duration)` | True if duration is positive |
| `transforms` | `duration(start Time, stop Time) Duration` | Compute difference between two times |

### Date

| Verb | Signature | Description |
|------|-----------|-------------|
| `reads` | `date(time Time) Date` | Extract date from a time |
| `creates` | `date(year Integer, month Integer, day Integer) Date` | Create date from components |
| `validates` | `date(year Integer, month Integer, day Integer)` | True if date components are valid |
| `transforms` | `date(date Date, days Integer) Date` | Add days to a date |

### DateTime

| Verb | Signature | Description |
|------|-----------|-------------|
| `reads` | `datetime(time Time) DateTime` | Extract datetime from a time |
| `creates` | `datetime(date Date, clock Clock) DateTime` | Create datetime from date and clock |
| `validates` | `datetime(datetime DateTime)` | True if datetime is valid |
| `transforms` | `datetime(datetime DateTime) Time` | Convert datetime to timestamp |

### Calendar

| Verb | Signature | Description |
|------|-----------|-------------|
| `reads` | `days(year Integer, month Integer) Integer` | Number of days in a month |
| `validates` | `days(year Integer)` | True if year is a leap year |
| `reads` | `weekday(date Date) Weekday` | Get weekday from a date |
| `validates` | `weekday(date Date)` | True if date falls on a weekend |

### Clock

| Verb | Signature | Description |
|------|-----------|-------------|
| `reads` | `clock(time Time) Clock` | Extract clock from a time |
| `creates` | `clock(hour Integer, minute Integer, second Integer) Clock` | Create clock from components |
| `validates` | `clock(hour Integer, minute Integer, second Integer)` | True if clock components are valid |

```prove
Time inputs time, creates duration date clock, reads days weekday, types Time Duration Date Clock

reads elapsed_days(start Time, stop Time) Integer
from
    span as Duration = Time.duration(start, stop)
    Time.duration(span) / 86400
```

---

## Bytes

**Module:** `Bytes` — byte sequence manipulation.

Defines a binary type: `ByteArray` (a sequence of bytes).

### Construction

| Verb | Signature | Description |
|------|-----------|-------------|
| `creates` | `byte(values List<Integer>) ByteArray` | Create byte array from list of integers |
| `validates` | `byte(data ByteArray)` | True if byte array is empty |

### Slicing

| Verb | Signature | Description |
|------|-----------|-------------|
| `reads` | `slice(data ByteArray, start Integer, length Integer) ByteArray` | Extract a sub-range of bytes |
| `creates` | `slice(first ByteArray, second ByteArray) ByteArray` | Concatenate two byte arrays |

### Hex Encoding

| Verb | Signature | Description |
|------|-----------|-------------|
| `reads` | `hex(data ByteArray) String` | Encode byte array as hex string |
| `creates` | `hex(source String) ByteArray` | Decode hex string to byte array |
| `validates` | `hex(source String)` | True if string is valid hex |

### Access

| Verb | Signature | Description |
|------|-----------|-------------|
| `reads` | `at(data ByteArray, index Integer) Integer` | Read byte at index |
| `validates` | `at(data ByteArray, index Integer)` | True if index is within bounds |

```prove
Bytes creates byte hex, reads slice hex at, validates hex

reads first_byte_hex(data ByteArray) String
from
    single as ByteArray = Bytes.slice(data, 0, 1)
    Bytes.hex(single)
```

---

## Hash

**Module:** `Hash` — cryptographic hashing and verification.

Defines a binary type: `Algorithm` (hash algorithm selector).

No external crypto dependency — all algorithms are implemented in the runtime.

### SHA-256

| Verb | Signature | Description |
|------|-----------|-------------|
| `creates` | `sha256(data ByteArray) ByteArray` | Hash bytes to SHA-256 digest |
| `reads` | `sha256(data String) String` | Hash string to SHA-256 hex string |
| `validates` | `sha256(data ByteArray, expected ByteArray)` | Verify data matches expected SHA-256 hash |

### SHA-512

| Verb | Signature | Description |
|------|-----------|-------------|
| `creates` | `sha512(data ByteArray) ByteArray` | Hash bytes to SHA-512 digest |
| `reads` | `sha512(data String) String` | Hash string to SHA-512 hex string |
| `validates` | `sha512(data ByteArray, expected ByteArray)` | Verify data matches expected SHA-512 hash |

### BLAKE3

| Verb | Signature | Description |
|------|-----------|-------------|
| `creates` | `blake3(data ByteArray) ByteArray` | Hash bytes to BLAKE3 digest |
| `reads` | `blake3(data String) String` | Hash string to BLAKE3 hex string |
| `validates` | `blake3(data ByteArray, expected ByteArray)` | Verify data matches expected BLAKE3 hash |

### HMAC

| Verb | Signature | Description |
|------|-----------|-------------|
| `creates` | `hmac(data ByteArray, key ByteArray) ByteArray` | Create HMAC-SHA256 signature |
| `validates` | `hmac(data ByteArray, key ByteArray, signature ByteArray)` | Verify HMAC-SHA256 signature |

```prove
Hash reads sha256, creates sha256 hmac, validates hmac, types ByteArray
Bytes creates byte

reads checksum(content String) String
from
    Hash.sha256(content)
```

---

## Module Summary

| Version | Module | Status | Purpose |
|---------|--------|--------|---------|
| v0.6 | **Character** | Complete | Character classification (`alpha`, `digit`, `space`, etc.) and string-to-char access |
| v0.6 | **Text** | Complete | String operations (`slice`, `contains`, `split`, `join`, `trim`, `replace`) and `Builder` for efficient string construction |
| v0.6 | **Table** | Complete | Hash map `Table<Value>` with `creates new`, `reads get`, `transforms add`, `validates has` |
| v0.7 | **InputOutput** (ext) | Complete | Channels: `console`, `file`, `system`, `dir`, `process` with `validates` verbs |
| v0.7 | **Parse** (ext) | Complete | TOML, JSON, URL, and Base64 codecs with `Value` and `Url` types |
| v0.9.6 | **Math** | Complete | Numeric functions: abs, min, max, floor, ceil, pow, clamp, sqrt, log |
| v0.9.6 | **Types** | Complete | Type validation and conversion: String ↔ Integer, String ↔ Float, Character ↔ Integer |
| v0.9.6 | **List** | Complete | Operations on `List<Value>`: length, first, last, contains, sort, reverse, range |
| v0.9.7 | **Path** | Complete | File path manipulation: join, parent, stem, extension, normalize |
| v0.9.7 | **Pattern** | Complete | Regex operations: test, search, replace, split with `Match` type |
| v0.9.8 | **Format** (ext) | Complete | String/number formatting (pad, hex, bin) and time/date formatting |
| v0.9.8 | **Error** | Complete | Result/Option utilities: ok, err, some, none, unwrap_or |
| v0.9.9 | **Bytes** | Complete | Byte sequence manipulation: create, slice, hex encode/decode, index access |
| v0.9.9 | **Hash** | Complete | Cryptographic hashing: SHA-256, SHA-512, BLAKE3, HMAC-SHA256 |
| v0.9.9 | **Random** | Complete | Random value generation: integer, decimal, boolean, choice, shuffle |
| v0.9.9 | **Time** | Complete | Time, Date, Clock, Duration, DateTime, Weekday with calendar operations |
