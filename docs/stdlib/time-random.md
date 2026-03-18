---
title: Time & Random - Prove Standard Library
description: Time calendar operations and Random value generation in the Prove standard library.
keywords: Prove Time, Prove Random, time operations, random generation, calendar
---

# Time & Random

## Time

**Module:** `Time` — time representation, arithmetic, and calendar operations.

Defines six binary types: `Time` (epoch timestamp), `Duration` (time span), `Date` (calendar date), `Clock` (time of day), `DateTime` (date + time), and `Weekday` (day of week, 0=Monday through 6=Sunday).

Only `inputs time()` is an IO verb (reads the system clock). All other functions are pure. See [Functions & Verbs](../functions.md) for the IO/pure distinction.

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
  Time inputs time creates duration date clock reads days weekday types Time Duration Date Clock

reads elapsed_days(start Time, stop Time) Integer
from
    span as Duration = Time.duration(start, stop)
    Time.duration(span) / 86400
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

inputs roll_pair() List<Integer>
from
    first as Integer = Random.integer(1, 6)
    second as Integer = Random.integer(1, 6)
    [first, second]
```
