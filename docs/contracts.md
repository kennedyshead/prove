---
title: Contracts & Annotations - Prove Programming Language
description: Complete reference for Prove's contract system — requires, ensures, explain, terminates, epistemic annotations, near_miss, trusted, and auto-testing.
keywords: Prove contracts, formal verification, testing, ensures, requires, explain, near_miss, invariant
---

# Contracts & Annotations

Prove's contract system is not syntactic sugar for assertions. It is a fundamentally different relationship between programmer intent and compiler enforcement. The compiler proves properties when it can, and generates tests when it can't.

---

## requires and ensures

`requires` and `ensures` are hard rules about the function's interface. The compiler enforces them automatically.

`requires` states what must be true before calling the function — the compiler generates property tests that verify it at runtime. `ensures` states what the function guarantees about its result — the compiler generates property tests to verify it.

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

### Combined Example

```prove
type Clamped is Integer where low .. high

transforms clamp(value Integer, low Integer, high Integer) Clamped
  requires low <= high
  ensures result >= low
  ensures result <= high
from
    max(low, min(value, high))
```

Here, the [refinement type](types.md#refinement-types) `Clamped` does the heavy lifting.

### requires valid — Validation and Narrowing

`requires valid func(param)` is a special form that does three things at once:

1. **Contract** — asserts the `validates` function returns true for the argument
2. **Type narrowing** — unwraps `Option<T>` and `Result<T, E>` parameters to `T` inside the function body
3. **Return narrowing** — if a called function returns `Result<T, E>` or `Option<T>` and its arguments are narrowed by `requires valid`, the return type is narrowed to `T` and automatically unwrapped

This is the idiomatic way to handle validated data in Prove. Rather than manually unwrapping and checking errors, you declare the validation requirement up front and the compiler generates the correct unwrap code.

```prove
module Main
  Parse validates toml creates toml

/// Parse validated TOML data into a Config record
matches config(data Result<String, Error>) Config
  requires valid toml(data)
from
    Config(toml(data))
```

Here `data` is `Result<String, Error>`. The `requires valid toml(data)` clause:

- Calls `Parse.validates toml` to check `data` is valid
- Narrows `data` from `Result<String, Error>` to `String` inside the body
- Since `toml(data)` now receives `String`, the compiler resolves to `creates toml(source String) Result<Table<Value>, String>` — not `reads toml(value Value) String`
- The return type `Result<Table<Value>, String>` is also narrowed to `Table<Value>` because the argument was validated
- The `Table<Value>` is then mapped to the `Config` record fields automatically

Without `requires valid`, you would need to manually unwrap the Result, call the right overload, and handle errors — `requires valid` collapses all of that into a single declaration.

The same pattern works for `Option`:

```prove
validates ok(id Option<Integer>)
  requires valid integer(id)
from
    id > 0
```

Here `id` is `Option<Integer>`, but inside the body it is narrowed to `Integer` because `requires valid integer(id)` guarantees the Option contains a value.

---

## explain

`explain` documents the chain of operations in the `from` block using controlled natural language. It is **LSP-suggested, not compiler-required** — the LSP recommends adding it when a function has enough complexity to warrant documentation.

**Two strictness modes:**

**Strict mode** (function has `ensures`): Each explain row corresponds to a **top-level statement** in the `from` block — a binding, a final expression, or a match arm. Multi-line expressions (pipe chains, multi-line arms) count as one. The count must match exactly (mismatch is a compiler error). The compiler warns if a single arm grows complex enough to warrant extraction into a named function.

The compiler parses each row for an **operation** (action verb), **connectors** (prepositions like `by`, `to`, `all`), and **references** (identifiers from the function). Operations are verified against called functions' contracts — if the called function has no contracts supporting the claimed operation, the compiler warns. References must be real identifiers. Sugar words ("the", "applicable", etc.) are ignored — keeping explain readable as natural English while remaining machine-verifiable.

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

Sugar words keep it readable — the compiler sees the same thing:

```prove
  explain
    we get an applicable email address from console
    we fetch the corresponding user from storage
    then we validate the email format against the regex pattern
    we set the new email to user
    save the updated user and return it
```

The compiler parses each row for operations (`get`, `fetch`, `validate`, `set`, `save`), connectors (`we`, `then`, `the`), and references (`email`, `user`, `format`). Operations are verified against called functions' contracts — if the claimed operation doesn't match the function's behavior, the compiler warns.

**Loose mode** (no `ensures`): Row count is flexible. Free-form text. Documentation value only.

```prove
transforms merge_sort(xs List<Value>) Sorted<List<Value>>
  explain
      split the list at the midpoint
      recursively sort both halves
      merge the sorted halves back together
  terminates: len(xs)
from
    halves as Pair<List<Value>> = split_at(xs, len(xs) / 2)
    left as Sorted<List<Value>> = merge_sort(halves.first)
    right as Sorted<List<Value>> = merge_sort(halves.second)
    merge(left, right)
```

**Warning pairs:**

- `ensures` without `explain` → warning: add explain to document how ensures are satisfied
- `explain` without `ensures` → warning: explain is unverifiable without contracts to check against

**Bare functions are fine.** Trivial code needs no annotations:

```prove
validates email(address String)
from
    contains(address, "@") && contains(address, ".")
```

No explain needed — the implementation is self-evident. The LSP suggests explain only when complexity warrants it.

For [`matches`](functions.md#intent-verbs) functions, each explain row corresponds to one arm. The LSP suggests per-arm explain for complex dispatch:

```prove
matches apply_discount(discount Discount, amount Price) Price
  ensures result >= 0
  ensures result <= amount
  explain
      clamp the difference to zero
      scale amount by complement of rate
      subtract bulk discount from amount
from
    FlatOff(off) => max(0, amount - off)
    PercentOff(rate) => amount * (1 - rate)
    BuyNGetFree(buy, free) =>
        sets as Integer = len(items) / (buy + free)
        amount - sets * cheapest_price(items)
```

**Custom vocabulary** for operations and connectors can be declared at module level or in [`prove.toml`](compiler.md#provetoml-configuration):

```toml
# prove.toml
[explain]
operations = ["amortize", "interpolate", "normalize"]
connectors = ["across", "between", "within"]
```

`explain` is independent of `requires` and `ensures`. A function can have any combination — though the strictness mode depends on whether `ensures` is present.

### Why explain matters

Unlike AI prompt-pong — where each change requires a fresh conversation to *maybe* get a working result — an `explain` statement is **source code**. You edit it like any other line. One small change propagates consistently across your entire codebase.

**Editable, not conversational.** When you need to refactor, you tweak the explain text and the implementation follows. No prompting, no retry loops, no hoping the AI "understands" this time.

**LSP/compiler suggestions as the ecosystem grows.** As your codebase accumulates well-documented functions, the compiler can suggest operations that already exist and match your intent. The explain text becomes a *query* against your library — "I need to X the Y" auto-completes to functions that actually do that. This gets more powerful with every function you write.

**Foundation-first code generation.** AI can generate correct code from intent, but only if the building blocks exist. Each `explain` + implementation pair you write is a new block the compiler understands. Over time, explain statements generate most of the boilerplate automatically — you provide the high-level intent, the ecosystem provides the implementation.

This is the inverse of typical AI workflows. Instead of fishing for working code through conversation, you're building a vocabulary the compiler uses to help you. The more complete your library, the less you need to write explicitly. This is the foundation of Prove's [vision for self-contained development](vision.md) — local, deterministic generation from your own declarations.

---

## terminates

Recursive functions must declare `terminates` with a measure expression — an expression that strictly decreases on each recursive call. Omitting `terminates` on a recursive function is a compiler error ([E366](diagnostics.md#e366-recursive-function-missing-terminates)).

```prove
transforms merge_sort(xs List<Value>) Sorted<List<Value>>
  explain
      split the list at the midpoint
      recursively sort the first half
      recursively sort the second half
      merge both sorted halves preserving order
  terminates: len(xs)
from
    halves as Pair<List<Value>> = split_at(xs, len(xs) / 2)
    left as Sorted<List<Value>> = merge_sort(halves.first)
    right as Sorted<List<Value>> = merge_sort(halves.second)
    merge(left, right)
```

The compiler verifies that `len(halves.first) < len(xs)` and `len(halves.second) < len(xs)` at both recursive call sites.

---

## Epistemic Annotations

`know`, `assume`, and `believe` express different levels of confidence about a claim:

```prove
transforms process_order(order Order) Receipt
  know: len(order.items) > 0
  assume: order.total == sum(prices)
  believe: order.user.is_verified
from
    // implementation
```

- **`know`** — the compiler attempts to prove the claim using constant folding, algebraic identities, [refinement types](types.md#refinement-types), assumption matching (facts from `requires`, `assume`, and `believe` in scope), arithmetic reasoning (e.g., `x + 1 > x`, transitivity), callee ensures propagation, and match arm structural narrowing. Provable claims pass silently; unprovable claims emit a warning ([W327](diagnostics.md#w327-know-claim-cannot-be-proven)) and fall back to a runtime assertion.
- **`assume`** — the compiler adds a runtime check. If the assumption fails at runtime, the program panics.
- **`believe`** — the compiler tries to break it with generated tests. Requires `ensures` to be present ([E393](diagnostics.md#e393-believe-without-ensures)).

### Callee Ensures Propagation

When a called function has an `ensures` clause, the compiler propagates that postcondition into the caller's proof context. If `f` declares `ensures result > 0`, and you write `y = f(x)`, the compiler automatically knows `y > 0` — no extra annotation required.

```prove
transforms positive(n Integer) Integer
    requires n > 0
    ensures result > 0
    explain
        n is positive so result is positive
    from
        n

transforms caller(n Integer) Integer
    requires n > 0
    know: y > 0        // proven — positive ensures result > 0
    from
        y as Integer = positive(n)
        y
```

The substitution is automatic: `result` in the callee's `ensures` is replaced by the binding name `y` in the caller's proof context. All `ensures` clauses on the callee are propagated, so multiple postconditions are all available.

### Match Arm Structural Narrowing

The compiler records structural match arm bindings in the proof context. When a `match` arm matches `Some(x)`, the compiler records that the subject was a `Some` variant; combined with a `requires` or `assume` fact, `know` claims about the subject's non-null status become provable.

```prove
transforms safe_unwrap(opt Option<Integer>) Integer
    requires opt != None
    know: opt != None   // proven — requires + Some arm recorded
    from
        match opt
            Some(x) => x
            None    => 0
```

Function-level `know` claims can also reference arm-bound variables directly. When a match arm binds `Some(inner)`, the compiler infers the type of `inner` (the unwrapped value) and makes it available during `know` checking. Unprovable arm-bound claims emit [W372](diagnostics.md#w372-arm-bound-know-claim-cannot-be-proven) rather than the general [W327](diagnostics.md#w327-know-claim-cannot-be-proven).

```prove
transforms check_inner(xs Option<Integer>) Integer
    requires xs != None
    know: inner > 0   // references arm-bound `inner` — W372 if unprovable
from
    match xs
        Some(inner) => inner
        None        => 0
```

All three are type-checked — their expressions must be Boolean ([E384](diagnostics.md#e384-know-expression-must-be-boolean), [E385](diagnostics.md#e385-assume-expression-must-be-boolean), [E386](diagnostics.md#e386-believe-expression-must-be-boolean)).

---

## Counterfactual Annotations

### why_not and chosen

`why_not` documents rejected alternatives. `chosen` explains the selected approach. The compiler verifies rationale consistency — it checks that `why_not` entries reference known names (W505), that `chosen` text relates to the implementation (W504), and that `why_not` entries don't contradict the implementation (W506).

```prove
transforms select_gateway(amount Price, region Region) Gateway
  why_not: "Round-robin ignores regional latency differences"
  why_not: "Cheapest-first causes thundering herd on one provider"
  chosen: "Latency-weighted routing balances cost and speed per region"
from
    closest_by_latency(region, available_gateways())
```

---

## near_miss

`near_miss` declares inputs that *almost* break the code but don't — the compiler verifies each near-miss exercises a distinct boundary condition. Redundant near-misses are rejected ([W322](diagnostics.md#w322-duplicate-near-miss-input)).

```prove
validates leap_year(y Year)
  near_miss: 1900  => false
  near_miss: 2000  => true
  near_miss: 2100  => false
from
    (y % 4) == 0 && ((y % 100) != 0 || (y % 400) == 0)
```

The compiler generates tests that pass each `near_miss` input to the function and confirms it is rejected by the preconditions. If a `near_miss` input is accidentally accepted, the test fails — the contract has a gap.

The LSP suggests `near_miss` for [`validates`](functions.md#intent-verbs) functions with compound logic — multiple `&&`/`||`, modular arithmetic, negation. Trivial validators (single field access, simple equality) get no suggestion.

---

## trusted

`trusted` is the explicit opt-out from the verification chain. It acknowledges that a function is unverified and silences the warning:

```prove
transforms subtotal(items List<OrderItem>) Price
  trusted: "sum of non-negative prices is non-negative"
from
    reduce(items, 0, |acc, item| acc + item.price)
```

The compiler stops warning. [`prove check`](cli.md) reports trusted functions in its verification coverage summary.

---

## intent

`intent` documents the purpose of a function. It goes in the function **header** (between the signature and `from`), not inside the body. The compiler records it and emits W311 when declared without `ensures`/`requires`. Prose consistency verification uses W501-W506 — warnings when the intent/why_not/chosen descriptions don't match the implementation.

```prove
transforms filter_valid(records List<Record>) List<Record>
  intent: "keep only valid records"
from
    filter(records, valid record)
```

---

## Module-Level Annotations

### narrative

`narrative` is required — it describes the module's purpose in plain language.

### domain

`domain` tags the module's problem domain. A module's `domain:` declaration selects a built-in profile that adds domain-specific warnings ([W340–W342](diagnostics.md)):

- **finance**: prefer `Decimal` over `Float`, require `ensures` contracts and `near_miss` examples
- **safety**: require `ensures`, `requires`, `explain` blocks
- **general**: no additional requirements

### temporal

`temporal` declares the expected ordering of operations.

```prove
module PaymentService
  narrative: """
  Customers submit payments. Each payment is validated,
  charged through the gateway, and recorded in the ledger.
  """
  domain Finance
  temporal: validate -> charge -> record
```

The compiler requires `narrative` blocks and enforces that referenced function names exist in scope. Domain-specific rules are implemented — the compiler enforces finance/safety domain requirements via W340-W342. Temporal ordering verification is upcoming.

---

## Invariant Networks

`invariant_network` defines rules that must always hold together. `satisfies` declares that a function obeys those rules.

```prove
invariant_network AccountingRules
  total_assets == total_liabilities + equity
  revenue - expenses == net_income
  every(transaction) preserves total_assets == total_liabilities + equity

transforms post_transaction(ledger Ledger, tx Transaction) Ledger
  satisfies AccountingRules
from
    // implementation — compiler verifies the rules hold after every change
```

---

## Annotation Ordering

All annotations appear between the verb line and `from`. The compiler accepts any order. The formatter normalizes to this canonical order:

1. `requires` — preconditions
2. `ensures` — postconditions
3. `terminates` — recursion measure
4. `trusted` — explicit verification opt-out
5. `know` / `assume` / `believe` — confidence levels
6. `why_not` / `chosen` — design reasoning
7. `near_miss` — boundary examples
8. `satisfies` — invariant networks
9. `event_type` — algebraic type for `listens` event dispatch
10. `explain` — implementation documentation (adjacent to `from`)

---

## Lookup Types

Algebraic types can use the `[Lookup]` modifier to create a bidirectional map in a single declaration. See [Type System — Lookup Types](types.md#lookup-types-bidirectional-maps) for the full reference.

```prove
type Status:[Lookup] is String where
    Pending | "pending"
    Active  | "active"
    Done    | "done"
```

Access works both ways:

- `Status:Active` → returns `"active"` (forward lookup)
- `Status:"active"` → returns the `Active` variant (reverse lookup)

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

### Diagnostics

- **[W370](diagnostics.md#w370-verification-chain-broken-public)** — a public function calls a verified function but has no `ensures` of its own. Add `ensures` to propagate verification, or `trusted` to explicitly opt out.
- **[W371](diagnostics.md#w371-verification-chain-broken-strict)** — same as W370 but for internal (underscore-prefixed) functions. Only emitted with `--strict`.

### When `ensures` is expected

The compiler warns when `ensures` is missing on:

- **Functions in a verification chain** — called by a function that has `ensures`
- **IO functions** (`inputs`/`outputs`) — API boundaries where contracts matter
- **Exported functions** — callers outside the module need guarantees

Functions outside any verification chain — trivial helpers, internal plumbing — are fine without annotations.

### `trusted` in the chain

When a function is in a verification chain but you don't want to add contracts yet, `trusted` acknowledges the gap:

```prove
transforms subtotal(items List<OrderItem>) Price
  trusted: "sum of non-negative prices is non-negative"
from
    reduce(items, 0, |acc, item| acc + item.price)
```

[`prove check`](cli.md) reports verification coverage:

```
$ prove check

Verification:
  ✓ 42 functions with ensures (property tests)
  ✓ 11 validators with near_miss (boundary tests)
  ⚠ 3 functions trusted
  ✗ 1 unverified in chain → add ensures or trusted

Coverage: 89%
```

Functions outside any verification chain and with no callers that have `ensures` are fine without annotations — nobody depends on them contractually.

---

## Auto-Testing

Testing is not a separate activity. It is woven into the language — contracts are mandatory and the compiler enforces them.

### Level 1: Property Tests

No test file needed. No QuickCheck boilerplate. The compiler generates thousands of random inputs and verifies all postconditions hold. Contracts are mandatory — every function declares what it guarantees.

```prove
transforms sort(xs List<Value>) List<Value>
  ensures len(result) == len(xs)
from
    // implementation
```

### Level 2: Edge-Case Generation

Given the type signature alone, the compiler knows to test boundary values and heuristic edge cases:

```prove
transforms divide(a Integer, b Integer where != 0) Integer
// Auto-generated test inputs: (0, 1), (1, 1), (-1, 1), (MAX_INT, 1),
// (MIN_INT, -1), (7, 3), ...
// Derived from type bounds + heuristic edge-case generation
```

For [refinement types](types.md#refinement-types), boundary testing is automatic:

```prove
transforms set_port(p Port) Config    // Port = 1..65535
// Auto-tests: 1, 2, 65534, 65535, and random values between
// Also verifies that 0 and 65536 are rejected at the call site
```

### Level 3: near_miss

A `near_miss` declares an input that *should fail* a contract. The compiler verifies that the function's `requires` or `validates` clauses actually reject it. This catches contracts that are too permissive.

```prove
transforms leap_year(y Integer) Boolean
  requires y > 0
  near_miss: 0 => false          // not a valid year
  near_miss: -1 => false         // negative year
from
    (y % 4 == 0 && y % 100 != 0) || y % 400 == 0
```

### Level 4: Mutation Testing

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
