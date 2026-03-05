# C Runtime Optimization Plan

## Context

The Prove runtime is ~4,000 lines of hand-written C across 20 `.c` files in `/workspace/prove-py/src/prove/runtime/`. It provides reference-counted strings, lists, tables, file I/O, pattern matching, JSON/TOML parsing, and more.

The build system performs **runtime library stripping** (`c_runtime.py`) — only C files actually used by a program are compiled. Any new cross-module dependencies (e.g., adding `#include "prove_text.h"` to `prove_input_output.c`) must be accounted for in `_RUNTIME_FUNCTIONS` in `c_runtime.py` so the stripping logic includes them.

Compilation uses `-O2` in release mode (`c_compiler.py:47`) but no further tuning (no LTO, `-march`, or strict-aliasing flag).

---

## Findings by Priority

### P0 — Bugs (correctness)

**1. `prove_region_exit()` frees entire frame chain** — `prove_region.c:77-88`
- Walks `frame->prev` to NULL and frees everything — identical to `prove_region_free()`.
- Should only free frames pushed since the matching `prove_region_enter()`.
- Currently unused in runtime, but designed for V2.0.

**2. Pattern module 4KB buffer truncation** — `prove_pattern.c:28-30`
- All pattern functions copy text/pattern into `char [4096]` stack buffers. Inputs >4095 bytes are silently truncated.
- `prove_pattern_replace()` also has a fixed `char result[8192]` output buffer (line 120).

**3. Path normalize limits** — `prove_path.c:111, 136`
- Fixed `char *segments[256]` array: paths with >256 components silently truncated.
- Fixed `char result[4096]` output buffer.

**4. `prove_string_concat()` null fast-path doesn't retain** — `prove_string.c:23-24`
- When `a` is NULL returns `b` directly; when `b` is NULL returns `a` directly — no `prove_retain()`.
- Caller releasing the result could free the original string prematurely.

**5. JSON parser string buffer limited to 4KB** — `prove_parse_json.c:46`
- `_json_parse_string()` uses `char buf[4096]`. Strings >4095 chars are truncated.
- Same in TOML parser: `prove_parse_toml.c:223`.

### P1 — High-Impact Performance

**6. JSON/TOML emitters use O(n²) string concatenation** — `prove_parse_json.c:242-244`, `prove_parse_toml.c:407-413`
```c
static void _jappend(Prove_String **out, const char *cstr) {
    *out = prove_string_concat(*out, prove_string_from_cstr(cstr));
}
```
- Every `_jappend`/`_append` call allocates a new `Prove_String` from `cstr`, then allocates a new concat result copying the entire accumulated output.
- Emitting a 100-key JSON object does ~300+ concat calls, each copying growing output. Also leaks both intermediate strings (no release).
- **Fix**: Replace with `Prove_Builder` (already exists in `prove_text.c`). Write to builder, call `prove_text_build()` once at the end.

**7. Process I/O uses O(n²) string concat loop** — `prove_input_output.c:166-180`
```c
while ((n = read(out_pipe[0], buf, sizeof(buf))) > 0) {
    Prove_String *chunk = prove_string_new(buf, (int64_t)n);
    Prove_String *tmp = prove_string_concat(out_str, chunk);
    out_str = tmp;  // old out_str and chunk leaked
}
```
- Same O(n²) pattern. Also leaks intermediate strings.
- **Fix**: Use `Prove_Builder`.

**8. `prove_text_split()` uses manual byte scan** — `prove_text.c:71-76`
- Hand-rolled `memcmp` loop instead of `memmem()` which uses SIMD on glibc/musl.
- **Fix**: Replace inner loop with `memmem()`.

**9. Pattern regex recompilation on every call** — `prove_pattern.c` (all 5 functions)
- Every call does `regcomp()` + `regfree()`. In a loop, same pattern is recompiled N times.
- **Fix**: Add a small direct-mapped regex cache (4 slots, keyed by pattern string hash).

