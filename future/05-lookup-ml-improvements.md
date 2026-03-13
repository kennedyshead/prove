# Lookup Table: Remaining ML Improvements

Two deferred improvements for `[Lookup]` / `binary` types, prioritised for ML use cases.

---

## Gap 4: Named Columns

**Problem**: When a binary lookup has two columns of the same type (e.g. two `Float` columns for
probability and confidence), the column is selected by matching type name alone. Both columns match
the same type, so the wrong one may be silently selected. There is no way to request a specific
column by name.

**Motivating example**:

```prove
binary Prediction Float Float where
    Cat     | 0.92 | 0.88
    Dog     | 0.07 | 0.91
    Other   | 0.01 | 0.73
```

`Prediction:Cat` is ambiguous — the emitter picks the first `Float` column regardless of intent.

**Proposed syntax**:

```prove
binary Prediction probability:Float confidence:Float where
    Cat     | 0.92 | 0.88
    Dog     | 0.07 | 0.91
    Other   | 0.01 | 0.73
```

Access: `Prediction:Cat.probability`, `Prediction:Cat.confidence`

**Scope of change**:
- Parser: `_parse_binary_lookup_def` — accept `name:Type` column headers
- AST: `LookupTypeDef.column_names: tuple[str, ...]` (parallel to `value_types`)
- Checker: `_check_lookup_access_expr` — use `.name` on `LookupAccessExpr` for column selection
- Emitter: `_emit_binary_lookup_tables` — use column names in array identifiers;
  `_emit_lookup_access` / `_emit_binary_lookup` — resolve by name instead of type match
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
