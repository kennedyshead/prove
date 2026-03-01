# Diagnostic Codes

The Prove compiler emits errors and warnings with unique codes. Each diagnostic includes the source location, an explanation, and often a suggestion for how to fix it.

---

## Verb Enforcement (E360-E364)

These errors enforce the purity rules of the verb system. Pure verbs (`transforms`, `validates`, `reads`, `creates`, `saves`) cannot perform side effects.

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

---

## Proof Verification (E390-E394)

These errors enforce the relationship between contracts (`ensures`, `requires`, `believe`) and proof obligations.

### E390 — `ensures` without proof block

Every function with `ensures` clauses must have a `proof` block. The proof explains *why* the postconditions hold.

```prove
// Wrong — has ensures but no proof
transforms clamp(x Integer, lo Integer, hi Integer) Integer
  ensures result >= lo
  ensures result <= hi
from                                          // E390
    max(lo, min(x, hi))

// Correct
transforms clamp(x Integer, lo Integer, hi Integer) Integer
  ensures result >= lo
  ensures result <= hi
  proof
    bounded_below: max with lo guarantees result >= lo
    bounded_above: min with hi guarantees result <= hi
from
    max(lo, min(x, hi))
```

### E391 — Duplicate proof obligation name

Each obligation in a `proof` block must have a unique name.

```prove
transforms abs(x Integer) Integer
  ensures result >= 0
  proof
    non_negative: x or negated x are both >= 0
    non_negative: redundant obligation             // E391
from
    max(x, 0 - x)
```

### E392 — Proof obligations fewer than ensures count

The number of proof obligations must be at least the number of `ensures` clauses.

```prove
transforms divide(a Integer, b NonZero<Integer>) Integer
  ensures result * b <= a
  ensures result * b > a - b
  proof
    approximation: integer division truncates       // E392 — 1 obligation, 2 ensures
from
    a / b
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
  proof
    sum: addition of a and b produces their sum
from
    a + b
```

### E394 — Proof condition must be Boolean

When a proof obligation includes a structured condition (a code expression rather than just text), that expression must evaluate to `Boolean`.

```prove
transforms abs(x Integer) Integer
  ensures result >= 0
  proof
    non_negative: result is non-negative
      when result + 1                              // E394 — Integer, not Boolean
from
    max(x, 0 - x)
```

---

## Warnings

### W321 — Proof text missing concept references

A text-only proof obligation should reference at least one concept from the function — a parameter name, the function name, or `result`. Obligations that reference none of these are likely too vague to be useful.

```prove
transforms double(x Integer) Integer
  ensures result == x * 2
  proof
    correct: this is obvious                       // W321 — doesn't mention x, result, or double
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

### W324 — `ensures` without `requires`

A function has postconditions but no preconditions. This is a warning, not an error — it may be intentional, but often indicates missing input constraints.

```prove
transforms head(xs List<T>) T
  ensures result == xs[0]                          // W324 — no requires on xs
  proof
    first: returns the first element
from
    xs[0]
```
