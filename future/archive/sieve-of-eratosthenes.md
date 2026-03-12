# Sieve of Eratosthenes Example

**Depends on:** `array-type-and-sequence-rename.md` fully implemented
(specifically `Array<Boolean>:[Mutable]` + `set`).

## Motivation

The primality benchmark currently uses trial division (`is_prime_step` recursive
helper) which is O(n √n). The Sieve of Eratosthenes is O(n log log n) and is the
standard benchmark for demonstrating mutable array performance. It is also the
canonical example showing that `Array<T>:[Mutable]` enables algorithms that are
impossible with immutable `Sequence<T>`.

Expected outcome: Prove sieve should match C sieve within a small constant factor,
unlike the current 500× gap from boxing + trial division.

## Algorithm

```
sieve(limit):
  is_composite = Array<Boolean> of size limit+1, all false
  set is_composite[0] = true
  set is_composite[1] = true
  for p in 2..sqrt(limit):
    if not is_composite[p]:
      for multiple in p*p..limit step p:
        set is_composite[multiple] = true
  count elements where is_composite[i] == false
```

## Prove implementation (target syntax once Array is ready)

```prove
module Main
  narrative: """Sieve of Eratosthenes benchmark"""
  System outputs console
  Array creates array
  Array transforms set
  Array reads get
  Array reads length
  Math reads sqrt

  UPPER_BOUND as Integer = 5000000

  main() Result<Unit, Error>!
  from
      limit as Integer = UPPER_BOUND
      is_composite as Array<Boolean>:[Mutable] = array(limit + 1, false)
      is_composite = set(is_composite, 0, true)
      is_composite = set(is_composite, 1, true)

      // Mark composites — need each over a range, stepping by p
      // TODO: requires range with step, or a counted loop construct
      ...
```

## Blocker: range with step

The inner loop (`p*p` to `limit` stepping by `p`) requires either:
- `range(start, end, step Integer)` — a stepped range
- A `while`-like construct (Prove has no `while`)

Neither exists yet. The sieve cannot be fully expressed until one of these is added.
Options:
1. Add `range(start Integer, end Integer, step Integer) Sequence<Integer>` to the
   `Sequence` module — cleanest, composes with existing HOF
2. Add a `counted` loop built-in — bigger language change, defer

**Recommended:** add the 3-argument `range` overload first. It is broadly useful
beyond the sieve (any strided iteration).

## Plan for 3-argument range

```prove
module Sequence
  // ... existing functions ...

  /// Create a list of integers from start to end (exclusive) with given step
  creates range(start Integer, end Integer, step Integer) Sequence<Integer>
  binary
```

C runtime: `prove_range_step(int64_t start, int64_t end, int64_t step)` — a loop
building a `Prove_List*`.

Optimizer: fuse `filter(range(s, e, step), p)` etc. as `__fused_filter_range_step`
(separate from the existing stride-1 `__fused_filter_range` planned in the main plan).

## Placement

Once working, the sieve should live in `examples/sieve/src/main.prv` as a standalone
example project, parallel to the existing benchmark. It demonstrates:
- `Array<Boolean>:[Mutable]` in-place writes
- Performance comparable to native C
- Contrast with `examples/primes/` (trial division) to show the algorithmic difference
