# 08 — Invariant Network Property Test Generation

## Status: Post-1.0

### Background

The compiler currently validates invariant network structure: constraint
expressions must be Boolean (E396), `satisfies` must reference a known network
(E382), and functions with `satisfies` must have `ensures` clauses (W391). It
does **not** verify that `ensures` clauses actually imply the invariant
constraints.

### Feature

Extend `TestGenerator` to emit property tests that call the function with
random inputs and assert every constraint in the declared `invariant_network`
holds on the result. This is the same strategy already used for `ensures` and
`believe`.

For each function with `satisfies NetworkName`:
1. Look up the constraints in the `invariant_network` declaration.
2. For each constraint, emit a property test that invokes the function and
   asserts the constraint holds on the return value.
3. Report failures via the same property-test infrastructure.

### Effort

Moderate — the infrastructure (random input generation, property test emission,
test runner wiring) already exists. The new work is extracting invariant
constraints after type-checking and threading them into `TestGenerator`.

### Why Post-1.0

The docs already accurately describe what the compiler does (structural
validation + `ensures` requirement). Property-test verification is a meaningful
improvement in confidence, but not required for correctness of the V1.0 language.
