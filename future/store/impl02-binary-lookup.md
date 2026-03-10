# Store Stdlib — Binary Lookup Tables

## Overview

Binary lookup tables as the foundation for the Prove store. Uses `Kind:[Lookup]` storage modifier for new code, `binary` keyword reserved for stdlib.

## Status

- `binary` keyword: ✅ Complete (parsed + E397 restriction)
- `type Name:[Lookup]` syntax: ✅ Complete

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

### 1. Parser ✅ Done

`type Name:[Lookup] is Type1 Type2 ... where entries` parses via the existing
modifier path in `parser.py` (lines ~769–793). `binary` parsing unchanged.

### 2. Checker ✅ Done

`LookupTypeDef` with `is_binary=True` registered and validated.

### 3. C Emitter ✅ Done

`_emit_type_def` in `_emit_types.py` handles `LookupTypeDef` — generates C enum
and (when `is_binary=True`) column arrays via `_emit_binary_lookup_tables`.

### 4. Restrict `binary` to stdlib ✅ Done (E397)

Two uses guarded in `checker.py`:

**Function body marker** — `_check_function()` emits E397 when `fd.binary`
is used outside a stdlib module (uses existing `_is_stdlib` flag set from
`is_stdlib_module(decl.name)`).

**Type body** — `_register_type()` emits E397 when `BinaryDef` is used
outside a stdlib module.

**Wiring:**
- `errors.py`: E397 registered in `DIAGNOSTIC_DOCS`
- `diagnostics.md`: E397 documented
- `diagnostics_demo/src/E397.prv`: example that triggers both errors
- `test_checker.py`: two tests (`test_e397_binary_function_body_non_stdlib`,
  `test_e397_binary_type_body_non_stdlib`)

## Example

`examples/lookup_demo/src/main.prv` — demonstrates `:[Lookup]` with forward
and reverse lookups.

## Exit Criteria

- [x] `binary` keyword restricted to stdlib only (E397)
- [x] `type Name:[Lookup] is ... where` parses correctly
- [x] Lookup tables compile to C arrays
- [x] Runtime lookup works (`TypeName:Variant`)
- [x] Example exists and works (`examples/lookup_demo`)
- [x] Stdlib `binary` keyword unchanged
- [x] Docs updated: `types.md` (Lookup modifier syntax), `syntax.md` (type modifiers)
- [x] Diagnostics: E397 documented, E395/E396 registered, W390/W391 registered
