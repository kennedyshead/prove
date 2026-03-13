# C Runtime Bug Fixes & Optimizations

**Date:** 2026-03-13
**Status:** Planned (not yet implemented)
**Scope:** `prove-py/src/prove/runtime/` — the C runtime that compiled Prove programs link against

## Context

A deep analysis of the Prove C runtime found 15 bugs (3 critical, 6 high, 6 medium)
and 7 optimization opportunities. This document triages each item against a key design
principle: **the Prove compiler is the primary safety mechanism**. The runtime should
only guard against things the compiler cannot enforce.

### What the compiler already handles (do NOT duplicate in runtime)

- **Type safety** — the checker enforces types at compile time
- **Array/list bounds** — the compiler verifies indices or emits safe iteration patterns
  (confirmed in `_emit_calls.py:1028`: "Direct array access — compiler verified bounds")
- **Null safety** — Option/Result types handle nullability at the language level
- **Refinement constraints** — checked statically by the checker

### What only the runtime can handle (MUST be in runtime)

- **OOM / system failures** — unpredictable at compile time
- **C undefined behavior (UB)** — the compiler emits C code, so the emitted C must be
  well-defined for all inputs the language allows
- **External input** — data from OS, network, files, child processes
- **Concurrency hazards** — `prove_par_map` uses pthreads; race conditions in C
  internals are invisible to the Prove type system
- **Logic bugs in runtime C code** — the compiler can't verify its own runtime

---

## Bug Triage

### Critical (use-after-free, deadlock, data loss)

#### #1 — Immortal refcount corruption
- **File:** `prove_runtime.h:19-32`
- **Problem:** `prove_retain()` and `prove_release()` don't guard against immortal
  objects (refcount set to `INT32_MAX`). Multiple files create immortal strings —
  `prove_string.c:82-84` (`_str_true`/`_str_false`), `prove_parse_toml.c:76-88`
  (tag strings). Every `prove_release()` call on these decrements toward zero;
  every `prove_retain()` overflows toward `INT32_MIN`. In a long-running program,
  this leads to use-after-free.
- **Category:** C undefined behavior (integer overflow)
- **Fix:** Guard both functions with `if (h->refcount >= INT32_MAX) return;`

#### #2 — Pipe deadlock in process execution
- **File:** `prove_input_output.c:138-151`
- **Problem:** `prove_io_system_inputs()` reads stdout to completion, then reads stderr.
  If the child writes enough stderr to fill the OS pipe buffer (~64KB) while also writing
  to stdout, both processes deadlock: child blocks on stderr write, parent blocks on
  stdout read.
- **Category:** OS-level concern (pipe buffer scheduling)
- **Fix:** Use `poll()` to read both pipes concurrently. This also addresses
  optimization O7 (sequential pipe reads).

#### #3 — Binary data truncation in process output
- **File:** `prove_input_output.c:139-141`
- **Problem:** `prove_text_write_cstr()` stops at embedded NUL bytes. Any process output
  containing `\0` is silently truncated.
- **Category:** External input handling
- **Fix:** Use `prove_text_write()` with a `Prove_String` wrapping the exact `n` bytes
  read, instead of `prove_text_write_cstr()`.

### High (C UB, wrong results, crashes)

#### #4 — No NULL check on array malloc
- **File:** `prove_array.c:6-14`
- **Verdict:** **FIX**
- **Problem:** Both `malloc` calls in `prove_array_new()` lack NULL checks. Also,
  `length * elem_size` can overflow. Every other allocator in the runtime handles OOM
  cleanly (`prove_alloc`, `prove_list_new`). Same issue in `prove_array_set()`.
- **Category:** OOM handling
- **Fix:** Add NULL checks and overflow guard. Panic on failure like the rest of the runtime.

#### #5 — No bounds checking in array get/set
- **File:** `prove_array.c:25-27,41-49,60-63`
- **Verdict:** **SKIP — compiler handles this**
- **Reasoning:** The emitter comment at `_emit_calls.py:1028` confirms the compiler
  verifies array bounds. Adding runtime checks would be redundant double-implementation.
  Note that `prove_list_get()` DOES have runtime bounds checks, but lists are dynamically
  sized and used in contexts (HOFs, stdlib) where the compiler may not statically verify
  indices. Arrays are fixed-size and compiler-verified.

#### #6 — Integer truncation in random modulus
- **File:** `prove_random.c:68,85`
- **Verdict:** **FIX**
- **Problem:** `rand() % (int)list->length` truncates `int64_t` length to `int` (UB when
  length > INT_MAX). `rand()` only returns 15-31 bits, creating modulo bias.
- **Category:** C undefined behavior (truncation)
- **Fix:** Replace with proper 64-bit modulo using combined `rand()` calls.

