---
title: Parse, Format & Pattern - Prove Standard Library
description: Parse data formats, Format strings and numbers, and Pattern regex matching in the Prove standard library.
keywords: Prove Parse, Prove Format, Prove Pattern, JSON, TOML, regex, formatting
---

# Parse, Format & Pattern

## Parse

**Module:** `Parse` — encoding and decoding of structured data formats, and generic tokenization.

Parse uses phantom-typed `Value<T>` types to track the format of parsed data. Each format has a phantom marker type (`Json`, `Toml`, `Csv`, `Tree`) that tags the Value at the type level while sharing the same runtime representation. The pattern: `creates` to decode (returns `Value<T>`), `creates` to tag (wraps plain `Value` as `Value<T>`), `validates` to check syntax. Serialization back to strings lives in the [Types module](math-types.md#format-serialization) as `creates string`.

Parse also provides a generic `Token` and `Rule` system for building custom tokenizers. Define rules as regex patterns with kind tags, then tokenize any source text into a `List<Token>`.

### Value Construction

| Verb | Signature | Description |
|------|-----------|-------------|
| `creates` | `value(source Source) Value` | Wrap a source as a Value |

### Formats

| Verb | Signature | Description |
|------|-----------|-------------|
| `creates` | `json(source String) Result<Value<Json>, String>` | Decode JSON string to Value |
| `creates` | `json(value Value) Value<Json>` | Tag a Value as JSON for serialization |
| `validates` | `json(source String)` | True if source is valid JSON |
| `creates` | `toml(source String) Result<Value<Toml>, String>` | Decode TOML string to Value |
| `creates` | `toml(value Value) Value<Toml>` | Tag a Value as TOML for serialization |
| `validates` | `toml(source String)` | True if source is valid TOML |

### Value Accessors

Extract typed data from a `Value`. For corresponding validators, see [Types — Value Validators](math-types.md#value-validators).

| Verb | Signature | Description |
|------|-----------|-------------|
| `creates` | `tag(v Value) String` | Get the type tag (`"string"`, `"number"`, etc.) |

### URL

Defines a binary `Url` type for parsed URL components.

| Verb | Signature | Description |
|------|-----------|-------------|
| `creates` | `url(raw String) Url` | Parse a URL string into components |
| `creates` | `url(scheme String, host String, path String) Url` | Construct a URL from parts |
| `validates` | `url(raw String)` | True if string is a valid URL |
| `reads` | `url(source Url, params Table<Value>) Url` | Add query parameters to a URL |
| `creates` | `port(url Url) Integer` | Read the port component (-1 if not set) |

### Base64

| Verb | Signature | Description |
|------|-----------|-------------|
| `creates` | `base64(encoded String) ByteArray` | Decode Base64 string to byte array |
| `creates` | `base64(data ByteArray) String` | Encode byte array as Base64 |
| `validates` | `base64(encoded String)` | True if string is valid Base64 |

### CSV

RFC 4180-compliant CSV parsing. Returns `Value<Csv>`. Serialize back to string via `Types.string`.

| Verb | Signature | Description |
|------|-----------|-------------|
| `creates` | `csv(source String) Result<Value<Csv>, String>` | Parse CSV string into a Value |
| `validates` | `csv(source String)` | True if source is valid CSV |

### Tokenization

Defines binary types `Token` (a text span with position and kind tag) and `Rule` (a regex pattern paired with a kind integer). Rules are tried in order; longest match wins.

| Verb | Signature | Description |
|------|-----------|-------------|
| `creates` | `rule(pattern String, kind Integer) Rule` | Create a tokenization rule from a regex pattern and kind tag |
| `creates` | `tokens(source String, rules List<Rule>) List<Token>` | Tokenize source text using rules |

Token accessors (`start`, `end`, `kind`) and `string(token)` are in the [Language module](language.md). Characters that match no rule produce tokens with kind `-1`.

### Syntax Trees

Parse Prove source into a syntax tree backed by tree-sitter. See the [Prove module](prove.md) for tree traversal accessors. Extract source text via `Types.string(tree)`.

| Verb | Signature | Description |
|------|-----------|-------------|
| `creates` | `tree(source String) Result<Value<Tree>, Error>` | Parse Prove source into a syntax tree |

### Phantom Types

Parse defines four phantom marker types used as type parameters for `Value<T>`:

| Type | Used in | Description |
|------|---------|-------------|
| `Json` | `Value<Json>` | JSON-formatted data |
| `Toml` | `Value<Toml>` | TOML-formatted data |
| `Csv` | `Value<Csv>` | CSV-formatted data |
| `Tree` | `Value<Tree>` | Parsed syntax tree |

Plain `Value` (unparameterized) is compatible with any `Value<T>` — the phantom type parameter is opt-in.

```prove
  Parse creates toml json url tokens rule tag base64 validates url base64
  Parse types Value Toml Json Url Token Rule
  Types creates string
  Table creates table reads keys get types Table

main() Result<Unit, Error>!
from
    source as String = System.file("config.toml")!
    doc as Value<Toml> = Parse.toml(source)!
    root as Table<Value> = table(doc)
    names as List<String> = Table.keys(root)
    System.console("Keys: " + join(names, ", "))
```

---

## Format

**Module:** `Format` — string formatting and numeric display.

### Padding

| Verb | Signature | Description |
|------|-----------|-------------|
| `reads` | `pad_left(text String, width Integer, fill Character) String` | Left-pad to width |
| `reads` | `pad_right(text String, width Integer, fill Character) String` | Right-pad to width |
| `reads` | `center(text String, width Integer, fill Character) String` | Center within width |

### Number Formatting

| Verb | Signature | Description |
|------|-----------|-------------|
| `creates` | `hex(number Integer) String` | Integer to hexadecimal string |
| `creates` | `bin(number Integer) String` | Integer to binary string |
| `creates` | `octal(number Integer) String` | Integer to octal string |
| `creates` | `decimal(value Float, places Integer) String` | Float with fixed decimal places |

### Time & Date Formatting

Format time, date, datetime, and duration values using pattern strings.

Supported patterns: `"ISO8601"`, `"%Y-%m-%d"`, `"%H:%M:%S"`, `"%Y-%m-%d %H:%M:%S"`, `"%Hh %Mm %Ss"`, and other `strftime`-style patterns.

| Verb | Signature | Description |
|------|-----------|-------------|
| `creates` | `time(time Time, pattern String) String` | Format a time as a string |
| `creates` | `time(source String, pattern String) Time` | Parse a string into a time |
| `validates` | `time(source String, pattern String)` | True if string matches time format |
| `creates` | `date(date Date, pattern String) String` | Format a date as a string |
| `creates` | `date(source String, pattern String) Date` | Parse a string into a date |
| `validates` | `date(source String, pattern String)` | True if string matches date format |
| `creates` | `datetime(datetime DateTime, pattern String) String` | Format a datetime as a string |
| `creates` | `datetime(source String, pattern String) DateTime` | Parse a string into a datetime |
| `validates` | `datetime(source String, pattern String)` | True if string matches datetime format |
| `creates` | `duration(duration Duration, pattern String) String` | Format a duration as a string |
| `creates` | `duration(source String, pattern String) Duration` | Parse a string into a duration |

```prove
  Format reads pad_left creates hex decimal date creates date
  Time creates date types Date

creates format_address(addr Integer) String
from
    Format.pad_left(Format.hex(addr), 8, '0')

creates format_date(date Date) String
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
| `creates` | `search(text String, pattern String) Option<Match>` | Find first match |
| `creates` | `find_all(text String, pattern String) List<Match>` | Find all matches |

### Transform

| Verb | Signature | Description |
|------|-----------|-------------|
| `reads` | `replace(text String, pattern String, replacement String) String` | Replace first match |
| `creates` | `split(text String, pattern String) List<String>` | Split on pattern |

### Match Accessors

| Verb | Signature | Description |
|------|-----------|-------------|
| `creates` | `string(matched Match) String` | Matched text |
| `creates` | `start(matched Match) Integer` | Start offset in source string |
| `creates` | `end(matched Match) Integer` | End offset in source string |

```prove
  Pattern validates test reads replace creates search find_all split string start end types Match

reads sanitize(input String) String
requires
    test(input, "[a-zA-Z0-9 ]+")
from
    Pattern.replace(input, " +", " ")
```
