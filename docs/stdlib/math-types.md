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
| `derives` | `abs(n Integer) Integer` | Absolute value of integer |
| `derives` | `abs(x Float) Float` | Absolute value of float |
| `derives` | `abs(x Decimal) Decimal` | Absolute value of decimal |
| `derives` | `min(first Integer, second Integer) Integer` | Smaller of two integers |
| `derives` | `min(first Float, second Float) Float` | Smaller of two floats |
| `derives` | `min(first Decimal, second Decimal) Decimal` | Smaller of two decimals |
| `derives` | `max(first Integer, second Integer) Integer` | Larger of two integers |
| `derives` | `max(first Float, second Float) Float` | Larger of two floats |
| `derives` | `max(first Decimal, second Decimal) Decimal` | Larger of two decimals |

### Clamp

| Verb | Signature | Description |
|------|-----------|-------------|
| `derives` | `clamp(value Integer, minimum Integer, maximum Integer) Integer` | Constrain integer to range |
| `derives` | `clamp(value Float, minimum Float, maximum Float) Float` | Constrain float to range |
| `derives` | `clamp(value Decimal, minimum Decimal, maximum Decimal) Decimal` | Constrain decimal to range |

### Float Operations

| Verb | Signature | Description |
|------|-----------|-------------|
| `derives` | `sqrt(x Float) Float` | Square root |
| `derives` | `power(base Float, exponent Float) Float` | Exponentiation (also available as `pow`) |
| `creates` | `floor(x Float) Integer` | Round down to integer |
| `creates` | `ceil(x Float) Integer` | Round up to integer |
| `creates` | `round(x Float) Integer` | Round to nearest integer |
| `derives` | `log(x Float) Float` | Natural logarithm |
| `derives` | `log2(x Float) Float` | Base-2 logarithm |
| `derives` | `log10(x Float) Float` | Base-10 logarithm |
| `derives` | `exp(x Float) Float` | Exponential (e^x) |

### Trigonometry

| Verb | Signature | Description |
|------|-----------|-------------|
| `derives` | `sin(angle Float) Float` | Sine |
| `derives` | `cos(angle Float) Float` | Cosine |
| `derives` | `tan(angle Float) Float` | Tangent |
| `derives` | `asin(value Float) Float` | Arc sine |
| `derives` | `acos(value Float) Float` | Arc cosine |
| `derives` | `atan(value Float) Float` | Arc tangent |
| `derives` | `atan2(y Float, x Float) Float` | Two-argument arc tangent |

### Constants

| Verb | Signature | Description |
|------|-----------|-------------|
| `derives` | `pi() Float` | Pi (3.14159...) |
| `derives` | `e() Float` | Euler's number (2.71828...) |

```prove
  Math derives abs min max sqrt clamp creates floor

derives distance(x Integer, y Integer) Integer
from
    Math.abs(Math.min(x, y) - Math.max(x, y))

derives clamp_price(price Decimal, lo Decimal, hi Decimal) Decimal
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
| `creates` | `integer(v Value) Integer` | Extract integer content from a Value |

### Float Conversions

| Verb | Signature | Description |
|------|-----------|-------------|
| `creates` | `float(s String) Result<Float, String>` | Parse string to float |
| `creates` | `float(n Integer) Float` | Promote integer to float |
| `creates` | `float(x Decimal) Float` | Convert decimal to float |
| `creates` | `float(v Value) Float` | Extract floating-point content from a Value |

### String Conversions

| Verb | Signature | Description |
|------|-----------|-------------|
| `creates` | `string(n Integer) String` | Integer to string |
| `creates` | `string(x Float) String` | Float to string |
| `creates` | `string(x Decimal) String` | Decimal to string |
| `creates` | `string(b Boolean) String` | Boolean to `"true"` or `"false"` |
| `creates` | `string(b Byte) String` | Byte to decimal string |
| `creates` | `string(c Character) String` | Character to string |
| `creates` | `string(v Value) String` | Convert a Value to its string representation |

### Format Serialization

Convert complex types to strings. For phantom-typed `Value<T>` (from [Parse](parse-format-pattern.md#phantom-types)), the phantom type determines the output format. Also handles `Url` host extraction and `Token` text extraction.

| Verb | Signature | Description |
|------|-----------|-------------|
| `creates` | `string(v Value<Json>) String` | Serialize JSON value to string |
| `creates` | `string(v Value<Toml>) String` | Serialize TOML value to string |
| `creates` | `string(v Value<Csv>) String` | Serialize CSV value to string |
| `creates` | `string(v Value<Tree>) String` | Extract full source text from tree |
| `creates` | `string(url Url) String` | Extract host component from URL |
| `creates` | `string(token Token) String` | Extract matched text from token |
| `creates` | `string(matched Match) String` | Extract matched text from Pattern match |
| `creates` | `string(node Node) String` | Source text spanned by an AST node |
| `creates` | `string(value ByteArray) String` | Convert byte array to string |
| `creates` | `string(position Position) String` | Convert position to string |
| `creates` | `string(time Time) String` | Time to ISO string |
| `creates` | `string(date Date) String` | Date to ISO string |
| `creates` | `string(datetime DateTime) String` | DateTime to ISO string |
| `creates` | `string(clock Clock) String` | Clock to string |
| `creates` | `string(duration Duration) String` | Duration to string |

```prove
  Parse creates json types Json
  Types creates string

creates render(user User) String
from
    user |> value |> json |> string
```

### Character Conversions

| Verb | Signature | Description |
|------|-----------|-------------|
| `creates` | `code(character Character) Integer` | Character to code point |
| `creates` | `character(code Integer) Character` | Code point to character |

### Boolean Conversions

| Verb | Signature | Description |
|------|-----------|-------------|
| `creates` | `boolean(n Integer) Boolean` | Integer to boolean (0=false, non-zero=true) |
| `creates` | `boolean(s String) Result<Boolean, String>` | Parse `"true"` or `"false"` |
| `creates` | `boolean(v Value) Boolean` | Extract boolean content from a Value |

### Decimal Conversions

| Verb | Signature | Description |
|------|-----------|-------------|
| `creates` | `decimal(s String) Result<Decimal, String>` | Parse string to decimal |
| `creates` | `decimal(n Integer) Decimal` | Promote integer to decimal |
| `creates` | `decimal(v Value) Decimal` | Extract decimal content from a Value |

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

Typed overloads are available for `Option<Float>`, `Option<Decimal>`, and `Option<Boolean>`.

#### Unwrap

| Verb | Signature | Description |
|------|-----------|-------------|
| `derives` | `unwrap(option Option<Integer>, default Integer) Integer` | Extract integer or use default |
| `derives` | `unwrap(option Option<String>, default String) String` | Extract string or use default |
| `derives` | `unwrap(option Option<Float>, default Float) Float` | Extract float or use default |
| `derives` | `unwrap(option Option<Decimal>, default Decimal) Decimal` | Extract decimal or use default |
| `derives` | `unwrap(option Option<Boolean>, default Boolean) Boolean` | Extract boolean or use default |
| `derives` | `unwrap(option Option<Value>, default Value) Value` | Extract value or use default |

```prove
  Types creates integer float decimal string code derives unwrap validates integer string ok value

creates format_pair(label String, n Integer) String
from
    label + ": " + Types.string(n)

derives safe_first(items List<Integer>) Integer
from
    Types.unwrap(List.first(items), 0)

transforms parse_price(input String) Decimal!
from
    Types.decimal(input)!
```
