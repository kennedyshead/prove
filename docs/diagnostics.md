# Diagnostic Codes

The Prove compiler emits errors and warnings with unique codes. Each diagnostic includes the source location, an explanation, and often a suggestion for how to fix it.

---

## Verb Enforcement (E360-E364)

These errors enforce the purity rules of the verb system. Pure verbs (`transforms`, `validates`, `reads`, `creates`, `matches`) cannot perform side effects.

### E360 — `validates` has implicit Boolean return

A `validates` function always returns `Boolean`. Declaring an explicit return type is an error.

```prove
// Wrong — do not declare a return type
validates is_active(u User) Boolean    // E360
from
    u.active

// Correct
validates is_active(u User)
from
    u.active
```

### E361 — Pure function cannot be failable

Functions with pure verbs cannot use the `!` fail marker. Pure functions do not perform IO and therefore cannot fail.

```prove
// Wrong — transforms is pure, cannot fail
transforms double(x Integer) Integer!    // E361
from
    x * 2

// Correct
transforms double(x Integer) Integer
from
    x * 2
```

### E362 — Pure function cannot call IO builtin

A function with a pure verb cannot call built-in IO functions such as `println`, `print`, `readln`, `read_file`, `write_file`, `open`, `close`, `flush`, or `sleep`.

```prove
// Wrong — transforms cannot call println
transforms greet(name String) String    // E362
from
    println("Hello")
    name

// Correct — use an IO verb
outputs greet(name String)
from
    println(f"Hello, {name}")
```

### E363 — Pure function cannot call user-defined IO function

A function with a pure verb cannot call a user-defined function that uses an IO verb (`inputs` or `outputs`).

```prove
outputs save(data String)
from
    write_file("out.txt", data)

// Wrong — transforms cannot call an outputs function
transforms process(data String) String    // E363
from
    save(data)
    data
```

### E364 — Lambda captures variable (closures not supported)

Lambdas cannot reference variables from an enclosing scope. All values must be passed as arguments.

```prove
transforms scale_all(xs List<Integer>, factor Integer) List<Integer>
from
    // Wrong — lambda captures `factor`
    map(xs, |x| x * factor)    // E364
```

### E365 — Ambiguous IO verb declaration

Two IO verbs (`inputs` and `outputs`) cannot declare functions with the same name and parameter types. If the compiler can't disambiguate, neither can the programmer.

```prove
// Wrong — same name, same params, both IO
inputs sync(data Data, server Server) Data!       // E365
outputs sync(data Data, server Server) Data!

// Correct — use distinct names
inputs fetch_sync(data Data, server Server) Data!
outputs push_sync(data Data, server Server) Data!
```

### E366 — Recursive function missing `terminates`

Every recursive function must declare a `terminates` measure expression. The compiler uses this to verify that the recursion converges.

```prove
// Wrong — recursive but no terminates
transforms factorial(n Integer) Integer                    // E366
from
    match n
        0 => 1
        _ => n * factorial(n - 1)

// Correct
transforms factorial(n Integer) Integer
  terminates: n
from
    match n
        0 => 1
        _ => n * factorial(n - 1)
```

---

## Explain & Contract Verification (E390-E394)

These diagnostics enforce the relationship between contracts (`ensures`, `requires`, `believe`) and implementation explanations.

### E390 — `explain` row count mismatch

When `explain` is present alongside `ensures` (strict mode), the number of explain rows must exactly match the number of lines in the `from` block. A mismatch is a compiler error.

```prove
// Wrong — 2 explain rows but 3 from lines
transforms clamp(x Integer, lo Integer, hi Integer) Integer
  ensures result >= lo
  ensures result <= hi
  explain
    bound the value from below                     // E390 — 2 rows, 3 lines
    bound the value from above
from
    clamped_low as Integer = max(lo, x)
    clamped as Integer = min(clamped_low, hi)
    clamped

// Correct — 3 explain rows match 3 from lines
transforms clamp(x Integer, lo Integer, hi Integer) Integer
  ensures result >= lo
  ensures result <= hi
  explain
    bound value from below using lo
    bound clamped_low from above using hi
    return the clamped result
from
    clamped_low as Integer = max(lo, x)
    clamped as Integer = min(clamped_low, hi)
    clamped
```

