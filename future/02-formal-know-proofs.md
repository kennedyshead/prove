# Formal `know` Proofs

**Status:** Exploring
**Roadmap:** General proof beyond the current lightweight `ClaimProver`

## Problem

The current `ClaimProver` (`prover.py:266`) is a lightweight engine that
handles constant folding, algebraic identities (`x == x`, `x - x == 0`), and
refinement-based reasoning. It returns `True`, `False`, or `None`
(indeterminate). Many useful `know` claims fall into the indeterminate
category because the prover lacks:

- Path-sensitive reasoning (facts learned from `requires` or earlier `match`
  arms)
- Quantifier support (`know all(list, fn)`)
- Inductive reasoning (reasoning about recursive data structures)
- Arithmetic beyond constant folding (e.g., `x + 1 > x`)
- Inter-function reasoning (if `f` ensures `result > 0`, callers can know
  the return is positive)

## Goal

Extend the proof engine to handle a broader class of `know` claims while
keeping the compiler fast and the proof obligations predictable. This is not
a full theorem prover — it's a practical middle ground between "constant
folding only" and "full SMT".

## Current State

### ClaimProver (`prover.py:266-476`)

Capabilities:
- **Constant folding:** `know 2 + 2 == 4` — arithmetic on literals.
- **Boolean logic:** `&&`, `||`, `!` with short-circuit evaluation.
- **Algebraic identities:** `x == x` (true), `x != x` (false), `x - x == 0`.
- **Refinement-based:** If `x` has type `Integer where >= 1`, then
  `know x > 0` succeeds via `_prove_from_refinement()`.

Limitations:
- No path sensitivity — `requires: x > 0` doesn't inform later `know` claims.
- No inter-procedural reasoning — can't use callee's `ensures`.
- No quantifier reasoning — `know all(...)` is always indeterminate.
- No arithmetic reasoning beyond eval — `know x + 1 > x` is indeterminate.
- No SMT or external solver — everything is hand-rolled pattern matching.

### Contract Interaction

- `know` claims are checked in `_check_contracts.py:172-201`.
- `ClaimProver` receives the symbol table but only uses it for refinement
  type lookups.
- `requires` and `ensures` are type-checked but their content is not fed
  into the prover as assumptions.

### `assume` vs `know`

- `assume` — accepted without proof (axiom). Checked for type only (E385).
- `know` — must be provable. If indeterminate, warns W355.
- `believe` — requires `ensures` present (E393), not proven.

## Design

### Proof Context

The core extension is a **proof context** — a set of facts known to be true
at a given program point. Sources of facts:

| Source | Fact |
|--------|------|
| `requires` clause | Precondition is true inside the body |
| `assume` clause | Axiom — assumed true |
| `know` (proven) | Previously proven claim |
| Match arm | Variant identity in scope |
| Refinement type | Type constraint on variable |
| `ensures` of callee | Postcondition substituted at call site |

The prover checks each `know` claim against this accumulated context.

### Proof Strategies (Incremental)

#### Level 1: Assumption Integration

Feed `requires` and `assume` clauses into ClaimProver as known facts. When
proving `know P`, check if `P` is directly in the assumption set or follows
by simple substitution.

Implementation: add `assumptions: list[Expr]` to `ClaimProver.__init__()`.
Before returning `None`, check if the claim matches any assumption.

#### Level 2: Arithmetic Reasoning

Add rules for common integer/decimal properties:

- `x + k > x` when `k > 0`
- `x * 2 >= x` when `x >= 0`
- `x - k < x` when `k > 0`
- Transitivity: if `x > y` and `y > z`, then `x > z`

Implementation: extend `_prove_binary()` with symbolic comparison rules. No
full solver — just pattern-matched common cases.

#### Level 3: Callee Ensures Propagation

When function `f` has `ensures: result > 0`, and the caller writes
`y = f(x)`, the prover should know `y > 0`. This requires:

1. Recording `ensures` clauses with their return-value bindings.
2. At call sites, substituting `result` with the call-site binding.
3. Adding the substituted ensures to the proof context.

#### Level 4: Match Arm Reasoning

Inside a `match` arm for `Some(x)`, the prover should know `x` is not
`None`. Inside `Ok(v)`, `v` is the success value. This is a form of
path-sensitive type narrowing that the checker partially does already — extend
it to the prover.

#### Level 5: Quantifier Basics

Limited support for `all` and `any` over lists:

- `know all(list, validates positive)` — if every element satisfies the
  predicate. Provable when the list was constructed from elements that
  individually satisfy the predicate (e.g., filtered by the same validator).
- No general induction — just constructor-based reasoning.

### What This Is NOT

- Not an SMT solver (no Z3, no external dependencies).
- Not full dependent types (no arbitrary computation in types).
- Not a Coq/Lean proof assistant (no tactic language, no proof terms).
- Not a model checker (no state space exploration).

The goal is a practical, fast engine that handles ~80% of the `know` claims
that arise in typical Prove code, with clear indeterminate results for the
rest.

## Implementation Phases

### Phase 1: Proof Context Infrastructure

- Add `ProofContext` class holding assumptions as a list of normalised
  expressions.
- Feed `requires` and `assume` clauses into the context before checking
  `know` claims.
- `ClaimProver` gains a `context: ProofContext` parameter.

### Phase 2: Assumption Matching

- Before returning `None`, check if the claim is structurally equal to any
  assumption.
- Handle simple substitutions: if assumption is `x > 0` and claim is
  `x >= 1`, recognise equivalence for integer types.

### Phase 3: Arithmetic Rules

- Add symbolic comparison rules to `_prove_binary()`.
- Transitivity chain: maintain a partial order from assumptions.
- Commutativity: `a + b == b + a`.

### Phase 4: Ensures Propagation

- At call sites in the checker, record callee ensures in the proof context
  with `result` replaced by the binding variable.
- Requires cooperation between checker and prover — the checker passes
  accumulated facts.

### Phase 5: Match Narrowing

- When entering a match arm, add the arm's pattern constraints to the
  proof context.
- `Some(x)` -> add `x is not None` (or rather, the Option is Some).
- `Ok(v)` -> add `result is Ok`.

### Phase 6: Quantifier Basics (Future)

- Track list provenance: if a list was created by `filter(list, pred)`,
  `all(result, pred)` is trivially true.
- Very limited — no inductive proofs.

## Open Questions

- Should the proof context be visible to users (e.g., `prove check --show-context`)?
- Should indeterminate `know` claims remain warnings (W355) or become errors
  at some strictness level?
- How much does proof context affect compile speed? Need to benchmark with
  large modules.
- Should there be a `lemma` keyword for intermediate proof steps?
- Should `believe` claims be usable as assumptions for later `know` claims?
  (They're unproven but declared — using them creates a trust chain.)

## Files Likely Touched

- `prover.py` — `ProofContext` class, extend `ClaimProver`
- `_check_contracts.py` — feed requires/assume into context, pass to prover
- `checker.py` — accumulate ensures from call sites
- `types.py` — possibly normalised expression forms for matching
- `ast_nodes.py` — if proof context needs new node types
- `cli.py` — `--show-context` flag