**10. File I/O mallocs for every path** — `prove_input_output.c:17, 55, 86, 98-103`
- Every file op mallocs a C string copy just to null-terminate the path.
- But `Prove_String.data` is *already* null-terminated (see `prove_string_new` line 12).
- **Fix**: Use `s->data` directly. Eliminates ~6 mallocs per file operation.

### P2 — Medium-Impact Performance

**11. List slice/reverse/sort copy via push loop** — `prove_list_ops.c:99-104, 115-120, 153-177`
- All three pre-allocate correct capacity but push elements one-by-one (each with bounds check).
- **Fix**: Single `memcpy` for slice and sort; direct indexed writes for reverse.

**12. `prove_string_from_bool()` allocates every time** — `prove_string.c:57-59`
- `prove_string_from_cstr("true")` / `prove_string_from_cstr("false")` allocates a new refcounted string per call.
- **Fix**: Return static strings with pinned refcount (INT32_MAX so release never frees).

**13. `prove_value_tag()` allocates every time** — `prove_parse_toml.c:64-74`
- Returns `prove_string_from_cstr("text")` etc. each call.
- **Fix**: Same static string technique as item 12.

### P3 — Compiler Flag Improvements

**14. Missing `-flto`** — `c_compiler.py:47`
- All runtime `.c` files compiled in one `gcc` invocation. LTO enables cross-file inlining.
- **Fix**: Add `-flto` when `optimize=True`.

**15. Missing `-fno-strict-aliasing`** — `c_compiler.py`
- Runtime casts between `void*`, `Prove_Header*`, and concrete types extensively.
- **Fix**: Add `-fno-strict-aliasing` to prevent potential miscompilation at `-O2`.

---

## Implementation Order

| # | Change | Files | Impact |
|---|--------|-------|--------|
| 1 | Use `s->data` directly (already null-terminated) | `prove_input_output.c` | Eliminates ~6 mallocs per file op |
| 2 | Fix JSON/TOML emitters to use Builder | `prove_parse_json.c`, `prove_parse_toml.c` | O(n) emit, fixes memory leaks |
| 3 | Fix process I/O to use Builder | `prove_input_output.c` | O(n) subprocess output, fixes leaks |
| 4 | Replace manual scan with `memmem()` | `prove_text.c` | SIMD-accelerated string splitting |
| 5 | Fix pattern 4KB buffer limits | `prove_pattern.c` | Correctness: handles large text |
| 6 | Fix JSON/TOML parser string buffer limits | `prove_parse_json.c`, `prove_parse_toml.c` | Correctness: handles long strings |
| 7 | Fix path normalize limits | `prove_path.c` | Correctness: handles deep paths |
| 8 | Bulk memcpy for list slice/reverse/sort | `prove_list_ops.c` | Fewer function calls |
| 9 | Add regex compilation cache | `prove_pattern.c` | Avoid repeated regcomp in loops |
| 10 | Static "true"/"false" and tag strings | `prove_string.c`, `prove_parse_toml.c` | Eliminate allocation per call |
| 11 | Fix string concat null fast-path (retain) | `prove_string.c` | Correctness: prevent double-free |
| 12 | Fix region allocator `exit()` | `prove_region.c` | Correctness for V2.0 |
| 13 | Add `-flto` and `-fno-strict-aliasing` | `c_compiler.py` | Better optimization, safety |

## Build System Considerations

`prove_text.h`/`prove_text.c` added to the always-included core runtime files in `c_runtime.py`, since the Builder API is now used internally by `prove_parse_json.c`, `prove_parse_toml.c`, `prove_input_output.c`, and `prove_pattern.c`.

## Verification

- `cd /workspace/prove-py && python -m pytest tests/ -v` — all 747+ tests must pass
- `ruff check src/ tests/` — no lint regressions
- Build and run example programs to verify correct output
