# impl05: Compiler CLI Commands ✓

**Status: Complete**

## Overview

Added `--load` and `--dump` flags to `prove compiler` for lookup table data management.

## What Was Implemented

### `src/prove/store_binary.py` (new)

Python implementation of the PDAT binary format matching `prove_store.c` exactly:

- `write_pdat(path, name, columns, variants, version)` — write PDAT from structured data
- `read_pdat(path)` — read PDAT, return `{name, version, columns, variants}`
- `prv_to_pdat(prv_path, output_path)` — parse `.prv`, extract binary `:[Lookup]`, write PDAT
- `pdat_to_prv(bin_path, output)` — read PDAT, generate `.prv` source with module declaration

### `src/prove/cli.py` (modified)

Added `prove compiler` subcommand after `prove view`:

```bash
prove compiler --load src/data.prv        # .prv → .dat
prove compiler --dump Data.dat            # .dat → stdout
prove compiler --dump Data.dat -o out.prv # .dat → file
prove compiler src/data.prv              # auto-detect from extension
```

### LSP cache switched to PDAT binary

`_ProjectIndexer` in `lsp.py` now writes cache as PDAT `.bin` files instead of `.prv` text:
- `.prove_cache/bigrams/current.bin`
- `.prove_cache/completions/current.bin`

### Tests

`tests/test_store_binary.py` — 15 tests covering:
- Write/read roundtrip (single, multi-column, empty, unicode)
- Error handling (bad magic, bad version)
- Format validation (magic bytes, version field)
- `.prv` ↔ PDAT conversion and full roundtrip

### Docs

`docs/cli.md` updated with `prove compiler` command reference.

## Exit Criteria

- [x] `--load` compiles .prv to .dat
- [x] `--dump` converts .dat to .prv
- [x] `--output` flag works
- [x] Tests pass (15/15 new + full suite)
- [x] Docs updated: `cli.md` (`prove compiler --load/--dump` commands)
- [x] LSP cache uses PDAT binary format
