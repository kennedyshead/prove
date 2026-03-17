# Formal `know` Proofs

**Status:** In Progress — Phases 1–3 implemented, Phases 4–5 remain
**Roadmap:** General proof beyond the current lightweight `ClaimProver`

## Problem

The original `ClaimProver` was a lightweight engine that handled constant
folding, algebraic identities (`x == x`, `x - x == 0`), and
refinement-based reasoning. It returned `True`, `False`, or `None`
(indeterminate). Many useful `know` claims fell into the indeterminate
category because the prover lacked:

- Path-sensitive reasoning (facts learned from `requires` or earlier `match` arms)
- Quantifier support (`know all(list, fn)`)
- Inductive reasoning (reasoning about recursive data structures)
- Arithmetic beyond constant folding (e.g., `x + 1 > x`)
- Inter-function reasoning (if `f` ensures `result > 0`, callers can know the return is positive)

## Goal

Extend the proof engine to handle a broader class of `know` claims while
keeping the compiler fast and the proof obligations predictable. This is not
a full theorem prover — it's a practical middle ground between "constant
folding only" and "full SMT".

## What's Implemented

### Phase 1: Proof Context Infrastructure ✅

`ProofContext` class (`prover.py:49`) holds accumulated facts from
`requires`, `assume`, and `believe` clauses. `_check_contracts.py` builds
the context before checking `know` claims, and each proven `know` is added
back to the context for subsequent claims in the same function.

### Phase 2: Assumption Matching ✅

`_prove_from_assumptions()` checks if a claim is structurally equal to any
fact in the proof context before returning `None`. Also handles integer
equivalences (e.g., `x > 0` ↔ `x >= 1`) via
`_prove_from_assumption_implication()`.

### Phase 3: Arithmetic Reasoning ✅

`_prove_arithmetic()` handles common symbolic rules:
- `x + k > x` when `k > 0`
- `x - k < x` when `k > 0`
- `x * 2 >= x` when `x >= 0` (from assumptions)
- Commutativity: `k + x > x`
- Transitivity: if `x > y` and `y > z`, then `x > z` (via `_prove_from_assumption_implication()`)

## What Remains

### Phase 4: Callee Ensures Propagation

When function `f` has `ensures: result > 0`, and the caller writes
`y = f(x)`, the prover should know `y > 0`. This requires:

1. Recording `ensures` clauses with their return-value bindings.
2. At call sites, substituting `result` with the call-site binding.
3. Adding the substituted ensures to the proof context.

The `ClaimProver` docstring already describes this; the implementation is not
yet wired in `_check_contracts.py` or `checker.py`.

### Phase 5: Match Arm Reasoning

Inside a `match` arm for `Some(x)`, the prover should know `x` is not
`None`. Inside `Ok(v)`, `v` is the success value. This is a form of
path-sensitive type narrowing that the checker partially does already —
extend it to the prover.

### Phase 6: Quantifier Basics (Future)

Limited support for `all` and `any` over lists:

- `know all(list, validates positive)` — if every element satisfies the
  predicate. Provable when the list was constructed from elements that
  individually satisfy the predicate (e.g., filtered by the same validator).
- No general induction — just constructor-based reasoning.

## Open Questions (Resolved)

- Should the proof context be visible to users (e.g., `prove check --show-context`)?
    - Yes
- Should indeterminate `know` claims remain warnings (W355) or become errors
  at some strictness level?
    - If we cannot build without they should become errors, else remain Warning. All warnings is error in strict
- How much does proof context affect compile speed? Need to benchmark with
  large modules.
    - We will find out while building proof compiler, no extra work required atm
- Should there be a `lemma` keyword for intermediate proof steps?
    - Yes.
- Should `believe` claims be usable as assumptions for later `know` claims?
  (They're unproven but declared — using them creates a trust chain.)
    - Yes, they should be usable in later know claims

## Files Likely Touched

- `prover.py` — Phase 4: extend `ClaimProver` with callee-ensures lookup; Phase 5: add match arm facts
- `_check_contracts.py` — Phase 4: pass callee ensures at call sites
- `checker.py` — Phase 4: record call-site bindings for ensures substitution
- `cli.py` — `--show-context` flag

## After implementation

* Make sure that implementation is reflected in this file if not all is done
* When all is done remove this file and update the roadmap.md with removal of this item.
* Update docs with any new/updated/removed functionallity if useful
