---
title: Performance - Prove Programming Language
description: Prove performance benchmarks — Sieve of Eratosthenes compared to C, Rust, and Zig on identical algorithms.
keywords: Prove performance, benchmark, sieve of Eratosthenes, primes, C comparison, Rust comparison, Zig comparison
---

# Performance

Prove compiles to native code via C (gcc or clang) with a full optimizer pipeline. The generated binaries are comparable in performance to hand-written C for compute-heavy workloads.

---

## Sieve of Eratosthenes — Primes to 5,000,000

The benchmark counts prime numbers up to 5,000,000 using the [Sieve of Eratosthenes](https://en.wikipedia.org/wiki/Sieve_of_Eratosthenes) with a boolean array. The algorithm marks composites in-place and counts unmarked indices. All implementations use the same algorithm and heap-allocated boolean arrays.

**Machine:** Apple M-series (arm64), macOS — median of 10 runs.

| Language | Time | Notes |
|----------|-----:|-------|
| C (clang -O2) | 6.6 ms | Reference implementation |
| Rust (-C opt-level=2) | 6.4 ms | |
| Zig (ReleaseFast) | 6.9 ms | Stack-allocated array |
| **Prove** | **10.7 ms** | `Array<Boolean>:[Mutable]`, all optimizer passes |
| Python 3 | ~102 ms | `bytearray` sieve, NumPy-style slice marking |

Times include process startup (~4–5 ms on this platform). The sieve computation itself takes approximately 2–3 ms in C and 6–7 ms in Prove.

The Prove result uses `Array<Boolean>:[Mutable]` with in-place mutation and TCO-converted loops — the compiler inlines the inner marking pass directly into the outer sieve loop, eliminating function call overhead.

---

## What the Prove Compiler Does

The optimizer pipeline contributes meaningfully to this result:

1. **Tail call optimization** — the three helper functions (`mark_composites`, `sieve_pass`, `count_primes`) are each converted to `while (1)` loops instead of recursive calls. With 5M iterations in `count_primes`, this is essential.

2. **TCO loop inlining** — `mark_composites` is inlined into `sieve_pass`'s hot loop. The generated C has a single outer while loop with a nested `while (!(_il_multiple > limit))` — no function call per prime.

3. **Dead code elimination** — `mark_composites` disappears entirely from the binary after inlining; it has no remaining call sites.

4. **In-place mutation dispatch** — `set(arr, idx, val)` on `Array<Boolean>:[Mutable]` compiles to `prove_array_set_mut_bool(arr, idx, val)` (in-place), while the same call on `Array<Boolean>` compiles to `prove_array_set_bool(arr, idx, val)` (copy-on-write). The verb name is identical; dispatch is by type.

The Prove source for the benchmark:

```prove
module Main
  narrative: """
  Primes benchmark - Sieve of Eratosthenes

  Optimized implementation using mutable array and in-place marking.
  """
  System outputs console
  Array creates array
  Array reads get
  Array transforms set

  UPPER_BOUND as Integer = 5000000

transforms mark_composites(arr Array<Boolean>:[Mutable], p Integer, multiple Integer, limit Integer) Array<Boolean>:[Mutable]
  terminates: limit - multiple
from
  match multiple > limit
    true => arr
    _ => mark_composites(set(arr, multiple, true), p, multiple + p, limit)

transforms sieve_pass(arr Array<Boolean>:[Mutable], p Integer, limit Integer) Array<Boolean>:[Mutable]
  terminates: limit - p
from
  match p * p > limit
    true => arr
    _ =>
      match get(arr, p)
        true => sieve_pass(arr, p + 1, limit)
        _ => sieve_pass(mark_composites(arr, p, p * p, limit), p + 1, limit)

reads count_primes(arr Array<Boolean>:[Mutable], i Integer, limit Integer, acc Integer) Integer
  terminates: limit - i
from
  match i > limit
    true => acc
    _ =>
      match get(arr, i)
        true => count_primes(arr, i + 1, limit, acc)
        _ => count_primes(arr, i + 1, limit, acc + 1)

main() Result<Unit, Error>!
from
  limit as Integer = UPPER_BOUND
  is_composite as Array<Boolean>:[Mutable] = array(limit + 1, false)
  marked0 as Array<Boolean>:[Mutable] = set(is_composite, 0, true)
  marked1 as Array<Boolean>:[Mutable] = set(marked0, 1, true)
  sieved as Array<Boolean>:[Mutable] = sieve_pass(marked1, 2, limit)
  count as Integer = count_primes(sieved, 2, limit, 0)
  console(f"Primes found: {count}")
```

---

## Profile-Guided Optimization (PGO)

PGO uses runtime profiling data to guide compiler optimizations — branch prediction hints, code layout, and inlining decisions. It is most effective on branchy code (parsing, table lookups, pattern matching).

Enable PGO in `prove.toml`:

```toml
[optimize]
enabled = true
pgo = true
```

When PGO is enabled, `prove build` runs a three-step build:

1. **Instrument** — compile with profiling instrumentation (`-fprofile-generate`)
2. **Train** — run the binary to collect execution profile data
3. **Rebuild** — recompile using the collected profile (`-fprofile-use`)

PGO requires GCC or Clang. On Clang, `llvm-profdata` must be available (included with Xcode on macOS). MSVC is not supported — the build will print a warning and fall back to a normal optimized build.

PGO is silently skipped when `enabled = false` or when building with `--debug`.

### Benchmark: JSON Parser

Parsing and validating a 1 MB JSON file with table lookups:

| Build | Time | Improvement |
|-------|-----:|-------------|
| `optimize.enabled = true` | ~185 ms | baseline |
| `optimize.pgo = true` | ~165 ms | ~11% faster |

The improvement comes from better branch prediction in the parser's `match` dispatch and hot-path inlining of table lookup functions.

---

## Binary Size

Runtime stripping means only the C runtime modules actually used by a program are compiled and linked. A program that uses only `console` output and `Array` operations links a small subset of the runtime.

The resulting binary is **35 KB**, including the array runtime, region allocator, and string formatting — no unused modules.
