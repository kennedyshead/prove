# Prove Compiler Refactoring Plan

## Context

The Prove compiler Python codebase (~49K LOC) is well-architected overall — clean pipeline, zero circular imports in the main path, good mixin separation. However, several god methods (300-700+ lines), duplicated tree walkers, repetitive cast/unwrap patterns, and data-heavy files create maintainability and readability risks. This plan addresses these systematically in 6 phases, each independently committable and testable.

---

## Phase 1: Shared Helpers (unblocks Phases 2-3)

### 1a. Deduplicate Expression Tree Walkers

**Problem**: 4-6 near-identical AST walkers across checker files.

**Exact duplicates to eliminate**:
- `_match_arms_have_fail_prop()` — checker.py:270-303 (has AsyncCallExpr) AND _check_contracts.py:650-681 (missing AsyncCallExpr). **Keep checker.py version, delete _check_contracts.py version**, have ContractCheckMixin call the shared function.
- `_collect_lambda_captures()` — checker.py:3595-3649 (has StringInterp) AND _check_types.py:427-480. **Keep checker.py version, delete _check_types.py version**, MRO resolves to Checker method.

**Optional** (no duplication, just consistency): Create generic `walk_expr(expr, visitor)` in new `_expr_walker.py` and rewrite `_expr_references_name` (_check_contracts.py:54-89) and `_walk_expr` (checker.py:210-248) to use it.

**Test**: `pytest tests/test_checker.py tests/test_checker_contracts.py tests/test_checker_types.py tests/test_checker_match.py -x`

### 1b. Cast/Unwrap Helpers for Emitter

**Problem**: The 3-way cast pattern (is_pointer / is_struct / intptr_t) appears **27+ times** across `_emit_calls.py` and `_emit_exprs.py`. Helpers `_hof_box` (line 1508) and `_hof_unbox` (line 1520) already exist but aren't used consistently.

**Steps**:
1. Make `_hof_box`/`_hof_unbox` accessible to both `_emit_calls.py` and `_emit_exprs.py` (move to base class or module-level)
2. Replace all 27 inline `(void*)(intptr_t)` / `({type})(intptr_t)` patterns with helper calls
3. Add `_cast_unwrap_option(expr, inner_ct)` for the Option-specific unwrap seen at _emit_exprs.py:867-873, 898-904, 934-940, 1286-1292

**Test**: `pytest tests/test_c_emitter.py` + all `tests/test_*_runtime_c.py`

### 1c. Type-to-String Dispatch Table

**Problem**: 11+ elif branches mapping type names to `prove_string_from_*` functions, duplicated in _emit_exprs.py:1249-1302 (string interp), _emit_exprs.py:335-357 (`_to_string_func`), and _emit_calls.py:2283-2309 (HOF lambda, already a local dict `_STRING_DISPATCH`).

**Steps**:
1. Create module-level `_TYPE_TO_STRING_FUNC` dict consolidating all three locations
2. Refactor `_to_string_func()` and `_emit_string_interp()` to use single dict lookup
3. Replace local `_STRING_DISPATCH` in _emit_calls.py with reference to shared dict

**Test**: `pytest tests/test_c_emitter.py tests/test_format_runtime_c.py -x`

---

## Phase 2: God Method Decomposition — Emitter

### 2a. `_emit_call()` — 717 lines (_emit_calls.py:787-1503)

**Problem**: 21 consecutive if-statements for HOF dispatch + stdlib/local/constructor call handling all in one method.

**Steps**:
1. Create dispatch dict:
   ```python
   _HOF_DISPATCH: dict[str, tuple[int, str]] = {
       "map": (2, "_emit_hof_map"),
       "filter": (2, "_emit_hof_filter"),
       "each": (2, "_emit_hof_each"),
       "all": (2, "_emit_hof_all"),
       "any": (2, "_emit_hof_any"),
       "find": (2, "_emit_hof_find"),
       "reduce": (3, "_emit_hof_reduce"),
       "par_map": (2, "_emit_hof_par_map"),
       "par_filter": (2, "_emit_hof_par_filter"),
       "par_reduce": (3, "_emit_hof_par_reduce"),
       "par_each": (2, "_emit_hof_par_each"),
       "__fused_map_filter": (3, "_emit_fused_map_filter"),
       # ... 10 fused entries
   }
   ```