#### #7 — Wrong error reporting for DNS failures
- **File:** `prove_network.c:86`
- **Verdict:** **FIX**
- **Problem:** `_socket_error("resolve")` calls `strerror(errno)`, but `getaddrinfo()`
  doesn't set `errno` — it returns its own error codes. Error messages will be misleading.
- **Category:** External input (POSIX API misuse)
- **Fix:** Use `gai_strerror(gai)` instead of `strerror(errno)`.

#### #8 — Signed overflow on INT64_MIN in formatting
- **File:** `prove_format.c:64,77,104`
- **Verdict:** **FIX**
- **Problem:** `(uint64_t)(-n)` when `n == INT64_MIN` is undefined behavior. INT64_MIN
  is `-9223372036854775808` and negating it in signed `int64_t` overflows.
- **Category:** C undefined behavior
- **Fix:** Use `(uint64_t)(-(n + 1)) + 1` or handle INT64_MIN as a special case.

#### #9 — NULL pointer passed to memcpy in hash functions
- **File:** `prove_hash_crypto.c:323-326`
- **Verdict:** **FIX**
- **Problem:** Hashing empty data calls `_sha256(NULL, 0, hash)`. Inside the function,
  `memcpy(block, data + i, rem)` where `data=NULL` and `rem=0` is undefined behavior per
  C standard, even with size 0. Same issue in `_sha512` and `_blake3`.
- **Category:** C undefined behavior
- **Fix:** Guard `memcpy` calls with `if (rem > 0)`.

### Medium (leaks, logic errors, portability, thread safety)

#### #10 — Thread-unsafe static initialization
- **Files:** `prove_string.c:76-87`, `prove_parse_toml.c:73-89`
- **Verdict:** **FIX**
- **Problem:** Static string singletons (`_str_true`/`_str_false`, `_tag_*`) use
  check-then-write patterns without synchronization. With `prove_par_map` using pthreads,
  concurrent calls can create duplicate objects or read half-initialized pointers.
  The compiler enforces "pure functions only" for par_map, but `prove_string_from_bool()`
  IS pure from the language level — the race condition is hidden in the C implementation.
- **Category:** Concurrency hazard
- **Fix:** Initialize these strings in `prove_runtime_init()` (called once at startup,
  guaranteed single-threaded). This is simpler and more reliable than `pthread_once`.

#### #11 — Memory leak in deserialization error path
- **File:** `prove_store.c:164-167`
- **Verdict:** **FIX**
- **Problem:** When reading column names fails partway through, already-read
  `Prove_String*` objects in `col_names[]` are leaked — only the array pointer is freed.
- **Category:** Error path correctness in C code
- **Fix:** Free already-read strings before returning NULL.

#### #12 — Mutation of input diff during merge
- **File:** `prove_store.c:452-482`
- **Verdict:** **FIX**
- **Problem:** `prove_store_merge()` modifies `local->changed[l].new_value` (line 480)
  and `local->added[l].values[col]` (line 520) in place. Callers holding references to
  the original diff see corrupted data.
- **Category:** Internal API contract violation (aliasing bug)
- **Fix:** Copy values before modifying them.

#### #13 — No NULL check after region alloc in list
- **File:** `prove_list.c:17-18`
- **Verdict:** **FIX**
- **Problem:** `prove_region_alloc()` can return NULL. The heap-backed `prove_list_new()`
  already panics on NULL — the region variant should be consistent.
- **Category:** OOM handling
- **Fix:** Add NULL check + panic after both `prove_region_alloc` calls.

#### #14 — Wrong bounds check in merge addition conflict
- **File:** `prove_store.c:503-508`
- **Verdict:** **FIX**
- **Problem:** Checks `col < local->added_count` but iterates up to `base->column_count`.
  `added_count` is the number of added *variants*, not columns. Silently skips values
  when there are fewer added variants than columns.
- **Category:** Logic error in C code
- **Fix:** The values array has `base->column_count` entries — check against that, or
  simply remove the redundant check since the loop variable already iterates within
  `base->column_count`.

#### #15 — Non-portable timegm fallback
- **File:** `prove_time.c:59-63`
- **Verdict:** **FIX**
- **Problem:** The `#if defined(_GNU_SOURCE) || defined(__linux__) || defined(__APPLE__)`
  guard for `timegm` is fragile. The file does NOT define `_GNU_SOURCE`, so on strict
  Linux builds without it pre-defined, the code falls through to `mktime()` which uses
  local timezone instead of UTC, giving wrong results.
- **Category:** Portability
- **Fix:** Define `_GNU_SOURCE` at the very top of `prove_time.c` (before any includes),
  or implement a portable UTC-to-epoch conversion.