> **Note:** `ensures` without `explain` is a **warning**, not an error — the LSP suggests adding explain to document how the postconditions are satisfied. Similarly, `explain` without `ensures` produces a warning: the explain is unverifiable without contracts to check against.

### E391 — Duplicate explain row

Each explain row must be distinct. Duplicate rows indicate copy-paste errors.

```prove
transforms abs(x Integer) Integer
  ensures result >= 0
  explain
    take the maximum of x and negated x
    take the maximum of x and negated x            // E391 — duplicate
from
    candidate as Integer = 0 - x
    max(x, candidate)
```

### E392 — `explain` reference not found

In strict mode (with `ensures`), the compiler verifies that references in explain rows correspond to real identifiers in the function. An unrecognized reference that isn't a sugar word triggers this error.

```prove
transforms double(x Integer) Integer
  ensures result == x * 2
  explain
    multiply foo by two                            // E392 — `foo` not found
from
    x * 2
```

### E393 — `believe` without `ensures`

The `believe` keyword is a weaker assertion that still requires `ensures` to be present on the function.

```prove
// Wrong — believe without ensures
transforms add(a Integer, b Integer) Integer
  believe result > 0                               // E393
from
    a + b

// Correct
transforms add(a Integer, b Integer) Integer
  ensures result == a + b
  believe result > 0
from
    a + b
```

### E394 — `explain` operation not recognized

In strict mode (with `ensures`), the compiler parses each explain row for a known operation (action verb). If no recognized operation is found and the word isn't in the custom vocabulary, this error is emitted.

```prove
transforms abs(x Integer) Integer
  ensures result >= 0
  explain
    frobulate x into a positive value              // E394 — `frobulate` not a known operation
from
    max(x, 0 - x)
```

Custom operations can be declared in `prove.toml` under `[explain].operations`.

---

## Warnings

### W321 — `explain` text missing concept references

An explain row should reference at least one concept from the function — a parameter name, a variable, or `result`. Rows that reference none of these are likely too vague to be useful.

```prove
transforms double(x Integer) Integer
  ensures result == x * 2
  explain
    this is obvious                                // W321 — doesn't mention x, result, or double
from
    x * 2
```

### W322 — Duplicate near-miss input

Two `near_miss` declarations on the same function have identical input expressions.

```prove
transforms parse_port(s String) Option<Port>
  near_miss "" => None
  near_miss "" => None                             // W322
from
    // ...
```

### W323 — `ensures` without `explain`

A function has postconditions but no `explain` block. If you promise, explain how. The LSP will suggest adding explain.

```prove
transforms clamp(x Integer, lo Integer, hi Integer) Integer
  ensures result >= lo                             // W323 — add explain
  ensures result <= hi
from
    max(lo, min(x, hi))
```

### W324 — `ensures` without `requires`

A function has postconditions but no preconditions. This is a warning, not an error — it may be intentional, but often indicates missing input constraints.

```prove
transforms head(xs List<T>) T
  ensures result == xs[0]                          // W324 — no requires on xs
from
    xs[0]
```

### W325 — `explain` without `ensures`

An `explain` block is present but there are no `ensures` clauses. Without contracts to check against, the explain is unverifiable — it serves as documentation only.

```prove
transforms double(x Integer) Integer
  explain
    multiply x by two                              // W325 — no ensures to verify against
from
    x * 2
```

### W326 — Recursion depth may be unbounded

A recursive function's `terminates` measure decreases by a constant amount per call, suggesting O(n) call depth. Consider using `map`, `filter`, or `reduce` via the pipe operator instead.

```prove
transforms sum_all(xs List<Integer>) Integer
  terminates: len(xs)                              // W326 — O(n) depth
from
    match xs
        [] => 0
        [head, ...tail] => head + sum_all(tail)

// Preferred: use reduce
transforms sum_all(xs List<Integer>) Integer
from
    reduce(xs, 0, |acc, x| acc + x)
```
