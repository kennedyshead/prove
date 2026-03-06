# Stdlib Pure Prove Analysis

This document analyzes which stdlib modules can be implemented in pure Prove (as opposed to C bindings).

## Summary

| Module | Status | Reason |
|--------|--------|--------|
| **Character** | Partial | Classification is pure, string indexing needs C |
| **Text** | Partial | Most operations pure, but split/join/replace need efficient C |
| **Table** | Partial | Interface is pure, hash table internals need C |
| **List** | Most | All operations are pure, but sort needs C for performance |
| **Math** | Most | Pure arithmetic in Prove, but sqrt/pow/log need C (-lm) |
| **Convert** | Yes | All conversions can be pure Prove |
| **Path** | Yes | All operations are pure string manipulation |
| **Pattern** | No | Requires POSIX regex.h C library |
| **Format** | Yes | Can use Prove string ops + snprintf FFI |
| **Error** | Yes | All validators/unwrap are pure |
| **Parse** | No | TOML/JSON parsing requires C implementation |
| **InputOutput** | No | By definition not pure (side effects) |

---

## Detailed Analysis

### ✅ Can Be Pure Prove (Convert, Path, Error)

These modules have simple pure functions that map directly to Prove logic.

#### Convert
- `integer(String)` — parse via Prove string iteration
- `float(String)` — parse via Prove string iteration  
- `string(Integer/Float/Boolean)` — digit-by-digit conversion
- `code(Character)` / `character(Integer)` — direct code point mapping

**Status:** Full Prove implementation feasible. No external C needed except possibly snprintf for Float→String.

#### Path
- `join` — string concatenation with `/` separator
- `parent` — find last `/` and slice
- `name` — find last `/` and take suffix
- `stem` — strip extension after last `.`
- `extension` — take substring after last `.`
- `absolute` — check if starts with `/`
- `normalize` — process `.` and `..` segments

**Status:** Pure string operations, fully implementable in Prove.

#### Error
- `ok(Result)` — check Result tag
- `err(Result)` — check Result tag
- `some(Option)` — check Option tag
- `none(Option)` — check Option tag
- `unwrap_or` — extract value or return default

**Status:** Trivial tag checks. Fully implementable in Prove.

---

### ⚠️ Mostly Pure (Needs Some C)

#### Character
**Pure Prove candidates:**
- `alpha`, `digit`, `alnum`, `upper`, `lower`, `space` — all simple range checks

**Requires C:**
- `at(String, Integer)` — efficient string indexing

**Status:** 6/7 functions can be pure Prove.

#### Text
**Pure Prove candidates:**
- `length` — already pure
- `slice` — string slicing via iteration
- `starts`, `ends`, `contains` — substring search
- `index` — find substring position
- `trim`, `lower`, `upper`, `repeat` — character iteration
- Builder pattern (`builder`, `string`, `char`, `build`, `length`)

**Requires C:**
- `split` — needs efficient string splitting
- `join` — needs efficient concatenation  
- `replace` — needs regex or complex iteration

**Status:** ~10/14 functions can be pure Prove.

#### List
**Pure Prove candidates:**
- `length`, `first`, `last`, `empty` — simple queries
- `contains`, `index` — linear search
- `slice`, `reverse` — list transformation
- `range` — generate integer sequence

**Requires C:**
- `sort` — quicksort/mergesort performance

**Status:** 7/9 functions can be pure Prove.

#### Math
**Pure Prove candidates:**
- `abs(Integer)` — simple conditional
- `min`, `max` — simple comparison
- `clamp` — simple conditional
- `floor`, `ceil`, `round` — integer operations

**Requires C:**
- `abs(Float)` — needs fabs()
- `min(Float)`, `max(Float)` — float comparison
- `clamp(Float)` — float comparison
- `sqrt`, `pow`, `log` — C math library (-lm)

**Status:** ~5/11 functions can be pure Prove.

#### Format
**Pure Prove candidates:**
- `pad_left`, `pad_right`, `center` — string padding
- `hex`, `bin`, `octal` — base conversion

**Requires C:**
- `decimal` — needs snprintf for float formatting

**Status:** 4/5 functions can be pure Prove.

---

### ❌ Requires C (Cannot Be Pure)

#### Pattern
- Uses POSIX `regex.h` for regex operations
- `test`, `search`, `find_all`, `replace`, `split`, `text`, `start`, `end`
- All require C regex library

#### Parse
- TOML/JSON parsing is complex state machine
- `toml`, `json`, `tag`, `text`, `number`, `decimal`, `bool`, `array`, `object`, validators

#### InputOutput
- By definition not pure (side effects)
- Console, file, system, directory, process operations

---

## Candidate Modules for Pure Prove Rewrite

**Priority 1 (Easy, high value):**
1. **Error** — trivial, 100% pure
2. **Path** — pure string ops, straightforward
3. **Convert** — parsing/formatting is good Prove exercise

**Priority 2 (Medium complexity):**
4. **Character** — 6 of 7 functions trivial
5. **List** — except sort
6. **Math** — except sqrt/pow/log

**Priority 3 (Complex, lower priority):**
7. **Text** — split/join/replace tricky
8. **Format** — decimal needs FFI

**Not Recommended:**
- Pattern — requires C regex
- Parse — complex parsing
- InputOutput — inherently impure
- Table — hash table internals
- List.sort — needs performant sorting

---

## Implementation Notes

### Pure Prove Functions Are Memoizable
All pure Prove stdlib functions are eligible for the compiler's auto-memoization:

```prove
transforms factorial(n Integer) Integer
  ensures result >= 1
  requires n >= 0
from
    if
    n <= 1
    then
    1
    else
    n * factorial(n - 1)
```

With memoization, repeated calls with same arguments return cached results.

### Current `binary` Keyword
The current stdlib uses `binary` to mark C-backed functions. When migrating to pure Prove:

```prove
# Current (C-backed)
transforms hex(n Integer) String
  binary

# Future (Pure Prove)
transforms hex(n Integer) String
  from
    # Prove implementation
```

### Performance Considerations
Even pure Prove implementations should benchmark against C versions. Likely needs C:
- `List.sort` — O(n log n) performance critical
- `Text.split` / `Text.join` — heavy string allocation
- `Pattern.*` — regex complexity
- `Parse.*` — parsing state machines
- `Math.sqrt` / `pow` / `log` — hardware-accelerated