2. Replace lines 806-848 with 4-line dict lookup
3. Extract `_emit_stdlib_call(name, args, expr)` for stdlib function resolution path
4. Extract `_emit_local_call(name, args, expr)` for local/imported functions
5. Extract `_emit_constructor_call(name, args, expr)` for TypeIdentifierExpr constructors

### 2b. `_emit_match_expr()` — 345 lines (_emit_exprs.py:760-1104)

**Problem**: Option/Result/Algebraic/literal matching all in one method with parallel code paths.

**Steps**:
1. Extract `_emit_option_match_expr(subj, subj_type, arms, result_tmp, result_type)`
2. Extract `_emit_result_match_expr(...)`
3. Extract `_emit_algebraic_match_expr(...)`
4. Extract `_emit_literal_match_expr(...)`
5. Main method becomes a type dispatcher

### 2c. `_emit_hof_lambda()` — 337 lines (_emit_calls.py:2247-2583)

**Steps**:
1. Extract `_emit_hof_lambda_from_funcref(expr, elem_type, kind)` for function-reference wrappers
2. Extract `_emit_hof_lambda_from_lambda(expr, elem_type, kind, accum_type)` for lambda bodies
3. Keep `_emit_hof_lambda` as dispatcher

**Test for all of Phase 2**: Full `pytest tests/test_*_runtime_c.py -x` (compiles and runs .prv programs end-to-end)

---

## Phase 3: God Method Decomposition — Checker

### 3a. `_infer_call()` — 522 lines (_check_calls.py:77-599)

**Steps**:
1. Extract `_infer_hof_call(expr, hof_name)` — lines 100-170 (HOF builtin element-type inference, sets `_hof_param_types`)
2. Extract `_resolve_and_check_call(name, arg_types, expr)` — lines 245-461 (overload resolution, arity checking)
3. Extract `_post_resolve_call_checks(sig, expr, arg_types, ret)` — lines 462-598 (ownership, verb validation, serialization)

### 3b. `_check_function()` — 378 lines (checker.py:1432-1810)

14 phases → extract 4 helpers:
1. `_setup_function_params(fd)` — lines 1443-1500 (param registration, borrow inference, With constraints)
2. `_setup_function_scope(fd)` — lines 1502-1556 (requires narrowings, implicit variables for renders/listens)
3. `_check_function_annotations(fd)` — lines 1693-1730 (intent prose, explain conditions, recursion, proof verification)
4. `_finalize_function_check(fd)` — lines 1732-1810 (mutation testing, survivor warnings, unused vars, scope cleanup)

### 3c. `_register_type()` — 167 lines (checker.py:833-999)

isinstance chain → extract per-type handlers:
1. `_register_record_type(td, body)` — lines 856-861
2. `_register_algebraic_type(td, body)` — lines 863-919 (largest, handles inheritance)
3. `_register_lookup_type(td, body)` — lines 936-982 (store-backed and static paths)
4. Keep RefinementTypeDef (3 lines) and BinaryDef (6 lines) inline

**Test for all of Phase 3**: `pytest tests/test_checker.py tests/test_checker_types.py tests/test_checker_contracts.py tests/test_diagnostics.py -x`

---

## Phase 4: Dispatch Tables

### 4a. `_infer_expr()` Literal Dispatch (_check_types.py:86-156)

Replace 10 literal-type if-elif branches (lines 88-107) with:
```python
_LITERAL_TYPES = {
    IntegerLit: INTEGER, DecimalLit: DECIMAL, FloatLit: FLOAT,
    StringLit: STRING, BooleanLit: BOOLEAN, CharLit: CHARACTER,
    RegexLit: STRING, PathLit: STRING, TripleStringLit: STRING,
    RawStringLit: PrimitiveType("String", ((None, "Reg"),)),
}
```

### 4b. Parser Annotation Dispatch (parser.py:515-607) — OPTIONAL

20 annotation types in if-elif. Many are 2-3 line blocks. Dispatch table may not improve readability here — skip unless there's appetite for it.

**Test**: `pytest tests/test_checker_types.py tests/test_parser.py -x`

---

## Phase 5: Data Externalization

### 5a. stdlib_loader.py Registration Data (1350+ lines of boilerplate)

