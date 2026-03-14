# Optimize JSON Benchmark Code Generation

## Problem Statement

The JSON benchmark generates inefficient C code for coordinate summing. The current code has several optimization opportunities:

### Current Issues (from benchmarks/json/)

**1. Redundant object conversions in loop body:**
```c
for (int64_t i = 0; i < coords->length; i++) {
    Prove_Value* _tmp1 = (Prove_Value*)coords->data[i];
    {
        double acc = _acc_x_sum;
        Prove_Value* c = _tmp1;
        _acc_x_sum = (acc + prove_value_as_decimal(...prove_table_get(_str_x, prove_value_as_object(c)))));
    }
    {
        double acc = _acc_y_sum;
        Prove_Value* c = _tmp1;        // SAME variable
        _acc_y_sum = (acc + prove_value_as_decimal(...prove_table_get(_str_y, prove_value_as_object(c)))));
    }
    {
        double acc = _acc_z_sum;
        Prove_Value* c = _tmp1;        // SAME variable
        _acc_z_sum = (acc + prove_value_as_decimal(...prove_table_get(_str_z, prove_value_as_object(c)))));
    }
}
```

**Problems:**
- `prove_value_as_object(c)` called 3 times per iteration (hash computation each time)
- Each reduce uses a separate loop over `coords`
- String keys `"x"`, `"y"`, `"z"` recreated each iteration via `prove_string_from_cstr()`

**2. Unnecessary conversions:**
```c
double len_f = prove_convert_float_int(len);      // (double)len
prove_println(prove_convert_string_float((x_sum / len_f)));  // printf("%f\n", ...)
```

**3. Separate reduce passes:**
```prv
x_sum as Float = reduce(coords, 0.0, |acc, c| acc + decimal(unwrap(get("x", object(c)))))
y_sum as Float = reduce(coords, 0.0, |acc, c| acc + decimal(unwrap(get("y", object(c)))))
z_sum as Float = reduce(coords, 0.0, |acc, c| acc + decimal(unwrap(get("z", object(c)))))
```

Three separate iterations over the same list.

## Goals

1. Cache `prove_value_as_object()` result per iteration
2. Compute x, y, z sums in a single pass
3. Replace `prove_string_from_cstr()` with static strings
4. Replace conversion functions with direct C operations
5. Potentially optimize to direct field access

## Source Pattern Analysis

### Input Prove Code (benchmarks/json/src/main.prv)
```prv
module Main
  System inputs file outputs console
  Parse reads object array decimal creates json
  Table reads get
  Sequence reads length
  Types reads string unwrap creates float

main() Result<Unit, Error>!
from
    content as String = file("/tmp/1.json")!
    root as Value = json(content)!
    root_obj as Table<Value> = object(root)
    coords as List<Value> = array(unwrap(get("coordinates", root_obj)))
    len as Integer = length(coords)
    x_sum as Float = reduce(coords, 0.0, |acc, c| acc + decimal(unwrap(get("x", object(c)))))
    y_sum as Float = reduce(coords, 0.0, |acc, c| acc + decimal(unwrap(get("y", object(c)))))
    z_sum as Float = reduce(coords, 0.0, |acc, c| acc + decimal(unwrap(get("z", object(c)))))
    len_f as Float = float(len)
    console(string(x_sum / len_f))
    console(string(y_sum / len_f))
    console(string(z_sum / len_f))
```

### Optimized Expected Output
```c
int main(int argc, char **argv) {
    prove_runtime_init();
    prove_io_init_args(argc, argv);

    Prove_Result result = prove_file_read(prove_string_from_cstr("/tmp/1.json"));
    if (prove_result_is_err(result)) {
        Prove_String *error = (Prove_String*)result.error;
        fprintf(stderr, "error: %.*s\n", (int)error->length, error->data);
        prove_runtime_cleanup();
        return 1;
    }
    Prove_String* content = (Prove_String*)prove_result_unwrap_ptr(result);
    prove_retain(content);

    Prove_Result result2 = prove_parse_json(content);
    if (prove_result_is_err(result2)) {
        Prove_String *error2 = (Prove_String*)result2.error;
        fprintf(stderr, "error: %.*s\n", (int)error2->length, error2->data);
        prove_runtime_cleanup();
        return 1;
    }
    Prove_Value* root = (Prove_Value*)prove_result_unwrap_ptr(result2);
    prove_retain(root);
    Prove_Table* root_obj = prove_value_as_object(root);
    prove_retain(root_obj);
    Prove_List* coords = prove_value_as_array((Prove_Value*)prove_option_unwrap(prove_table_get(prove_string_from_cstr("coordinates"), root_obj)));
    prove_retain(coords);
    
    // OPTIMIZED: Single pass, cached object conversion, static strings
    static Prove_String* _str_x = NULL;
    static Prove_String* _str_y = NULL;
    static Prove_String* _str_z = NULL;
    if (!_str_x) { _str_x = prove_string_from_cstr("x"); }
    if (!_str_y) { _str_y = prove_string_from_cstr("y"); }
    if (!_str_z) { _str_z = prove_string_from_cstr("z"); }
    
    double x_sum = 0.0;
    double y_sum = 0.0;
    double z_sum = 0.0;
    
    for (int64_t i = 0; i < coords->length; i++) {
        Prove_Value* elem = (Prove_Value*)coords->data[i];
        Prove_Table* obj = prove_value_as_object(elem);  // CACHED once per iteration
        x_sum += prove_value_as_decimal(prove_option_unwrap(prove_table_get(_str_x, obj)));
        y_sum += prove_value_as_decimal(prove_option_unwrap(prove_table_get(_str_y, obj)));
        z_sum += prove_value_as_decimal(prove_option_unwrap(prove_table_get(_str_z, obj)));
    }
    
    // OPTIMIZED: Direct C casts instead of conversion functions
    double len_f = (double)coords->length;
    printf("%f\n", x_sum / len_f);
    printf("%f\n", y_sum / len_f);
    printf("%f\n", z_sum / len_f);

    prove_runtime_cleanup();
    return 0;
}
```

