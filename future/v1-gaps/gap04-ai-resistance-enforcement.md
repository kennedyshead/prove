# AI-Resistance Enforcement — V1.0 Gap 04

## Overview

Five AI-resistance features are lexed and parsed into AST nodes but produce no semantic
effects beyond basic warnings. The module-level keywords (`temporal`, `invariant_network`)
have incomplete parsing that causes syntax highlighting and linting errors. This plan
covers enforcing the parsed features; proposed features that are not yet parsed are
covered in gap11.

## Current State

### 4a. Counterfactual annotations (`why_not`, `chosen`)

- Parsed into `FunctionDef.why_not` (list) and `FunctionDef.chosen` (str)
  (`parser.py:489–496`)
- Variables initialized at `parser.py:454`
- Formatter preserves them; LSP provides keyword completion
- **Not used** — no semantic checking, no documentation generation

### 4b. Temporal effect ordering (`temporal:`)

- Parsed in module declaration (`parser.py:1219–1226`)
- Variable initialized at `parser.py:1194`, stored at `parser.py:1295`
- **Incomplete parsing** — causes syntax highlighting and linting errors
- **No enforcement** — declared operation ordering never checked

### 4c. Intent annotations (`intent:`)

- Parsed into `FunctionDef.intent` (str) (`parser.py:516–519`)
- Stored at `parser.py:569`
- W311 warning if `intent` declared without `ensures`/`requires`
  (`_check_contracts.py:168–176`)
- **No deeper verification** — intent not compared to actual behavior

### 4d. Invariant networks (`invariant_network`, `satisfies`)

- `invariant_network` blocks parsed with rules (`parser.py:1260–1261`,
  `_parse_invariant_network()` at `parser.py:1307–1330`)
- `satisfies` parsed on function definitions; checker validates reference
  exists (E382)
- **Incomplete parsing** — causes syntax highlighting and linting errors
- **No invariant verification** — rules never checked against implementations
- **No cross-function coherence checking**

### 4e. Domain declarations (`domain`)

- Keyword recognized but not substantively parsed or used
- **No enforcement or use**

## What's Missing

1. **Parsing fixes** — `temporal`, `invariant_network`, and `domain` cause errors
   in syntax highlighting and linting when used
2. **Temporal ordering enforcement** — checker should verify operation order
3. **Invariant network rule verification** — rules should be checked against
   function implementations
4. **Intent verification** — intent should be compared to actual behavior
5. **Counterfactual documentation** — `why_not`/`chosen` should surface in output

## Implementation

### Phase 1: Fix module-level parsing (temporal, domain, invariant_network)

1. Audit `_parse_module_decl()` (`parser.py:1194–1295`) for the parsing issues
   that cause syntax highlighting errors.

2. Fix token consumption so that `temporal:`, `domain:`, and `invariant_network`
   blocks parse cleanly without leaving orphaned tokens.

3. Update tree-sitter grammar (`tree-sitter-prove`) to handle these keywords.

4. Verify `module_features_demo` example parses without errors for these features.

### Phase 2: Temporal ordering enforcement

1. In `checker.py`, after collecting the module's `temporal:` declaration, build an
   ordered list of operation names.

2. For each function in the module, check that calls to temporal operations occur in
   the declared order. Emit a new error code if ordering is violated.

3. Handle conditional branches: if operation B is in both arms of a match, it
   satisfies ordering regardless of which arm executes.

### Phase 3: Invariant network verification

1. In `_check_contracts.py`, after collecting `invariant_network` rules, iterate
   over functions that declare `satisfies`.

2. For each rule in the network, verify that the function's `ensures` contracts are
   compatible with the rule's requirements. Emit a new error code for violations.

3. For cross-function coherence: verify that all functions satisfying the same
   network collectively cover all rules.

### Phase 4: Intent and counterfactual features

1. **Intent verification**: Compare `intent:` text against function contracts
   (`ensures`/`requires`) using keyword matching. If the intent mentions concepts
   not reflected in contracts, emit a warning.

2. **Domain tags**: Store domain tag on module AST node. Use it to scope
   `invariant_network` rules and enable domain-specific checking in future.

3. **Counterfactual documentation**: Include `why_not` and `chosen` in
   `prove check --verbose` output and in LSP hover information.

## Files to Modify

| File | Change |
|------|--------|
| `parser.py:1194–1295` | Fix module-level keyword parsing |
| `parser.py:1307–1330` | Fix `invariant_network` parsing |
| `checker.py` | Add temporal ordering verification pass |
| `_check_contracts.py:168–176` | Extend intent checking; add invariant verification |
| `errors.py` | Register new error/warning codes |
| `tree-sitter-prove/` | Update grammar for module-level keywords |

## Exit Criteria

- [ ] `temporal:`, `domain:`, `invariant_network` parse without errors
- [ ] `module_features_demo` no longer expected-to-fail for AI-resistance parsing
- [ ] Temporal ordering violations produce errors
- [ ] Invariant network rules verified against `satisfies` functions
- [ ] `why_not`/`chosen` visible in check output and LSP hover
- [ ] Intent warning (W311) remains; deeper intent comparison emits info diagnostic
- [ ] Tests: unit tests for each enforcement phase
- [ ] Tests: e2e example exercising temporal ordering
- [ ] Doc fix: `ai-resistance.md` "Parsed" section updated to reflect enforcement
