---
title: Parse, Format & Pattern - Prove Standard Library
description: Parse data formats, Format strings and numbers, and Pattern regex matching in the Prove standard library.
keywords: Prove Parse, Prove Format, Prove Pattern, JSON, TOML, regex, formatting
---

# Parse, Format & Pattern

## Parse

**Module:** `Parse` — encoding and decoding of structured data formats.

Parse uses a universal `Value` type (binary) that represents any parsed value. The same two-function pattern applies to each format: `creates` to decode, `reads` to encode, `validates` to check syntax. Supported formats: JSON, TOML, URL, Base64, CSV.

### Value Construction

| Verb | Signature | Description |
|------|-----------|-------------|
| `creates` | `value(source Value) Value` | Wrap any value as a Value |
| `validates` | `value(source Value)` | True if source can be wrapped as a Value |

### Formats

| Verb | Signature | Description |
|------|-----------|-------------|
| `creates` | `json(source String) Result<Value, String>` | Decode JSON to Value |
| `reads` | `json(value Value) String` | Encode Value to JSON |
| `validates` | `json(source String)` | True if source is valid JSON |
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