23 `_register_module()` calls with repetitive c_map/overloads dicts. **Approach**: Extract c_map and overloads data into a companion `_stdlib_data.py` file with compact module-level dicts. Keep registration logic in `stdlib_loader.py`. This avoids new file format dependencies while reducing noise.

### 5b. c_runtime.py `_RUNTIME_FUNCTIONS` (560 lines of dict data)

Move to `data/runtime_functions.json`, load with `importlib.resources`. Also: compile regex at module level (`_FUNC_CALL_RE = re.compile(r"\b([a-zA-Z_][a-zA-Z0-9_]*)\s*\(")`) instead of per-call at line 731.

**Test**: `pytest tests/test_c_types.py tests/test_c_emitter.py tests/test_stdlib_loader.py -x`

---

## Phase 6: Minor Optimizations & Cleanup

### 6a. Performance
- Compile regex in c_runtime.py at module level (line 731)
- Lexer: consolidate `_lex_hex_digits`/`_lex_bin_digits`/`_lex_oct_digits` (lines 523-533) into parameterized `_lex_digits(text, valid_chars: frozenset)`
- Consolidate `has_own_modifier`/`has_mutable_modifier` (types.py:630-645) into `has_modifier(ty, name)` with thin wrappers

### 6b. Duplicate Cleanup
- `_LIT_KINDS` in parser.py: defined 3 times (lines 1718, 1888, 1939) → module-level constant
- `_lex_doc_comment`/`_lex_line_comment` (lexer.py:206-233): parameterize into `_lex_comment(prefix_len, kind)`

### 6c. NLP Lazy Imports
- Move `_body_gen` and `_nl_intent` imports in lsp.py to inside methods that use them (cold-start perf)

**Test**: Full `pytest tests/ -x`

---

## Phase Dependencies

```
Phase 1 (helpers) ──> Phase 2 (emitter decomp) ──┐
                  ──> Phase 3 (checker decomp) ──┤──> Phase 4 (dispatch) ──> Phase 5 (data) ──> Phase 6 (cleanup)
                                                  │
                      (2 and 3 are independent)   │
```

## Effort Summary

| Phase | Effort | Risk | Description |
|-------|--------|------|-------------|
| 1a | S | Low | Deduplicate tree walkers |
| 1b | S-M | Medium | Consolidate 27 cast/unwrap sites |
| 1c | S | Low | Type-to-string dispatch table |
| 2a | L | Medium | Decompose `_emit_call` (717 lines) |
| 2b | M | Medium | Decompose `_emit_match_expr` (345 lines) |
| 2c | M | Low | Decompose `_emit_hof_lambda` (337 lines) |
| 3a | L | Medium | Decompose `_infer_call` (522 lines) |
| 3b | M | Low | Decompose `_check_function` (378 lines) |
| 3c | S | Low | Decompose `_register_type` (167 lines) |
| 4a | S | Low | Literal type dispatch table |
| 4b | S | Low | Parser annotation dispatch (optional) |
| 5a | M | Low | stdlib_loader data extraction |
| 5b | S | Low | c_runtime data externalization |
| 6a-c | S | Low | Minor perf + cleanup |

**Total**: ~12-16 working days

## Verification Strategy

Every commit:
1. `cd prove-py && python -m pytest tests/ -x` — all 68 test files pass
2. Emitter changes: also `pytest tests/test_*_runtime_c.py -x` (full compile+run)
3. Checker changes: also `pytest tests/test_diagnostics.py tests/test_diagnostic_links.py -x`
4. Never modify .prv files

## Critical Files

| File | LOC | Phases |
|------|-----|--------|
| `_emit_calls.py` | 3584 | 1b, 1c, 2a, 2c |
| `checker.py` | 4403 | 1a, 3b, 3c |
| `_emit_exprs.py` | 1674 | 1b, 1c, 2b |
| `_check_calls.py` | 1101 | 3a |
| `_check_contracts.py` | 1251 | 1a |
| `_check_types.py` | 904 | 1a, 4a |
| `stdlib_loader.py` | 1470 | 5a |
| `c_runtime.py` | 890 | 5b, 6a |
| `parser.py` | 2925 | 4b, 6b |
| `lexer.py` | 703 | 6a, 6b |
| `types.py` | 658 | 6a |
