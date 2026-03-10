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
