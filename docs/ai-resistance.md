---
title: AI Resistance - Prove Programming Language
description: Learn about Prove's AI-resistance features including binary AST format, intent declarations, and anti-training license.
keywords: AI resistance, AI slop, code scraping, anti-training, binary AST
---

# AI Resistance

Prove's AI-resistance features fall into four categories based on implementation status. The design goal is twofold: resist AI *generating* correct Prove code, and resist AI *training on* Prove source code.

These same features serve a broader purpose. The intent declarations, verifiable explanations, and coherence checks that make AI generation difficult are also the foundation for Prove's [vision](vision.md) of local, self-contained development — where your project's own declarations drive code generation without external services. AI resistance is a consequence of intent-first design, not the other way around.

---

### Implementation Explanation as Code

[`explain`](contracts.md#explain) documents the chain of operations in the `from` block using controlled natural language. With [`ensures`](contracts.md#requires-and-ensures) present, the compiler parses each row for operations (action verbs), connectors, and references to identifiers — then verifies them against called functions' contracts. Sugar words ("the", "applicable", etc.) are ignored, keeping explain readable as English while remaining machine-verifiable. AI can generate plausible-looking explanations, but they won't verify — operations must match real function behaviors, and references must be real identifiers. See [Contracts & Annotations — explain](contracts.md#explain) for full syntax.

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

### Verb Purity Enforcement

The compiler enforces that [pure verbs](functions.md#intent-verbs) (`transforms`, `validates`, `reads`, `creates`, `matches`) cannot perform IO, cannot be failable, and cannot call IO functions. This is checked at compile time — errors [E361](diagnostics.md#e361-pure-function-cannot-be-failable), [E362](diagnostics.md#e362-pure-function-cannot-call-io-builtin), [E363](diagnostics.md#e363-pure-function-cannot-call-user-defined-io-function).

### Exhaustive Match

[Match expressions](types.md#pattern-matching) on algebraic types must cover all variants or include a wildcard. The compiler rejects non-exhaustive matches and warns about unreachable arms ([I301](diagnostics.md#i301-unreachable-match-arm)). AI-generated code that forgets a variant does not compile.

### Adversarial Type Puzzles (Refinement Types)

[Refinement types](types.md#refinement-types) encode constraints requiring genuine reasoning, not just pattern matching:

```prove
type BalancedTree<Value> is
  Node(left BalancedTree<Value>, right BalancedTree<Value>)
  where abs(left.depth - right.depth) <= 1

transforms insert(tree BalancedTree<Value>, val Value) BalancedTree<Value>
  // Can't just pattern match — you need to construct a value
  // that satisfies the depth constraint, which requires
  // understanding rotation logic
```

### Adversarial Near-Miss Examples

[`near_miss`](contracts.md#near_miss) declares inputs that *almost* break the code but don't. The compiler verifies each near-miss exercises a distinct branch or boundary condition. Redundant near-misses are rejected ([W322](diagnostics.md#w322-duplicate-near-miss-input)). AI can memorize correct implementations but cannot identify the *diagnostic* inputs that prove understanding.

```prove
validates leap_year(y Year)
  near_miss 1900 => false
  near_miss 2000 => true
  near_miss 2100 => false
from
    (y % 4) == 0 && ((y % 100) != 0 || (y % 400) == 0)
```

### Epistemic Checking (Basic)

[`know`, `assume`, and `believe`](contracts.md#epistemic-annotations) are parsed and type-checked — their expressions must be Boolean ([E384](diagnostics.md#e384-know-expression-must-be-boolean), [E385](diagnostics.md#e385-assume-expression-must-be-boolean), [E386](diagnostics.md#e386-believe-expression-must-be-boolean)). `believe` requires `ensures` to be present ([E393](diagnostics.md#e393-believe-without-ensures)). `know` claims are proven when possible via constant folding and algebraic identities — provably false claims are errors ([E356](diagnostics.md#e356-know-claim-is-provably-false)), unprovable claims fall back to runtime assertions ([W327](diagnostics.md#w327-know-claim-cannot-be-proven)). `assume` inserts a runtime check. Remaining: generating adversarial tests for `believe`.

```prove
transforms process_order(order Order) Receipt
  know: len(order.items) > 0
  assume: order.total == sum(prices)
  believe: order.user.is_verified
from
    // implementation
```

### Anti-Training License for Prove Code

Every `prove new` project is initialized with the **Prove Source License v1.0**. It is a permissive MIT-style license with comprehensive AI restrictions covering:

- **Training, fine-tuning, and distillation** (Section 3.1)
- **Dataset inclusion, vector stores, RAG indices, and embedding databases** (Section 3.2)
- **Synthetic data generation** from the Software (Section 3.3)
- **Sublicensing for AI use** — third parties cannot be granted AI rights (Section 3.4)
- **Downstream propagation** — all redistributors must carry the restrictions forward (Section 3.5)
- **Technical protection circumvention** — bypassing binary format, normalization, or signatures for AI training is a breach (Section 4)

The license explicitly permits using AI tools *to write* Prove code and building AI-powered applications *with* Prove — it only prohibits using Prove source *as training data*.

The Prove Source License covers the language, its specification, and `.prv` source code. The compiler tooling (Python bootstrap, docs, editor integrations) is separately licensed under Apache-2.0 — see [AI Transparency](design.md#ai-transparency) for the reasoning behind this split.

---

## Intent and Counterfactual Annotations

These keywords are parsed and stored in the AST, and the compiler enforces their semantic claims.

### Intent Annotations

[`intent`](contracts.md#intent) documents the purpose of a function in plain prose.

```prove
transforms filter_valid(records List<Record>) List<Record>
  intent: "keep only valid records"
from
    filter(records, valid record)
```

It goes in the function **header**, not inside the body.

The compiler verifies the `intent` prose is consistent with the function's actual behavior:
- W501: Verb not described in module narrative
- W502: Explain entry doesn't match from-body  
- W504: Chosen text doesn't relate to from-body
- W505: Why-not entry mentions no known name
- W506: Why-not entry contradicts from-body

---

## Counterfactual Annotations

Every non-trivial design choice can explain what would break under alternative approaches. The compiler checks that `why_not` and `chosen` annotations are coherent with the implementation. See [Contracts & Annotations — Counterfactual Annotations](contracts.md#counterfactual-annotations) for the full reference.

```prove
transforms evict(cache Cache:[Mutable]) Option<Entry>
  why_not: "FIFO would evict still-hot entries under burst traffic"
  why_not: "Random eviction has unbounded worst-case for repeated keys"
  chosen: "LRU because access recency correlates with reuse probability"
from
    // LRU implementation
```

Four checks are active on every function that uses `why_not` or `chosen`:

- **[W503](diagnostics.md#w503-chosen-declared-without-why_not)** — `chosen:` declared without any `why_not:` entry. Design decisions are more valuable when paired with trade-offs.
- **[W504](diagnostics.md#w504-chosen-text-doesnt-relate-to-from-body)** — `chosen:` text has no overlap with operations or parameters in the `from` block. The rationale should relate to what the code actually does.
- **[W505](diagnostics.md#w505-why-not-entry-mentions-no-known-name)** — a `why_not:` entry contains no identifier from the current scope. Rejection notes must anchor to a concrete function, type, or algorithm.
- **[W506](diagnostics.md#w506-why-not-entry-contradicts-from-body)** — a `why_not:` entry rejects an approach whose function name appears in the `from` block. The rejected approach is in use, which contradicts the rationale.

AI can generate plausible-looking counterfactuals, but they won't satisfy these structural checks without understanding the actual implementation.

## Temporal Effect Ordering

A module's `temporal:` declaration constrains the required call order for its operations. The compiler enforces this within function bodies — calling a later step before an earlier one is an error. See [Contracts & Annotations — Module-Level Annotations](contracts.md#module-level-annotations) for the declaration syntax.

```prove
module Auth
  temporal: authenticate -> authorize -> access

  inputs authenticate(creds Credentials) Token!
  transforms authorize(token Token, resource Resource) Permission
  inputs access(perm Permission, resource Resource) Data!
```

**[W390](diagnostics.md#w390-temporal-operation-out-of-declared-order)** fires when a function body calls temporal operations in the wrong order.

## Invariant Networks

`invariant_network` declarations define sets of mutually-dependent constraints. Functions that claim to satisfy a network use `satisfies`. The compiler validates that constraint expressions are well-typed and that functions with `satisfies` provide `ensures` clauses to document how the invariant is maintained. See [Contracts & Annotations — Invariant Networks](contracts.md#invariant-networks) for the full reference.

```prove
invariant_network AccountingRules
  total_assets == total_liabilities + equity
  revenue - expenses == net_income

transforms post_transaction(ledger Ledger, tx Transaction) Ledger
  satisfies AccountingRules
  ensures result.total_assets == result.total_liabilities + result.equity
from
    // implementation
```

- **[E382](diagnostics.md#e382-satisfies-references-undefined-type)** — `satisfies` references an unknown invariant network.
- **[E396](diagnostics.md#e396-invariant-constraint-must-be-boolean)** — a constraint expression in an `invariant_network` is not Boolean.
- **[W391](diagnostics.md#w391-satisfies-invariant-without-ensures)** — a function declares `satisfies` but has no `ensures` clauses; without postconditions the invariant cannot be verified.

## Domain Declarations

A module's `domain:` tag selects a built-in enforcement profile that adds domain-specific warnings. See [Contracts & Annotations — Module-Level Annotations](contracts.md#module-level-annotations).

```prove
module Accounting
  domain finance
```

Active profiles:

- **finance** — prefer `Decimal` over `Float` ([W340](diagnostics.md#w340-domain-profile-violation)); require `ensures` contracts and `near_miss` examples ([W341](diagnostics.md#w341-missing-required-contract-for-domain), [W342](diagnostics.md#w342-missing-required-annotation-for-domain))
- **safety** — require `ensures`, `requires`, and `explain` blocks
- **general** — no additional requirements

## Refutation Challenges

The compiler generates plausible-but-wrong alternative implementations using its mutation testing engine and requires the programmer to explain (via `why_not`) why they fail.

Run `prove check --challenges` to see unaddressed challenges for functions with `ensures` contracts. Each challenge is a mutation of the function body that might violate the contract:

```bash
$ prove check --challenges

  transforms sort — 3 challenges, 1 addressed:
    [+] swap + to - in comparison
    [-] replace < with <=
    [-] change constant 0 to 1
```

Address challenges by adding `why_not` annotations to the function.

## Domain Profiles

A module's [`domain:`](contracts.md#module-level-annotations) declaration selects a built-in profile that adds domain-specific warnings ([W340–W342](diagnostics.md)):

- **finance**: prefer `Decimal` over `Float`, require `ensures` contracts and `near_miss` examples
- **safety**: require `ensures`, `requires`, `explain` blocks
- **general**: no additional requirements

```prove
module Accounting
  domain finance

// W340: domain 'finance' prefers Decimal over Float

transforms total(amounts List<Float>) Float
from
    reduce(amounts, 0.0, add)
```

## Coherence Checking

Run [`prove check --coherence`](cli.md) to verify vocabulary consistency between the module's [`narrative:`](contracts.md#module-level-annotations) and its function/type names ([I340](diagnostics.md)). The compiler extracts key words from the narrative and checks that function names use related vocabulary:

```prove
module UserAuth
  narrative: """
  Users authenticate with credentials, receive a session token,
  and the token is validated on each request.
  """

  inputs login(creds Credentials) Session!
  transforms validate(token Token) User
  outputs expire(session Session)
  // I340: 'send_email' — vocabulary not found in narrative
```

## Proposed — Semantic Commit Verification (Post-1.0)

The compiler diffs the previous version, reads the commit message, and verifies the change actually addresses the described bug. Deferred to post-1.0 due to the inherent complexity of natural language understanding.

```prove
commit "fix: off-by-one in pagination — last page was empty
       when total % page_size == 0"

// Vague messages like "fix stuff" don't compile.
```

---

## Future Research (Post-1.0)

These are anti-training mechanisms that make Prove source code resistant to being useful as AI training data. They require significant toolchain changes and are deferred to post-1.0.

### Structured Source Format (Binary `.prv`)

`.prv` files stored as a compact binary AST, not human-readable text. The `prove` CLI provides views:

```bash
$ prove view src/server.prv              # pretty-print to terminal
```

The editor experience is seamless — the language server decodes `.prv` on the fly, and the formatter writes binary back. Web scrapers and training pipelines see binary blobs, not parseable source code.

### Semantic Normalization

The compiler canonicalizes all code before storage. Variable names, ordering of declarations, whitespace, and stylistic choices are normalized away. A name map is stored alongside the canonical AST. The LSP reconstructs human-readable code on demand.

```prove
// What you write:
transforms calculate_total_price(items List<Item>, tax TaxRate) Price
from
    subtotal as Decimal = sum(prices(items))
    subtotal * (1 + tax.rate)

// What is stored (canonical form):
transforms _f0(_a0 List<_T0>, _a1 _T1) _T2
from
    _v0 as _T3 = _f1(_f2(_a0))
    _v0 * (1 + _a1._f3)
```

### Fragmented Source

A function's complete definition is distributed across multiple files that only make sense together:

```
src/
  server.prv          # implementation (canonical binary AST)
  server.explain      # implementation explanations
  server.intent       # intent declarations
  server.near_miss    # adversarial near-miss examples
  server.narrative    # module narrative
```

All files are required to compile. No single artifact is useful in isolation.

### Identity-Bound Compilation

Source files carry a cryptographic signature chain. The compiler verifies authorship. Scraped code with stripped signatures won't compile.

### Project-Specific Grammars

Each project can define syntactic extensions via `prove.toml`. Two Prove projects may look completely different at the surface level, destroying the statistical regularities that AI training depends on.

---

## The Fundamental Tension

Every feature that makes code harder for AI also makes it harder for humans.

The AI-resistance features force the programmer to:

- **Explain their reasoning** (explain, intents, narratives, counterfactuals)
- **Maintain global coherence** (not just local correctness)
- **Understand *why*, not just *what*** (near-misses, refutation challenges)
- **Acknowledge uncertainty** (epistemic annotations)
- **Respect temporal protocols** (effect ordering)

The uncomfortable truth is that the things AI is bad at are the things lazy humans skip too. A language that resists AI would also resist copy-paste programming, cargo-culting Stack Overflow, and coding without understanding.

The anti-training features (binary format, semantic normalization, fragmented source) add friction to sharing and collaboration. The mitigation is a first-class toolchain: the `prove` CLI and LSP make the experience seamless for developers working inside the ecosystem, while making the code opaque to anything outside it.

These same features — intent declarations, verifiable explanations, coherence checking — are also the building blocks for Prove's [local generation model](vision.md#local-self-contained-development). The things that make code hard for external AI to generate are exactly what make it possible for the *project's own toolchain* to generate structure from declared intent. The friction is selective: it blocks opaque external generation while enabling transparent local generation.

**The design answers both questions:** Prove resists AI *writing* the code (generation resistance) and resists AI *training on* the code (anti-training). And the same mechanisms enable [self-contained development](vision.md) where the programmer remains the author.
