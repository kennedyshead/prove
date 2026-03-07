---
title: Contracts & Testing - Prove Programming Language
description: Learn about Prove's contract system for formal verification, preconditions, postconditions, and automatic test generation.
keywords: Prove contracts, formal verification, testing, ensures, requires, invariant
---

# Contracts & Testing

## Formal Verification of Contracts

The compiler proves properties when it can, and generates tests when it can't:

```prove
transforms binary_search(xs Sorted<List<Integer>>, target Integer) Option<Integer>
  ensures is_some(result) implies xs[unwrap(result)] == target
  ensures is_none(result) implies target not_in xs
```

## Contracts by Example — What Makes Prove Different

Prove's contract system is not syntactic sugar for assertions. It is a fundamentally different relationship between programmer intent and compiler enforcement.

### Compiler-Enforced Preconditions

```prove
transforms calculate_total(items List<OrderItem>, discount Discount, tax TaxRule) Price
  requires len(items) > 0
from
    sub as Price = subtotal(items)
    discounted as Price = apply_discount(discount, sub)
    apply_tax(tax, discounted)
```

The `requires` clause is type-checked at compile time (must be a Boolean expression). At runtime, the compiler automatically generates property tests that verify the requirement holds across thousands of random inputs.

### Compiler-Verified Postconditions

```prove
transforms calculate_total(items List<OrderItem>, discount Discount, tax TaxRule) Price
  ensures result >= 0
from
    sub as Price = subtotal(items)
    discounted as Price = apply_discount(discount, sub)
    apply_tax(tax, discounted)
```

The `ensures` clause is type-checked at compile time. The compiler generates property tests that verify the postcondition across thousands of random inputs at runtime.

These are hard rules — the compiler enforces them automatically.

### Implementation Reasoning

When the implementation has multiple steps, `explain` documents the chain of operations using controlled natural language. With `ensures` present (strict mode), the row count must match the `from` block and the compiler verifies references against contracts:

```prove
outputs update_email(id Option<Integer>) User:[Mutable]!
  ensures valid user(user)
  requires valid id(id)
  explain
      we get an email address
      we fetch the user
      then we validate the email format
      we set the email to user
      save and return the user
from
    email as Option<Email> = email()
    user as User:[Mutable] = user(id)!
    set_email(user, email)
    save(dump_user(user))
    user
```

`requires` and `ensures` are about the function's *interface*. `explain` is about the function's *implementation* — it documents *how* each step satisfies the promises.

`explain` is LSP-suggested, not compiler-required. Simple functions with `ensures` don't need it — the LSP suggests it when complexity warrants documentation. However, `ensures` without `explain` produces a warning: if you promise, explain how.

### Bidirectional Lookup Types

Algebraic types can use the `[Lookup]` modifier to create a bidirectional map in a single declaration:

```prove
type Status:[Lookup] is String where
    Pending | "pending"
    Active  | "active"
    Done    | "done"
```

Access works both ways:

- `Status:Active` → returns `"active"` (forward lookup)
- `Status:"active"` → returns the `Active` variant (reverse lookup)

This is impossible in most languages without separate maps in both directions. In Python you'd need two dictionaries, maintaining consistency manually. In Rust you'd define the enum, a `HashMap` for each direction, and hope they stay in sync. In Prove, it's a single declaration that the compiler verifies is exhaustive and unique.

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
transforms divide(a Integer, b Integer where != 0) Integer
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

### Level 3: `near_miss` — Boundary Witnesses

A `near_miss` declares an input that *should fail* a contract. The compiler verifies that the function's `requires` or `validates` clauses actually reject it. This catches contracts that are too permissive.

```prove
transforms leap_year(y Integer) Boolean
  requires y > 0
  near_miss 0 => rejected       // not a valid year
  near_miss -1 => rejected      // negative year
from
    (y % 4 == 0 && y % 100 != 0) || y % 400 == 0
```

The compiler generates tests that pass each `near_miss` input to the function and confirms it is rejected by the preconditions. If a `near_miss` input is accidentally accepted, the test fails — the contract has a gap.

### Level 4: Built-in Mutation Testing *(v0.9.6+)*

```
$ prove build    # mutation testing runs by default
# or
$ prove build --no-mutate    # skip mutation testing

Mutation score: 97.2% (347/357 mutants killed)
Surviving mutants:
  src/cache.prv:45  — changed `>=` to `>` (boundary condition not covered)
  src/cache.prv:82  — removed `+ 1` (off-by-one not detected)

  Suggested contract to add:
    ensures len(cache) <= max_size   // would kill both mutants
```

---

## Verification Chain

`ensures` requirements propagate through the call graph. If function A has `ensures` and calls function B, the compiler needs B's contracts to verify A's postconditions. If B has no `ensures`, the verification has a gap — the compiler warns.

```prove
transforms calculate_total(items List<OrderItem>, discount Discount, tax TaxRule) Price
  ensures result >= 0
from
    sub as Price = subtotal(items)
    discounted as Price = apply_discount(discount, sub)
    apply_tax(tax, discounted)
```

If `subtotal` has `ensures result >= 0`, the compiler can verify the chain. If it doesn't, the compiler warns that `calculate_total`'s verification depends on an unverified function.

### When `ensures` is expected

The compiler warns when `ensures` is missing on:

- **Functions in a verification chain** — called by a function that has `ensures`
- **IO functions** (`inputs`/`outputs`) — API boundaries where contracts matter
- **Exported functions** — callers outside the module need guarantees

Functions outside any verification chain — trivial helpers, internal plumbing — are fine without annotations.

### `trusted` — explicit opt-out

When a function is in a verification chain but you don't want to add contracts yet, `trusted` acknowledges the gap:

```prove
transforms subtotal(items List<OrderItem>) Price
  trusted: "sum of non-negative prices is non-negative"
from
    reduce(items, 0, |acc, item| acc + item.price)
```

The compiler stops warning. `prove check` reports trusted functions in its verification coverage summary.

### `near_miss` — LSP-suggested for validators

The LSP suggests `near_miss` for `validates` functions with compound logic — multiple `&&`/`||`, modular arithmetic, negation. Trivial validators (single field access, simple equality) get no suggestion. `near_miss` proves the programmer understands the exact boundary between valid and invalid inputs.
