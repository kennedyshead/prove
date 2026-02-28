# Compiler-Driven Development

## Conversational Compiler Errors

Errors are suggestions, not walls:

```
error[E042]: `port` may exceed type bound
  --> server.prv:12:5
   |
12 |   port as Port = get_integer(config, "port")
   |                   ^^^^^^^^^^^^^^^^^^^^^^^^^^^^
   = note: `get_integer` returns Integer, but Port requires 1..65535

   try: port as Port = clamp(get_integer(config, "port"), 1, 65535)
    or: port as Port = check(get_integer(config, "port"))!
```

## Comptime (Compile-Time Computation)

Inspired by Zig. Arbitrary computation at compile time, including IO. Files read during comptime become build dependencies.

```prove
MAX_CONNECTIONS as Integer = comptime
    if cfg.target == "embedded"
        16
    else
        1024

LOOKUP_TABLE as List<Integer:[32 Unsigned]> = comptime
    collect(map(0..256, crc32_step))

ROUTES as List<Route> = comptime
    decode(read("routes.json"))                   // IO allowed — routes.json becomes a build dep
```

## Formal Verification of Contracts

The compiler proves properties when it can, and generates tests when it can't:

```prove
transforms binary_search(xs Sorted<List<Integer>>, target Integer) Option<Index>
    ensures is_some(result) implies xs[unwrap(result)] == target
    ensures is_none(result) implies target not_in xs
```

---

## Auto-Testing

Testing is not a separate activity. It is woven into the language — contracts are mandatory and the compiler enforces them.

### Level 1: Contracts Generate Property Tests

No test file needed. No QuickCheck boilerplate. The compiler generates thousands of random inputs and verifies all postconditions hold. Contracts are mandatory — every function declares what it guarantees.

```prove
transforms sort(xs List<T>) List<T>
    ensures len(result) == len(xs)
    ensures is_sorted(result)
    ensures is_permutation_of(result, xs)
    from
        // implementation
```

### Level 2: Automatic Edge-Case Generation

Given the type signature alone, the compiler knows to test boundary values and heuristic edge cases:

```prove
transforms divide(a Integer, b NonZero<Integer>) Integer
// Auto-generated test inputs: (0, 1), (1, 1), (-1, 1), (MAX_INT, 1),
// (MIN_INT, -1), (7, 3), ...
// Derived from type bounds + heuristic edge-case generation
```

For refinement types, boundary testing is automatic:

```prove
transforms set_port(p Port) Config    // Port = 1..65535
// Auto-tests: 1, 2, 65534, 65535, and random values between
// Also verifies that 0 and 65536 are rejected at the call site
```

### Level 4: Built-in Mutation Testing

```
$ prove build --mutate

Mutation score: 97.2% (347/357 mutants killed)
Surviving mutants:
  src/cache.prv:45  — changed `>=` to `>` (boundary condition not covered)
  src/cache.prv:82  — removed `+ 1` (off-by-one not detected)

  Suggested contract to add:
    ensures len(cache) <= max_size   // would kill both mutants
```

---

## Concurrency — Structured, Typed, No Data Races

```prove
inputs fetch_all(urls List<Url>) List<Response>!
    from
        par_map(urls, fetch)   // parallel map — compiler proves no shared mutable state
```

The ownership system and effect types combine to eliminate data races at compile time.

---

## Error Handling — Errors Are Values

No exceptions. Every failure path is visible in the type signature. Uses `!` for error propagation. Panics exist only for violated `assume:` assertions at system boundaries — normal error handling is always through `Result` values.

```prove
main() Result<Unit, Error>!
    from
        config as Config = read_config("app.yaml")!
        db as Database = connect(config.db_url)!
        serve(config.port, db)!
```

---

## Zero-Cost Abstractions

- Pure functions auto-memoized and inlined
- Region-based memory for short-lived allocations
- Reference counting only where ownership is shared (compiler-inserted)
- No GC pauses, predictable performance
- Native code output

---

## Pain Point Comparison

| Pain in existing languages | How Prove solves it |
|---|---|
| Tests are separate from code | Testing is part of the definition — `ensures`, `requires`, `near_miss` |
| "Works on my machine" | Verb system makes IO explicit (`inputs`/`outputs`) |
| Null/nil crashes | No null — use `Option<T>`, enforced by compiler |
| Race conditions | Ownership + verb system prevents data races |
| "I forgot an edge case" | Compiler generates edge cases from types |
| Slow test suites | Property tests run at compile time when provable |
| Runtime type errors | Refinement types catch invalid values at compile time |
