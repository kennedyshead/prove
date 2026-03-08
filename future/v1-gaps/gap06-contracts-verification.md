# Contracts & Verification — V1.0 Gap 06

## Overview

The contract system (`ensures`, `requires`, `know`, `assume`, `believe`, `near_miss`)
is parsed and type-checked, with property test generation for `ensures` and adversarial
tests for `believe`. However, `know` claims "the compiler can prove it" while the
compiler only type-checks it as a boolean expression. Verification chain propagation
and `near_miss` boundary distinctness are also incomplete.

## Current State

Working pieces:

- `_check_contracts()` mixin method (`_check_contracts.py:47`) handles all contract
  keywords
- `know` type-checked as boolean expression (`_check_contracts.py:114–121`)
- `assume` type-checked as boolean, emits runtime assertion (`_check_contracts.py:124–133`)
- `believe` requires `ensures` (E393), generates 3x adversarial tests
- `near_miss` generates boundary test cases: `_gen_near_miss_test()`
  (`testing.py:257`), dispatch at `testing.py:202–203`
- `ProofVerifier` in `prover.py` — structural verifier for explain/ensures/near_miss/
  believe consistency (E391, E392, E393, W321–W325). NOT a theorem prover.
- Mutation testing via `mutator.py`

## What's Missing

1. **`know` proof engine** — docs say "compiler can prove it" but the compiler just
   type-checks that the expression is boolean. No algebraic simplification, no SMT,
   no proof.

2. **Verification chain propagation** — docs say `ensures` propagates through the
   call graph and warns when called functions lack `ensures`. Current implementation
   reports statistics but does NOT emit per-call-site warnings.

3. **`near_miss` boundary distinctness** — docs say "compiler verifies each exercises
   a distinct boundary". Implementation generates test cases but doesn't verify
   distinctness.

## Implementation

### Phase 1: Lightweight proof engine for `know`

Full SMT integration is not appropriate for V1.0. Instead, implement a lightweight
algebraic simplifier that can prove simple propositions.

1. Create a `prove_claim()` method in `prover.py` that takes a boolean expression
   AST and attempts to prove it using:
   - **Constant folding**: `know 2 + 2 == 4` → trivially true
   - **Type-based**: `know x > 0` when `x` has type `Integer where > 0` → true
     from refinement constraint
   - **Contract propagation**: if a called function has `ensures result > 0`, then
     `know f(x) > 0` → true from callee's contract
   - **Algebraic simplification**: basic arithmetic identities
     (`x + 0 == x`, `x * 1 == x`, `x - x == 0`)

2. If the claim can be proven: no warning, no runtime check.
   If the claim cannot be proven: emit W-level diagnostic ("cannot prove; treating
   as runtime assertion") and fall through to `assume` behavior.

3. **Impact on existing code**: currently `know` silently passes type-checking with
   no diagnostic. After this change, existing `.prv` code using `know` with claims
   the proof engine cannot verify will see new W-level diagnostics. This is
   informational only — code still compiles and behavior is unchanged (runtime
   assertion is emitted as before). The warnings guide programmers toward provable
   claims or toward using `assume` when proof is not expected.

4. This design is sound: it never accepts false claims, it just might not prove all
   true claims.

### Phase 2: Verification chain propagation

1. In the checker, after processing all functions in a module, build a call graph.

2. For each call site where the callee lacks `ensures` contracts, emit a per-call-site
   info diagnostic: "calling unverified function `foo` from verified function `bar`".

3. Track a "verification score" per function: ratio of verified-to-unverified call
   sites. Surface in `prove check` output.

4. With `--strict`, promote unverified callee warnings to errors.

### Phase 3: `near_miss` boundary distinctness

1. In `testing.py`, after generating `near_miss` test cases, analyze the set of
   generated boundary values.

2. Check that each `near_miss` entry exercises a distinct boundary condition:
   - Extract the constraint being tested from each near-miss case
   - Verify no two cases test the same constraint at the same boundary
   - Emit W-level diagnostic for duplicate boundaries

3. This is a best-effort heuristic — exact boundary equivalence is undecidable in
   general, but common cases (same literal boundary, same comparison operator) are
   detectable.

## Files to Modify

| File | Change |
|------|--------|
| `prover.py` | Add `prove_claim()` method with algebraic simplifier |
| `_check_contracts.py:114–121` | Call `prove_claim()` for `know` expressions |
| `checker.py` | Build call graph for verification chain analysis |
| `_check_contracts.py` | Emit per-call-site warnings for unverified callees |
| `testing.py:257` | Add boundary distinctness check to `_gen_near_miss_test()` |
| `errors.py` | Register new warning codes |
| `docs/syntax.md` | Qualify `know` claim to match implementation |

## Exit Criteria

- [ ] `know` with provable claims (constants, refinements, contracts) emits no warning
- [ ] `know` with unprovable claims emits warning and falls back to runtime assertion
- [ ] Per-call-site verification chain warnings emitted
- [ ] `--strict` promotes unverified callee warnings to errors
- [ ] `near_miss` duplicate boundary detection implemented
- [ ] Tests: unit tests for proof engine (provable and unprovable cases)
- [ ] Tests: unit test for verification chain propagation
- [ ] Doc fix: `syntax.md` `know` description matches implementation
