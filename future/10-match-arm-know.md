# `know` Claims Inside Match Arms

**Status:** Exploring
**Roadmap:** `docs/roadmap.md` → Exploring section

## Background

Phase 5 of formal `know` proofs added match arm structural narrowing to `ProofContext`:
the checker records `(subject, variant, bindings)` tuples when it sees `Some(x)`,
`Ok(v)`, `Err(e)`, or `None` arms. `ClaimProver._prove_from_match_bindings()` uses
these to confirm `subj != None` when a `Some` arm is reached.

This infrastructure is function-level — `know` claims are checked against the full
function proof context, which includes all match arm bindings from all arms. What is
missing is **arm-level** proof checking: allowing `know` claims inside individual
match arms that reference the locally bound variable.

```prove
transforms safe_head(xs Option<List<Value>>) Integer
  ensures result >= 0
from
  match xs
    Some(inner) =>
      know: len(inner) > 0    // wants to use `inner` — not yet supported
      List.head(inner)
    None => 0
```

---

## Problem

`know` claims currently appear only in the function header (between the signature
and `from`). They are checked against the proof context built from `requires`,
`assume`, `believe`, callee ensures, and match bindings.

There is no syntax or checker support for `know` claims inside a match arm body.
The bound variable `inner` is in scope within the arm's expression, but the proof
context does not reflect arm-local narrowing deeply enough to prove claims about it.

---

## Goal

Allow `know:` annotations inside match arm bodies. An arm-level `know` is checked
against the function's proof context **plus** the arm's structural binding facts.

```prove
match xs
  Some(inner) =>
    know: len(inner) > 0    // proven from: requires xs is Some(_) AND requires len(xs) > 0
    List.head(inner)
  None => 0
```

---

## Design

### Syntax

`know:` inside a match arm body — parsed as a `KnowStmt` (or `KnowAnnotation`)
within the arm's statement list. The parser already handles `know:` in function
headers; the same node can be reused in arm bodies.

### AST Changes

`MatchArm` currently holds `pattern` and `body` (expression or statement list).
Allow `KnowStmt` nodes in the arm body before the final expression:

```python
@dataclass(frozen=True)
class MatchArm:
    pattern: Pattern
    know: list[Expr]      # new: arm-level know claims
    body: Expr | list[Stmt]
    span: Span
```

### Checker Changes

In `_check_contracts.py` (or a new `_check_match_arm_know()`):

1. When entering a match arm during contract checking, build an **arm-local proof context**:
   - All facts from the function-level `ProofContext`
   - Add the arm's structural binding (e.g., `subject == Some(_)` and `inner` bound)
   - Add any `ensures` from callee functions called in the arm before the `know`
2. Check each arm-level `know` claim against this arm-local context
3. Emit W372 (or next available) if the claim cannot be proven

### Proof Context Enrichment for Arms

The arm binding `Some(inner)` already records `(subject, "Some", ["inner"])` in
the function-level context. For arm-level checking, additionally add:

- `inner != None` (since `inner` is the unwrapped value, it cannot be None)
- Any `requires` that constrain `subject` carry over with substitution:
  `requires xs != None` → `inner != None` (substituting the unwrapped name)

### Files to Touch

- `prove-py/src/prove/ast_nodes.py` — add `know` field to `MatchArm`
- `prove-py/src/prove/parser.py` — parse `know:` in arm body
- `prove-py/src/prove/_check_contracts.py` — arm-local proof context, arm `know` checking
- `prove-py/src/prove/prover.py` — extend `ProofContext` to support arm-local push/pop
- `prove-py/src/prove/errors.py` — register W372 (arm `know` cannot be proven)
- `prove-py/tests/test_checker_contracts.py` — arm-level know tests
- `docs/contracts.md` — remove *Upcoming* from match arm narrowing section
- `docs/diagnostics.md` — document W372

---

## Open Questions

1. Should arm-level `know` failures be W-warnings or E-errors? Consistent with
   function-level `know` (W370/W371 range) → warnings.
    - Error is for compiler-breaking and Warning is for added value to compiled program
2. Can arm-level `know` claims be referenced by subsequent function-level `know`
   claims? Probably not for V1.0 — keep arm-level and function-level separate.
    - Keep arm-level seperate for now
3. Should arm-level `know` appear before or after the arm body expression?
   Before — it documents an assumption before the computation, consistent with
   how `know:` reads in function headers.
   do not change how we already setup the structure! between Verb > from is the place for all contracts!

## After Implementation

- Delete this file
- Update `docs/roadmap.md` (remove from Exploring)
- Update `docs/contracts.md`: remove *Upcoming* from match arm narrowing section
