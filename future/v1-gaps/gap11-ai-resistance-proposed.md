# AI-Resistance Proposed Features — V1.0 Gap 11

## Overview

Four AI-resistance features are documented in `docs/ai-resistance.md` under "Proposed"
but have no implementation — not even parsed. This plan assesses feasibility and
outlines implementation approaches for each. Semantic commit verification is deferred
to post-1.0; the other three features are V1.0.

Depends on gap04 (AI-resistance enforcement) being substantially complete, since
these features build on the enforcement infrastructure.

## Current State

From `docs/ai-resistance.md` "Proposed" section:

1. **Refutation challenges** — compiler generates plausible-but-wrong alternatives,
   programmer must explain why they fail
2. **Semantic commit verification** — compiler verifies commit messages match changes
3. **Context-dependent syntax** — syntax adapts based on module's `domain`
4. **Non-local coherence enforcement** — module must tell coherent "story"

None of these are parsed, type-checked, or emitted. No AST nodes exist.

## Feasibility Assessment

### 1. Refutation challenges — Medium feasibility

**Concept**: For functions with `ensures` contracts, the compiler generates alternative
implementations that are plausible but violate the contract. The programmer must explain
(via `why_not`) why each alternative fails.

**Approach**:
- Use the mutation testing infrastructure (`mutator.py`) as the alternative generator
- For each function with `ensures`, generate N mutants
- Present mutants to the programmer during `prove check --challenges`
- Programmer adds `why_not` annotations explaining each rejection
- Compiler verifies that the `why_not` explanations reference the specific mutation

**Complexity**: Medium. The mutation infrastructure exists. The challenge is designing
a good UX for presenting challenges and validating responses.

**V1.0 scope**: CLI mode (`prove check --challenges`) that presents mutants and
validates `why_not` annotations. No interactive mode.

### 2. Semantic commit verification — Low feasibility for V1.0

**Concept**: When committing code changes, the compiler verifies that the commit
message accurately describes the semantic changes.

**Approach**:
- Git hook integration: `prove verify-commit` command
- Parse the commit message for intent keywords (add, fix, refactor, remove)
- Diff the changed `.prv` files
- Compare: "add function X" matches a new function definition in the diff
- Compare: "fix bug in Y" matches a modification to function Y

**Complexity**: High. Natural language understanding of commit messages is inherently
fuzzy. Keyword matching produces false positives/negatives.

**V1.0 scope**: Defer. The signal-to-noise ratio of keyword-based commit verification
is too low to be useful without AI/NLP, which contradicts the language's philosophy.

### 3. Context-dependent syntax — Medium feasibility

**Concept**: A module's `domain` declaration influences what syntax is available or
required within that module.

**Approach**:
- Requires gap04's `domain:` parsing to be complete
- Define domain profiles: e.g., `domain: "finance"` requires `Decimal` over `Float`,
  mandates `ensures` on all public functions, requires `near_miss` for boundary cases
- In the checker, load domain profile and apply additional rules
- Domain profiles defined in a `domains.toml` or as built-in presets

**Complexity**: Medium. The mechanism is straightforward (conditional checker rules).
The challenge is defining useful domain profiles.

**V1.0 scope**: Possible. Start with 2–3 built-in domain profiles (`finance`,
`safety`, `general`) that add domain-specific warnings.

### 4. Non-local coherence enforcement — High feasibility

**Concept**: A module must tell a coherent "story" — its `narrative:`, function names,
contracts, and `explain` blocks should be internally consistent.

**Approach**:
- Extract key concepts from `narrative:` docstring (simple keyword extraction)
- Check that function names, parameter names, and type names use vocabulary from
  the narrative's concept set
- Check that `explain` blocks reference concepts mentioned in the narrative
- Emit info-level diagnostics for vocabulary drift

**Complexity**: Low-medium. This is essentially vocabulary consistency checking, not
semantic understanding.

**V1.0 scope**: Possible. Implement as `prove check --coherence` flag.

## Implementation

### Phase 1: Refutation challenges

1. Add `prove check --challenges` flag to `cli.py`.

2. In `testing.py`, extend mutation test generation:
   - For each function with `ensures`, generate 3–5 mutants using `mutator.py`
   - Format mutants as challenge descriptions

3. In `_check_contracts.py`, validate `why_not` annotations:
   - Each `why_not` entry should correspond to a plausible mutation
   - Verify the `why_not` text references the specific behavior that changes

4. Output: list of unaddressed challenges (functions with `ensures` but missing
   `why_not` for generated mutants).

### Phase 2: Context-dependent syntax (domain profiles)

1. Define domain profiles as Python dicts in a new `domains.py` module:
   ```python
   DOMAIN_PROFILES = {
       "finance": {
           "required_types": ["Decimal"],  # Float usage warns
           "required_contracts": ["ensures"],  # public functions must have ensures
           "required_annotations": ["near_miss"],  # boundary cases required
       },
       "safety": {
           "required_contracts": ["ensures", "requires"],
           "required_annotations": ["terminates", "explain"],
       },
   }
   ```

2. In the checker, after resolving the module's `domain:` tag, load the profile
   and apply additional checks.

3. Domain violations emit W-level diagnostics.

### Phase 3: Non-local coherence checking

1. Add `--coherence` flag to `prove check` in `cli.py`.

2. Extract vocabulary from `narrative:` block (split into words, normalize).

3. Check function names, parameter names, and type names against vocabulary.

4. Emit info-level diagnostics for names that don't overlap with narrative vocabulary.

### Phase 4: Semantic commit verification (deferred)

Documented here for future reference but deferred to post-1.0. If implemented:
- `prove verify-commit` CLI command
- Git hook template in `prove new` project scaffolding
- Keyword-based diff analysis

## Files to Modify

| File | Change |
|------|--------|
| `cli.py` | Add `--challenges` and `--coherence` flags |
| `testing.py` | Extend mutation generation for challenges |
| `_check_contracts.py` | Validate `why_not` against mutations |
| `domains.py` (new) | Domain profile definitions |
| `checker.py` | Domain profile application |
| `prover.py` | Coherence vocabulary analysis |

## Exit Criteria

### V1.0

- [ ] `prove check --challenges` generates and displays refutation challenges
- [ ] `why_not` annotations validated against generated challenges
- [ ] 2–3 built-in domain profiles with domain-specific warnings
- [ ] `prove check --coherence` checks vocabulary consistency
- [ ] Tests: unit tests for each feature
- [ ] Docs: `ai-resistance.md` "Proposed" section updated with implementation status

### Deferred to post-1.0

- [ ] Semantic commit verification
- [ ] Custom domain profiles via `prove.toml`
- [ ] Interactive challenge mode
