# impl05: Compiler CLI Commands

## Overview

Add `--load` and `--dump` flags to `prove compiler` for lookup table data management.

## Commands

### prove compiler --load <file.prv>

Compiles Prove source lookup table to binary:

```
Input:  ast/types.prv
Output: binaries/types.bin
```

```bash
prove compiler --load ast/types.prv
prove compiler --load ast/math.prv
```

### prove compiler --dump

Dumps binary to Prove source for viewing/editing:

```
Input:  binaries/types.bin
Output: stdout (or --output file.prv)
```

```bash
prove compiler --dump binaries/types.bin
prove compiler --dump --output types.prv
```

Replaces current `prove view` command for binary files.

## Data Flow

```
AST (.prv)  ──prove compiler --load──→  Binary (.bin)
Binary (.bin)  ──prove compiler --dump──→  AST (.prv)
```

## Implementation

- Parse `.prv` files with `:[Lookup]` type definitions
- Compile to binary lookup tables
- Add `--output` flag for custom paths

## Exit Criteria

- [ ] `--load` compiles .prv to .bin
- [ ] `--dump` converts .bin to .prv
- [ ] `--output` flag works
- [ ] Tests pass
- [ ] Docs updated: `cli.md` (`prove compiler --load/--dump` commands)