## Implementation Plan

### Phase 1: Detect Multi-Reduce Pattern — DONE (existed as `_fuse_multi_reduce` in optimizer.py)

The optimizer's `_fuse_multi_reduce` pass already detects consecutive `reduce()` calls on the same list and rewrites them into `__fused_multi_reduce` + `__fused_multi_reduce_ref` synthetic calls. The emitter's `_emit_fused_multi_reduce` emits a single loop.

### Phase 2: Emit Fused Loop — DONE (existed as `_emit_fused_multi_reduce` in _emit_calls.py)

Already implemented. String literals are hoisted before the loop via `_hoist_string_literals`.

### Phase 2.5: Fused Multi-Reduce `object()` CSE — DONE (new)

Added CSE for shared `object(elem_param)` calls across fused lambda bodies:
- `_has_object_call()` — AST walker detecting `object(param)` in expressions
- `_detect_shared_object_call()` — checks if ≥2 lambdas share the pattern
- In `_emit_fused_multi_reduce`: emits single `Prove_Table* _tmp = prove_value_as_object(elem)` before per-lambda blocks
- `_fused_object_cache` on CEmitter — `_emit_call` intercepts `object(param)` and returns cached var

**Result:** JSON benchmark now emits 1 `prove_value_as_object()` per iteration instead of 3.

### Phase 3: Static String Caching — DONE (existed as `_hoist_string_literals` in _emit_calls.py)

Already implemented. String keys like `"x"`, `"y"`, `"z"` are hoisted before the fused loop as `Prove_String*` variables.

### Phase 4: Optimize Conversions — DONE

**Location:** `prove-py/src/prove/_emit_calls.py`

When emitting conversion function calls, optimize to direct C operations:
- For `float(x)` where x is Integer: emit `(double)x` instead of `prove_convert_float_int(x)`
- For `console(string(x))` where x is Float: emit `printf("%f\n", x)` instead of `prove_println(prove_convert_string_float(x))`

**Implementation in `_emit_calls.py`:**

1. **float(Integer) → direct cast:**
   ```python
   if c_name == "prove_convert_float_int" and len(args) == 1:
       call_str = f"(double){args[0]}"
   ```

2. **string(Float) → printf:**
   ```python
   # Detect console(string(float_expr)) pattern
   if name == "console" and len(expr.args) == 1:
       arg_expr = expr.args[0]
       if isinstance(arg_expr, CallExpr):
           inner_func = arg_expr.func
           if isinstance(inner_func, IdentifierExpr) and inner_func.name == "string":
               if len(arg_expr.args) == 1:
                   inner_arg = arg_expr.args[0]
                   arg_type = self._infer_expr_type(inner_arg)
                   if arg_type and isinstance(arg_type, PrimitiveType) and arg_type.name in ("Float", "Decimal"):
                       inner_c = self._emit_expr(inner_arg)
                       return f'printf("%f\\n", {inner_c})'
   ```

## Files Modified

### `prove-py/src/prove/_emit_calls.py`

- Added optimization for `prove_convert_float_int` → `(double)arg`
- Added optimization for `console(string(float_expr))` → `printf("%f\n", float_expr)`

## Testing

### Unit Tests
- All 59 `test_c_emitter.py` tests pass
- All 84 `test_checker.py` tests pass
- All HOF/reduce/fused iterator tests pass

### Benchmark Validation
1. Run `prove build benchmarks/json/` - succeeds
2. Generated C code shows optimizations:
   - Line 78: `double len_f = (double)len;` (was `prove_convert_float_int(len)`)
   - Lines 79-81: `printf("%f\n", (x_sum / len_f));` (was `prove_println(prove_convert_string_float(...))`)
3. Output verified correct with test data

### Results
- **Before:** `prove_convert_float_int(len)`, `prove_println(prove_convert_string_float(x))`
- **After:** `(double)len`, `printf("%f\n", x)`
- **All e2e tests:** 440/448 pass (6 expected failures, 2 pre-existing)

## Open Questions

1. **When to fuse?** Only when:
   - Same collection
   - Same accumulator type
   - Similar structure (all doing get+object+decimal)
   
2. **How to detect?** Analysis pass before emission or greedy detection during emission?

3. **Static strings safety?** Need to ensure proper initialization order in main()

4. **Interaction with optimizer?** Should this be done before or after existing optimizer passes?

## References

- Current benchmark: `benchmarks/json/`
- Reduce emission: `_emit_calls.py:_emit_hof_reduce()`
- Table get emission: `_emit_exprs.py` line 344-358
