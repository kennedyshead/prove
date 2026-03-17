# Verification Chain Propagation

**Status:** Exploring
**Roadmap:** Per-call-site warnings for unverified `ensures` chains

## Problem

Prove's contract system (`ensures`, `requires`, `know`, `believe`, `assume`)
verifies individual functions but does not track whether a function's
guarantees propagate through call chains. If function A has `ensures` clauses
and function B calls A but has no contracts of its own, the verification chain
is broken — B's callers have no compiler-checked guarantees about what B
returns, even though A's internals are verified.

The `trusted` annotation explicitly opts out of verification, but there is no
warning for functions that implicitly break the chain by simply omitting
contracts.

## Goal

Emit per-call-site warnings when a function calls verified code but does not
propagate the verification to its own signature, creating a gap in the
verification chain.

## Current State

### Contract Checking (`_check_contracts.py`)

- `ensures` expressions are type-checked and scoped (lines 92-142).
- `requires` preconditions are type-checked.
- `know` claims are attempted by `ClaimProver` — proven true, proven false
  (E356), or indeterminate (W355 warning).
- `believe` requires `ensures` to be present (E393).
- `assume` is type-checked but not proven.
- W311: intent declared but no ensures/requires.
- W323: ensures without explain (when body has 3+ statements).

### ProofVerifier (`prover.py`)

- Structural checks: W323 (ensures without explain), W324 (ensures without
  requires), W325 (explain without ensures), E391-E393.

### Trusted (`checker.py:3124`)

- Functions with `trusted` are skipped in domain profile checks.
- Trusted is an explicit opt-out — the warning system should respect it.

### What's Missing

- No tracking of which functions in a call graph have verified contracts.
- No warnings when a call chain drops from verified to unverified.
- No concept of "verification level" or "chain depth".

## Design

### Verification Status Per Function

Each function gets a verification status:

| Status | Meaning |
|--------|---------|
| **Verified** | Has `ensures` (and optionally `requires`, `know`) |
| **Trusted** | Has `trusted` annotation — explicitly unverified |
| **Unverified** | No contracts, no trusted — implicitly unverified |

### Chain Propagation Rule

**Warning W360:** A function that is **Unverified** and calls at least one
**Verified** function should warn: *"function `foo` calls verified function
`bar` but has no `ensures` clause — verification chain broken"*.

This is a **warning**, not an error. It nudges authors toward full-chain
verification without blocking compilation.

### Exceptions (No Warning)

- **Trusted functions** — explicitly opted out.
- **Main functions** — entry points don't need ensures.
- **IO verbs** (`inputs`, `outputs`, `streams`) — side-effecting functions
  often can't express postconditions purely.
- **Functions calling only unverified code** — no chain to break.

### Severity Levels

Consider a graduated approach:

1. **W360** (default): warn only when an unverified function is the *direct
   public API* (exported, not prefixed with `_`).
2. **W361** (strict mode / `--strict`): warn for all unverified functions
   that call verified ones, including internal helpers.

### Call Graph Construction

The checker already resolves function calls during type inference. The chain
analysis runs as a post-pass after all functions in a module are checked:

1. Collect verification status for each function.
2. For each **Unverified** function, check if any callee is **Verified**.
3. If yes, emit W360 with the specific call site span.

Cross-module: when calling an imported function, check if the imported
function's signature includes `ensures` (this info is available via
`stdlib_loader.py` registrations and local module registries).

## Implementation Phases

### Phase 1: Verification Status Tracking

- After checking a function, record its status in a module-level dict:
  `{func_name: "verified" | "trusted" | "unverified"}`.
- Store on the checker instance alongside existing `_function_sigs`.

### Phase 2: Call Graph Recording

- During `_check_function`, record each resolved call target in a
  `_call_graph: dict[str, set[str]]` mapping.
- Only track calls to known Prove functions (skip runtime/C calls).

### Phase 3: Chain Analysis Post-Pass

- After all functions are checked, iterate unverified functions.
- For each, check if any callee is verified.
- Emit W360 at the call site where the chain breaks.
- Include a note: *"add `ensures` to propagate verification, or `trusted`
  to opt out"*.

### Phase 4: Cross-Module Support

- When loading stdlib/imported module signatures, include verification status.
- Extend `_register_module()` to note which functions have ensures.

### Phase 5: CLI Integration

- `prove check` displays chain coverage in the verification summary.
- `prove check --strict` enables W361 for all internal functions.
- Verification summary: `"3/7 functions verified, 2 trusted, 2 chain breaks"`.

## Open Questions

- Should the warning reference the specific ensures clause that's not
  propagated, or just the general concept?
- Should `believe` count as "verified" for chain purposes? (It's weaker than
  `ensures` — the user believes but the compiler hasn't proven it.)
- How does this interact with `--coherence` mode? Chain warnings could be
  coherence-only or always-on.
- Should there be a per-function annotation to suppress W360, distinct from
  `trusted`? (e.g., `unchecked` or `@suppress(W360)`)

## Files Likely Touched

- `checker.py` — verification status dict, call graph recording, post-pass
- `_check_contracts.py` — status classification helper
- `prover.py` — possibly extend ProofVerifier with chain checks
- `cli.py` — summary display, `--strict` flag for W361
- `diagnostics.py` — W360, W361 diagnostic codes
- `stdlib_loader.py` — verification status in module signatures
