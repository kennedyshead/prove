# Comptime Polish — Remaining Work

## Status

Comptime execution is functional. `comptime` expressions work in any position
(variable declarations, function bodies). The tree-walking interpreter evaluates
pure constant expressions and `read()` for file I/O. Results are inlined as C
constants at compile time.

Two items remain for V1.0 polish.

---

## 1. Build Dependency Tracking

### Problem

Files accessed via comptime `read("routes.json")` should become build
dependencies. Currently, if `routes.json` changes, the project is not
automatically rebuilt — the developer must manually trigger a rebuild.

### Current State

- `ComptimeInterpreter.evaluate()` handles `read()` calls (`interpreter.py`)
- The interpreter reads the file and returns its contents as a string
- The file path is NOT recorded anywhere
- `builder.py` has no mechanism to track comptime file dependencies

### Implementation

1. **Track read paths in interpreter** — Add a `read_files: list[str]` field
   to `ComptimeInterpreter`. Each `read()` call appends the resolved absolute
   path. After evaluation, the builder can query `interpreter.read_files`.

2. **Wire into builder** — In `builder.py`, after the optimizer runs (which
   calls the interpreter for comptime evaluation), collect the list of files
   read during comptime. Store them alongside the build outputs.

3. **Rebuild check** — On subsequent builds, check if any tracked comptime
   dependency has a newer mtime than the build output. If so, trigger a
   rebuild even if the `.prv` source is unchanged.

4. **Storage format** — Write comptime deps to a `.prove-deps` file in the
   build directory (one path per line). Read on next build to check staleness.

### Files to modify

- `src/prove/interpreter.py` — Add `read_files` tracking
- `src/prove/optimizer.py` — Expose `read_files` after optimization
- `src/prove/builder.py` — Collect deps, write `.prove-deps`, check on rebuild

### Tests

- Unit test: interpreter records file paths on `read()` calls
- Unit test: builder detects stale comptime dep and triggers rebuild
- E2e test: project with `comptime read("data.txt")` rebuilds when data changes

---

## 2. Comptime Match for Conditional Compilation

### Problem

The docs (`compiler.md`) show:

```prove
MAX_CONNECTIONS as Integer = comptime
    match platform()
        "linux" => 4096
        "macos" => 2048
        _ => 1024
```

The `platform()` builtin exists in the interpreter. The `comptime` expression
evaluates correctly. However, this specific pattern (comptime match for
conditional compilation) has not been verified end-to-end — the match inside
a comptime context may not emit correct C constants for all arm types.

### Current State

- `platform()` is implemented in `interpreter.py` (returns OS name string)
- `comptime` expressions evaluate and inline as C constants
- Match expressions inside comptime blocks should work via the interpreter's
  `_eval_match()` method
- No dedicated e2e test verifies this pattern

### Implementation

1. **Verify existing code path** — Write an e2e test with the exact pattern
   from the docs. If it works, this item is just a test addition.

2. **If broken, fix interpreter match** — The interpreter's `_eval_match()`
   may need to handle string comparison for platform detection. Ensure match
   arms with string literals evaluate correctly.

3. **Add `arch()` builtin** — Complement `platform()` with `arch()` returning
   the CPU architecture (`"x86_64"`, `"aarch64"`, etc.). Useful for
   conditional compilation of architecture-specific constants.

### Files to modify

- `src/prove/interpreter.py` — Verify/fix `_eval_match()`, add `arch()`
- `examples/comptime_demo/` — Add conditional compilation example

### Tests

- E2e test: comptime match on `platform()` produces correct constant
- E2e test: comptime match with wildcard arm
- Unit test: interpreter `arch()` returns valid architecture string

---

## Exit Criteria

- [ ] Comptime `read()` files tracked as build dependencies
- [ ] Stale comptime deps trigger automatic rebuild
- [ ] `.prove-deps` file written to build directory
- [ ] Comptime match with `platform()` verified end-to-end
- [ ] `arch()` builtin added to interpreter
- [ ] Docs accurate (remove "files tracked as build dependencies" claim
      from compiler.md until implemented — **done**, removed in this session)
