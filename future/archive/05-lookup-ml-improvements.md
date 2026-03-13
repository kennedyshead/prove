# Lookup Table: Remaining ML Improvements

Two deferred improvements for `[Lookup]` types, prioritised for ML use cases.

---

## Gap 4: Named Columns (for Duplicate-Type Columns)

**Default behaviour** (unchanged): Column access is matched by type, and each column type must be
unique. A single-`Float` column is accessed directly via `Prediction:Cat` — no names needed.

**Problem**: When a lookup genuinely needs two columns of the same type (e.g. two `Float`
columns for probability and confidence), type-based access is ambiguous. Today the emitter silently
picks the first matching column.

**Linter rule**: The linter must detect duplicate column types and flag them. For example:

```prove
// FLAGGED — duplicate Float columns, access is ambiguous
  type Prediction:[Lookup] is Float | String | Float where
    Cat     | 0.92 | "feline" | 0.88
    Dog     | 0.07 | "canine" | 0.91
    Other   | 0.01 | "other"  | 0.73
```

The diagnostic should suggest using named columns to disambiguate:

```
W350: lookup 'Prediction' has duplicate column type 'Float'.
      Use named columns to disambiguate: probability:Float | String | confidence:Float
```

**Named column syntax** (escape hatch for duplicate types):

```prove
  type Prediction:[Lookup] is probability:Float | String | confidence:Float where
    Cat     | 0.92 | "feline" | 0.88
    Dog     | 0.07 | "canine" | 0.91
    Other   | 0.01 | "other"  | 0.73
```

Access: `Prediction:Cat.probability`, `Prediction:Cat.confidence`.
The `String` column (unique type) is still accessed by type as usual — naming is only required
for the duplicate types.

**Scope of change**:
- Parser: `_parse_binary_lookup_def` — accept `name:Type` column headers alongside bare `Type`
- AST: `LookupTypeDef.column_names: tuple[str | None, ...]` (parallel to `value_types`;
  `None` for unnamed columns)
- Linter: detect duplicate column types when all columns are unnamed — emit warning with
  suggestion to use `name:Type` syntax
- Checker: `_check_lookup_access_expr` — use `.name` on `LookupAccessExpr` for named column
  selection; reject bare type access when the type is duplicated
- Emitter: `_emit_binary_lookup_tables` — use column names in array identifiers;
  `_emit_lookup_access` / `_emit_binary_lookup` — resolve by name when names are present,
  by type otherwise
- Formatter: `format_lookup_type` — preserve column names

---

## Gap 5: Performance at Scale (Binary Search / Hash Reverse Lookup)

**Problem**: `prove_lookup_find` and `prove_lookup_find_int` use linear scans — O(n) per lookup.
For ML label vocabularies with 1 000–10 000+ classes (ImageNet, WordNet), this is measurably slow
at inference time.

**Proposed approach**: Add sorted-array variants that use binary search — O(log n) — with no
dependency on dynamic allocation.

```c
/* Sorted string reverse table: binary search, O(log n). */
int prove_lookup_find_sorted(const Prove_LookupTable *table, const char *key);

/* Sorted integer reverse table: binary search, O(log n). */
int prove_lookup_find_int_sorted(const Prove_IntLookupTable *table, int64_t key);
```

The emitter would emit the reverse tables pre-sorted (at compile time, since entries are static)
and call the sorted variants automatically when `is_binary` is true and the table has more than
a threshold number of entries (e.g. > 16).

**Scope of change**:
- `prove_lookup.h` / `prove_lookup.c`: add `prove_lookup_find_sorted` and
  `prove_lookup_find_int_sorted`
- `_emit_types.py`: sort reverse entries at emission time; choose sorted vs. linear based on
  entry count
- `_emit_exprs.py`: call the appropriate variant in `_emit_binary_lookup`
- `test_lookup_runtime_c.py`: add tests for sorted variants

**Threshold**: linear scan is faster for very small tables (cache effects); a threshold around
16–32 entries is a reasonable crossover.

---

## Documentation & AGENTS Updates

When this work is implemented:

- **`docs/types.md`** — Under Lookup Types, add a "Named Columns" subsection showing
  the `name:Type` column header syntax and `.name` field access. Add a note that the
  binary search variant is selected automatically by the emitter for tables with more
  than 16 entries (no user action needed).
- **`AGENTS.md`** — Under AST nodes, add `LookupTypeDef.column_names: tuple[str, ...]`
  as a parallel field to `value_types`. Under the emitter, note: "Lookup reverse tables
  with >16 entries are emitted pre-sorted and use `prove_lookup_find_sorted` /
  `prove_lookup_find_int_sorted` (binary search, O(log n))."
- Run `mkdocs build --strict` after editing the types page.
