# Database Stdlib — Binary Lookup Tables

## Overview

Binary lookup tables as the foundation for the Prove database. Uses `Kind:[Lookup]` storage modifier for new code, `binary` keyword reserved for stdlib.

## Status

- `binary` keyword: ✅ Complete
- `type Name:[Lookup]` syntax: Not started

## Current Syntax (stdlib only)

```prove
binary HttpStatus String Integer where
    Ok | "OK" | 200
    NotFound | "Not Found" | 404
    ServerError | "Internal Server Error" | 500
```

## New Syntax (user code)

```prove
type HttpStatus:[Lookup] is String Integer where
    Ok | "OK" | 200
    NotFound | "Not Found" | 404
    ServerError | "Internal Server Error" | 500
```

## Usage

```prove
// Variant → column lookup
name as String = HttpStatus:Ok      // "OK"
code as Integer = HttpStatus:NotFound  // 404
Integer HttpStatus:Ok              // 200
Decimal HttpStatus:Ok               // 200.0
```

## Implementation

### 1. Parser

Add `Lookup` as modifier in type expressions:
- Handle `type Name:[Lookup] is Type1 Type2 ... where entries`
- Keep existing `binary` parsing unchanged

### 2. Checker

- Handle `Lookup` modifier on type definitions
- Generate same `LookupTypeDef` with `is_binary=True`

### 3. C Emitter

No changes — reuses existing lookup table emission.

## Files to Modify

| File | Change |
|------|--------|
| `prove-py/src/prove/parser.py` | Add modifier parsing for `Kind:[Lookup]` |
| `prove-py/src/prove/checker.py` | Handle Lookup modifier |

## Example

`examples/binary_lookup_demo/src/main.prv`

## Verification

```bash
cd examples/binary_lookup_demo
prove build
./binary_lookup_demo
# Output:
# Status name: OK
# Status code: 404
```

## Exit Criteria

- [ ] `binary` keyword removed from user code, kept in stdlib only
- [ ] `type Name:[Lookup] is ... where` parses correctly
- [ ] Lookup tables compile to C arrays
- [ ] Runtime lookup works (`TypeName:Variant`)
- [ ] Example updated and passes
- [ ] Stdlib `binary` keyword unchanged
- [ ] Docs updated: `types.md` (Lookup modifier syntax), `syntax.md` (type modifiers)
