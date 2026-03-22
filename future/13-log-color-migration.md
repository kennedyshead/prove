# Log Module — Migrate ANSI Constants to UI Color Lookup

## Summary

Replace the raw ANSI escape string constants in `Log` (`RED`, `GREEN`, `YELLOW`, `BLUE`, `MAGENTA`, `CYAN`, `WHITE`, `RESET`, `BOLD`, `DIM`) with references to `UI`'s `Color:[Lookup]` type.

## Current State

`Log` (pure-Prove module at `proof/src/stdlib/pure/log.prv`) defines 10 string constants with raw ANSI escape codes:

```prove
RED as String = "[31m"
GREEN as String = "[32m"
// etc.
```

These are used in the four logging functions (`debug`, `info`, `warning`, `error`) to colorize output.

## Target State

`Log` imports `UI` and uses `Color` lookup values instead of raw escape strings:

```prove
UI types Color
```

The logging functions use `Color:Blue`, `Color:Green`, etc. The C emitter resolves `Color` lookups to the platform-appropriate escape sequence.

## Migration Steps

1. **Emit Color lookup to ANSI** — ensure the C emitter can resolve `Color:Red` → `"\033[31m"` in string interpolation contexts. This may already work via the lookup's `ansi` column; verify with a test.

2. **Handle BOLD/DIM** — `BOLD` and `DIM` are text attributes, not colors. Either:
   - Add a `Style` or `TextWeight` lookup to `UI` (Phase 2 already plans a `Style` struct with `bold`/`underline` fields), or
   - Keep `BOLD`/`DIM` as raw constants in `Log` until Phase 2 `Style` lands.

3. **Handle RESET** — `RESET` (`\033[0m`) resets all formatting. Either:
   - Add `Color:Default` (already exists in `UI` with ansi code 0), or
   - Add a dedicated `reset()` function in Terminal.

4. **Update log.prv** — replace string constants with Color references. Add `UI types Color` import. Update the format strings in `debug`/`info`/`warning`/`error`.

5. **Update tests** — `test_stdlib_loader.py` tests that Log constants are `String` type with escape sequences. These tests need updating to reflect the new Color-based approach.

6. **Update docs** — `docs/stdlib/log.md` constants table changes from raw escapes to Color references.

7. **Deprecation** — the raw constants (`RED`, `GREEN`, etc.) can be removed outright since this is pre-1.0 for the Color migration. No deprecation period needed.

## Dependencies

- Requires Color lookup → ANSI string emission to work in f-string interpolation
- Phase 2 `Style` struct for BOLD/DIM migration (optional — can ship color migration first)

## Priority

Low — cosmetic cleanup. The current approach works fine. This is a consistency improvement to consolidate color handling in a single type.
