---
title: Character & Text - Prove Standard Library
description: Character classification and Text string operations in the Prove standard library.
keywords: Prove Character, Prove Text, string operations, StringBuilder
---

# Character & Text

## Character

**Module:** `Character` — character classification and string-to-character access.

All classification functions take a single `Character` and return `Boolean`.

### Classification

| Verb | Signature | Description |
|------|-----------|-------------|
| `validates` | `alphabetic(c Character)` | True if alphabetic (a–z, A–Z) |
| `validates` | `digit(c Character)` | True if numeric digit (0–9) |
| `validates` | `alphanumeric(c Character)` | True if alphanumeric |
| `validates` | `uppercase(c Character)` | True if uppercase letter |
| `validates` | `lowercase(c Character)` | True if lowercase letter |
| `validates` | `whitespace(c Character)` | True if whitespace |

### Access

| Verb | Signature | Description |
|------|-----------|-------------|
| `creates` | `at(string String, index Integer) Character` | Character at index (0-based, bounds-checked) |

```prove
  Character validates alphabetic digit whitespace creates at

validates is_identifier_start(c Character)
from
    Character.alphabetic(c)
```

---

## Text

**Module:** `Text` — string operations and construction.

Defines a binary `StringBuilder` type for efficient incremental string building.

### Query

| Verb | Signature | Description |
|------|-----------|-------------|
| `creates` | `length(s String) Integer` | Number of bytes in string |
| `creates` | `index(text String, substring String) Option<Integer>` | Find position of substring |

### Validation

| Verb | Signature | Description |
|------|-----------|-------------|
| `validates` | `starts(s String, prefix String)` | True if string begins with prefix |
| `validates` | `ends(s String, suffix String)` | True if string ends with suffix |
| `validates` | `contains(s String, sub String)` | True if substring is present |

### Transform

| Verb | Signature | Description |
|------|-----------|-------------|
| `derives` | `slice(text String, start Integer, end Integer) String` | Extract substring [start, end) |
| `creates` | `split(text String, separator String) List<String>` | Split by delimiter |
| `creates` | `join(parts List<String>, separator String) String` | Join strings with separator |
| `derives` | `trim(text String) String` | Remove leading and trailing whitespace |
| `derives` | `lower(text String) String` | Convert to lowercase |
| `derives` | `upper(text String) String` | Convert to uppercase |
| `derives` | `replace(text String, old String, new String) String` | Replace all occurrences |
| `derives` | `repeat(text String, count Integer) String` | Repeat string count times |

### Builder

The `StringBuilder` type allows efficient incremental string construction.

| Verb | Signature | Description |
|------|-----------|-------------|
| `creates` | `builder() StringBuilder:[Mutable]` | Create an empty builder |
| `derives` | `string_builder(builder StringBuilder:[Mutable], text String) StringBuilder:[Mutable]` | Append a string |
| `derives` | `char(builder StringBuilder:[Mutable], character Character) StringBuilder:[Mutable]` | Append a character |
| `creates` | `build(builder StringBuilder:[Mutable]) String` | Finalize to string |
| `creates` | `length(builder StringBuilder:[Mutable]) Integer` | Current builder length |

```prove
  Text creates length index validates contains starts derives slice derives trim lower upper replace repeat creates split join
  Text creates builder derives string_builder creates build

creates word_count(text String) Integer
from
    parts as List<String> = Text.split(Text.trim(text), " ")
    Text.length(parts)
```