---

## Optimizations

#### O1 — Range uses push in a pre-known-size loop (**DO**)
- **File:** `prove_list_ops.c:186-189`
- `prove_list_ops_range()` calls `prove_list_push()` in a loop when final size is already
  computed. Use direct `result->data[i]` assignment and set `result->length = count`.
  Same applies to `prove_list_ops_range_step`.

#### O2 — Split fast path for single-char separator (**DO**)
- **File:** `prove_text.c:53-87`
- `prove_text_split()` always calls `memmem()`. For single-character separators (the
  common case), `memchr()` is significantly faster due to no setup overhead.

#### O3 — Array copy-on-write when refcount is 1 (**DO**)
- **File:** `prove_array.c:41-49`
- `prove_array_set()` always copies the entire array. When `arr->header.refcount == 1`,
  mutate in-place instead: `if (arr->header.refcount == 1) return prove_array_set_mut(arr, idx, val);`

#### O4 — O(n^2) variant lookup in store (**DEFER**)
- **File:** `prove_store.c:285-290`
- `_find_variant()` is O(n) linear scan called O(n) times. Would need a temporary hash
  table. Low priority — store tables are typically small.

#### O5 — Weak PRNG (**DEFER**)
- **File:** `prove_random.c`
- `rand()/srand()` is weak but intentionally simple. Upgrading to `getrandom()` changes
  behavior and needs fallback paths. The truncation bug (#6) is the immediate fix.
  Defer PRNG quality to a future stdlib revision.

#### O6 — 16-slot regex cache is small (**DEFER**)
- **File:** `prove_pattern.c`
- 16 direct-mapped slots means frequent recompilation for programs using many patterns.
  Need profiling data to pick the right size. Not urgent.

#### O7 — Sequential pipe reads (**COVERED by #2**)
- Already addressed by the pipe deadlock fix, which requires `poll()`-based concurrent
  reading of both stdout and stderr.

---

## Implementation Phases

### Phase 1: Critical (highest impact, smallest blast radius)
1. #1 — Immortal refcount guard (4 lines in `prove_runtime.h`)
2. #2 + #3 + O7 — Pipe rewrite with `poll()` (in `prove_input_output.c`)

### Phase 2: High (C UB and wrong error messages)
3. #4 — Array OOM checks (`prove_array.c`)
4. #6 — Random truncation fix (`prove_random.c`)
5. #7 — DNS error with `gai_strerror()` (`prove_network.c`)
6. #8 — INT64_MIN handling (`prove_format.c`)
7. #9 — NULL memcpy guard (`prove_hash_crypto.c`)

### Phase 3: Medium (leaks, logic errors, portability)
8. #10 — Thread-safe static init (`prove_string.c`, `prove_parse_toml.c`)
9. #11 — Deserialization leak (`prove_store.c`)
10. #12 — Merge input mutation (`prove_store.c`)
11. #13 — List region NULL check (`prove_list.c`)
12. #14 — Merge bounds fix (`prove_store.c`)
13. #15 — timegm portability (`prove_time.c`)

### Phase 4: Optimizations
14. O1 — Range pre-alloc (`prove_list_ops.c`)
15. O2 — Split fast path (`prove_text.c`)
16. O3 — Array COW (`prove_array.c`)

---

## Tally

| Category | Total | Fix | Skip | Defer |
|----------|-------|-----|------|-------|
| Critical | 3 | 3 | 0 | 0 |
| High | 6 | 5 | 1 (#5 bounds) | 0 |
| Medium | 6 | 6 | 0 | 0 |
| Optimizations | 7 | 3 (O1,O2,O3) | 0 | 3 (O4,O5,O6) |
| **Total** | **22** | **17** | **1** | **3** |

- **Skipped:** #5 (array bounds checking) — compiler already verifies this
- **Deferred:** O4, O5, O6 — need profiling data or represent larger design decisions
- **Covered:** O7 — subsumed by bug #2 fix

---

## Documentation & AGENTS Updates

When this work is implemented:

- **No public-facing docs changes** — these are internal C runtime fixes with no visible
  language or API surface changes.
- **`AGENTS.md`** — Add two conventions to the C Runtime section:
  - "Immortal objects (refcount `INT32_MAX`) must guard `prove_retain`/`prove_release`
    with `if (h->refcount >= INT32_MAX) return;`"
  - "Static singleton strings must be initialized in `prove_runtime_init()`, not lazily
    on first call, to avoid races with `prove_par_map`."
  - "`getaddrinfo()` errors must be reported with `gai_strerror()`, not `strerror(errno)`."
- Run e2e tests and the C runtime test suite (`python -m pytest tests/test_*_runtime_c.py`)
  after each phase.
