---
title: Math & Types - Prove Standard Library
description: Math numeric operations and Types conversion functions in the Prove standard library.
keywords: Prove Math, Prove Types, numeric operations, type conversion
---

# Math & Types

## Math

**Module:** `Math` — numeric operations on `Integer`, `Float`, and `Decimal`.

Functions with Integer/Float/Decimal overloads dispatch based on argument type.

### Absolute Value, Min, Max

| Verb | Signature | Description |
|------|-----------|-------------|
| `reads` | `abs(n Integer) Integer` | Absolute value of integer |
| `reads` | `abs(x Float) Float` | Absolute value of float |
| `reads` | `abs(x Decimal) Decimal` | Absolute value of decimal |
| `reads` | `min(first Integer, second Integer) Integer` | Smaller of two integers |
| `reads` | `min(first Float, second Float) Float` | Smaller of two floats |
| `reads` | `min(first Decimal, second Decimal) Decimal` | Smaller of two decimals |
| `reads` | `max(first Integer, second Integer) Integer` | Larger of two integers |
| `reads` | `max(first Float, second Float) Float` | Larger of two floats |
| `reads` | `max(first Decimal, second Decimal) Decimal` | Larger of two decimals |

### Clamp

| Verb | Signature | Description |
|------|-----------|-------------|
| `transforms` | `clamp(value Integer, minimum Integer, maximum Integer) Integer` | Constrain integer to range |
| `transforms` | `clamp(value Float, minimum Float, maximum Float) Float` | Constrain float to range |
| `transforms` | `clamp(value Decimal, minimum Decimal, maximum Decimal) Decimal` | Constrain decimal to range |

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

reads clamp_price(price Decimal, lo Decimal, hi Decimal) Decimal
from
    Math.clamp(price, lo, hi)
```

> **Note:** Math functions like `sqrt` and `floor` require `Float` arguments. Use the `f` suffix on literals: `16.0f` not `16.0` (which is `Decimal`). Overloaded functions (`abs`, `min`, `max`, `clamp`) accept both `Float` and `Decimal` arguments. See [Type System — Type Modifiers](../types.md#type-modifiers) for more on the Float/Decimal distinction.

---

## Types

**Module:** `Types` — type validation and conversion between primitive types.

The function name is the *target type*. Failable conversions from strings return [`Result`](../types.md#option-and-result). Validators check that a value is of the expected type.

### Type Validators

| Verb | Signature | Description |
|------|-----------|-------------|
| `validates` | `string(s String)` | True if value is a string |
| `validates` | `integer(n Integer)` | True if value is an integer |
| `validates` | `float(n Float)` | True if value is a float |
| `validates` | `decimal(n Decimal)` | True if value is a decimal |
| `validates` | `boolean(b Boolean)` | True if value is a boolean |
| `validates` | `character(c Character)` | True if value is a character |

### Integer Conversions

| Verb | Signature | Description |
|------|-----------|-------------|
| `creates` | `integer(s String) Result<Integer, String>` | Parse string to integer |
| `creates` | `integer(x Float) Integer` | Truncate float to integer |
| `creates` | `integer(x Decimal) Integer` | Truncate decimal to integer |
| `creates` | `integer(b Boolean) Integer` | Boolean to integer (true=1, false=0) |

### Float Conversions

| Verb | Signature | Description |
|------|-----------|-------------|
| `creates` | `float(s String) Result<Float, String>` | Parse string to float |
| `creates` | `float(n Integer) Float` | Promote integer to float |
| `creates` | `float(x Decimal) Float` | Convert decimal to float |

### String Conversions

| Verb | Signature | Description |
|------|-----------|-------------|
| `reads` | `string(n Integer) String` | Integer to string |
| `reads` | `string(x Float) String` | Float to string |
| `reads` | `string(x Decimal) String` | Decimal to string |
| `reads` | `string(b Boolean) String` | Boolean to `"true"` or `"false"` |
| `reads` | `string(b Byte) String` | Byte to decimal string |
| `reads` | `string(c Character) String` | Character to string |
| `reads` | `string(v Value) String` | Extract string content from a Value |

### Character Conversions

| Verb | Signature | Description |
|------|-----------|-------------|
| `reads` | `code(character Character) Integer` | Character to code point |
| `creates` | `character(code Integer) Character` | Code point to character |

### Boolean Conversions

| Verb | Signature | Description |
|------|-----------|-------------|
| `creates` | `boolean(n Integer) Boolean` | Integer to boolean (0=false, non-zero=true) |
| `creates` | `boolean(s String) Result<Boolean, String>` | Parse `"true"` or `"false"` |

### Decimal Conversions

| Verb | Signature | Description |
|------|-----------|-------------|
| `creates` | `decimal(s String) Result<Decimal, String>` | Parse string to decimal |
| `creates` | `decimal(n Integer) Decimal` | Promote integer to decimal |

### Value Validators

| Verb | Signature | Description |
|------|-----------|-------------|
| `validates` | `text(value Value)` | Check if Value is text |
| `validates` | `number(value Value)` | Check if Value is a number |
| `validates` | `decimal(value Value)` | Check if Value is a decimal |
| `validates` | `boolean(value Value)` | Check if Value is a boolean |
| `validates` | `array(value Value)` | Check if Value is an array |
| `validates` | `object(value Value)` | Check if Value is an object |
| `validates` | `unit(value Value)` | Check if Value is unit (null) |
| `validates` | `value(source Source)` | Check if a Source is valid |

### Result and Option Utilities

The Types module also provides validators and unwrap functions for [`Result<Value, Error>`](../types.md#option-and-result) and [`Option<Value>`](../types.md#option-and-result).

#### Result Validators

| Verb | Signature | Description |
|------|-----------|-------------|
| `validates` | `ok(result Result<Value, Error>)` | True if Result is Ok |
| `validates` | `error(result Result<Value, Error>)` | True if Result is Err |

#### Option Validators

| Verb | Signature | Description |
|------|-----------|-------------|
| `validates` | `value(option Option<Value>)` | True if Option has a value |
| `validates` | `unit(option Option<Value>)` | True if Option is empty |

Typed overloads are available for `Option<Integer>`, `Option<String>`, `Option<Float>`, `Option<Decimal>`, and `Option<Boolean>`.

#### Unwrap

| Verb | Signature | Description |
|------|-----------|-------------|
| `reads` | `unwrap(option Option<Integer>, default Integer) Integer` | Extract integer or use default |
| `reads` | `unwrap(option Option<String>, default String) String` | Extract string or use default |
| `reads` | `unwrap(option Option<Float>, default Float) Float` | Extract float or use default |
| `reads` | `unwrap(option Option<Decimal>, default Decimal) Decimal` | Extract decimal or use default |
| `reads` | `unwrap(option Option<Boolean>, default Boolean) Boolean` | Extract boolean or use default |
| `transforms` | `unwrap(option Option<Value>) Value` | Extract inner value (panics if empty) |

```prove
  Types creates integer float decimal reads string code unwrap validates integer string ok value

reads format_pair(label String, n Integer) String
from
    label + ": " + Types.string(n)

reads safe_first(items List<Integer>) Integer
from
    Types.unwrap(List.first(items), 0)

reads parse_price(input String) Decimal!
from
    Types.decimal(input)!
```
