# Contracts & Testing

## Formal Verification of Contracts

The compiler proves properties when it can, and generates tests when it can't:

```prove
transforms binary_search(xs Sorted<List<Integer>>, target Integer) Option<Index>
  ensures is_some(result) implies xs[unwrap(result)] == target
  ensures is_none(result) implies target not_in xs
```

## Contracts by Example — Why This Matters

Prove's contract system is not syntactic sugar for assertions. It is a fundamentally different relationship between programmer intent and compiler enforcement. To see why, compare the same function — `calculate_total` — across four languages.

### Prove

```prove
transforms calculate_total(items List<OrderItem>, discount Discount, tax TaxRule) Price
  ensures result >= 0
  requires len(items) > 0
from
    sub as Price = subtotal(items)
    discounted as Price = apply_discount(discount, sub)
    apply_tax(tax, discounted)
```

Two things happen at compile time:

- **`requires`** — The compiler rejects any call site that cannot prove `len(items) > 0`. This is not a runtime check. If your list might be empty, the code does not compile.
- **`ensures`** — The compiler verifies that every code path produces `result >= 0`. If it cannot prove this statically, it generates property tests that exercise thousands of inputs.

These are hard rules — the compiler enforces them automatically.

When the implementation has multiple steps, `explain` documents the chain of operations using controlled natural language. With `ensures` present (strict mode), the row count must match the `from` block and the compiler verifies references against contracts:

```prove
transforms calculate_total(items List<OrderItem>, discount Discount, tax TaxRule) Price
  ensures result >= 0
  requires len(items) > 0
  explain
    sum all items.price
    reduce sub by discount
    add tax to discounted
from
    sub as Price = subtotal(items)
    discounted as Price = apply_discount(discount, sub)
    apply_tax(tax, discounted)
```

`requires` and `ensures` are about the function's *interface*. `explain` is about the function's *implementation* — it documents *how* each step satisfies the promises.

`explain` is LSP-suggested, not compiler-required. Simple functions with `ensures` don't need it — the LSP suggests it when complexity warrants documentation. However, `ensures` without `explain` produces a warning: if you promise, explain how.

### Python

```python
def calculate_total(items: list[OrderItem], discount: Discount, tax: TaxRule) -> Price:
    """Calculate order total after discount and tax.

    Args:
        items: must be non-empty
        discount: discount to apply
        tax: tax rule to apply

    Returns:
        total price, always >= 0
    """
    assert len(items) > 0  # only checked if -O is not set
    sub = subtotal(items)
    discounted = apply_discount(discount, sub)
    result = apply_tax(tax, discounted)
    assert result >= 0  # also stripped by -O
    return result
```

- **Preconditions** — `assert` statements, stripped by `python -O`. The type hint `list[OrderItem]` says nothing about length. An empty list passes type checking and reaches runtime.
- **Postconditions** — Another `assert`, also stripped in production. The docstring says "always >= 0" but nothing enforces it.
- **Proof** — Does not exist. The docstring is a comment. Tests are a separate file written by a separate person at a separate time.

### Haskell

```haskell
calculateTotal :: NonEmpty OrderItem -> Discount -> TaxRule -> Price
-- | Precondition: items is non-empty (enforced by NonEmpty type)
-- | Postcondition: result >= 0 (NOT enforced — Price is just a newtype)
calculateTotal items discount tax =
  let sub = subtotal (toList items)
      discounted = applyDiscount discount sub
  in applyTax tax discounted
```

- **Preconditions** — `NonEmpty` enforces non-emptiness at the type level. This is genuinely good. But most preconditions ("discount is valid", "tax rate is between 0 and 1") require dependent types that Haskell does not have.
- **Postconditions** — Comments. The type `Price` does not carry the invariant `>= 0` unless you build a custom smart constructor, and even then the compiler does not verify that `applyTax` preserves it.
- **Proof** — Does not exist in the language. QuickCheck can test properties, but it is a library, it is opt-in, and the properties are written in test files separate from the function.

### Rust

```rust
fn calculate_total(items: &[OrderItem], discount: &Discount, tax: &TaxRule) -> Price {
    debug_assert!(!items.is_empty(), "items must be non-empty");
    let sub = subtotal(items);
    let discounted = apply_discount(discount, sub);
    let result = apply_tax(tax, discounted);
    debug_assert!(result >= Price::ZERO, "result must be non-negative");
    result
}
```

- **Preconditions** — `debug_assert!`, compiled out in release builds. The slice type `&[OrderItem]` permits empty slices. A `NonEmpty` wrapper exists in crates but is not standard.
- **Postconditions** — Another `debug_assert!`, also absent in release. The type system enforces memory safety but says nothing about business logic invariants.
- **Proof** — Does not exist. Tests are in a `#[cfg(test)]` module. Property testing requires `proptest` or `quickcheck` crates, and properties are written manually in test files.

### Summary

| Capability | Prove | Python | Haskell | Rust |
|---|---|---|---|---|
| **Preconditions** | `requires` — compile-time enforced | `assert` — runtime, strippable | Types cover some; rest are comments | `debug_assert!` — stripped in release |
| **Postconditions** | `ensures` — compiler-verified or auto-tested | `assert` — runtime, strippable | Comments or smart constructors (manual) | `debug_assert!` — stripped in release |
| **Implementation reasoning** | `explain` — checked by compiler | Does not exist | Does not exist | Does not exist |
| **Test generation** | Automatic from contracts | Manual (pytest, hypothesis) | Manual (QuickCheck) | Manual (proptest) |
| **Contracts are...** | Part of the function signature, compiler-enforced | Optional, easily ignored | Convention, not enforced | Convention, not enforced |

The gap is not about syntax. Python, Haskell, and Rust all have *mechanisms* for expressing some of these ideas. The difference is that in Prove, contracts are **compiler-enforced** and **self-testing**. You cannot write a function that silently ignores its own guarantees.

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
