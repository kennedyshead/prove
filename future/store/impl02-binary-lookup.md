# Store Stdlib — Binary Lookup Tables

## Overview

Binary lookup tables as the foundation for the Prove store. Uses `Kind:[Lookup]` storage modifier for new code, `binary` keyword reserved for stdlib.

## Status

- `binary` keyword: ✅ Complete (parsed); restriction to stdlib pending (E397)
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

### 4. Restrict `binary` to stdlib (pending — E397)

`binary` is still parseable in user code. Two uses need guarding:

**Function body marker** (`parser.py` line ~542 sets `is_binary=True` on `FunctionDef`):
```python
# checker.py — in _check_function():
if fd.binary and not self._is_stdlib_source():
    self._error("E397", "`binary` is reserved for stdlib implementations", fd.span)
```

**Type body** (`type X is binary` → `BinaryDef` in `ast_nodes.py`):
```python
# checker.py — in _check_type_def():
if isinstance(body, BinaryDef) and not self._is_stdlib_source():
    self._error("E397", "`binary` is reserved for stdlib type definitions", td.span)
```

**Helper** — the checker already reads `module.span.file` (line 249). Stdlib `.prv`
files live under `.../prove/stdlib/`; programmatic stubs use `"<stdlib>"`:
```python
def _is_stdlib_source(self) -> bool:
    f = self._module.span.file if self._module.span else ""
    return f.startswith("<") or "/stdlib/" in f
```

**Wiring:**
- `errors.py`: extend `_register_doc_range("E", 391, 394)` to include 397,
  or add `_register_doc_range("E", 397, 397)`
- `diagnostics_demo/src/E397.prv`: example that triggers the error
- Next available code after E396 (E397 — E398–E409 free; E410+ = comptime)

## Files to Modify

| File | Change |
|------|--------|
| `prove-py/src/prove/checker.py` | Add `_is_stdlib_source()` + E397 checks in `_check_function` and `_check_type_def` |
| `prove-py/src/prove/errors.py` | Register E397 in doc range |
| `examples/diagnostics_demo/src/E397.prv` | New — triggers E397 |
| `examples/binary_lookup_demo/src/main.prv` | New — demo of `:[Lookup]` usage |

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
- [x] `type Name:[Lookup] is ... where` parses correctly
- [x] Lookup tables compile to C arrays
- [x] Runtime lookup works (`TypeName:Variant`)
- [ ] Example updated and passes
- [x] Stdlib `binary` keyword unchanged
- [ ] Docs updated: `types.md` (Lookup modifier syntax), `syntax.md` (type modifiers)
