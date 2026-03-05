# AI Resistance

Prove's AI-resistance features fall into four categories based on implementation status. The design goal is twofold: resist AI *generating* correct Prove code, and resist AI *training on* Prove source code.

---

## Implemented

These mechanisms are enforced by the current compiler.

### Implementation Explanation as Code

`explain` documents the chain of operations in the `from` block using controlled natural language. With `ensures` present, the compiler parses each row for operations (action verbs), connectors, and references to identifiers — then verifies them against called functions' contracts. Sugar words ("the", "applicable", etc.) are ignored, keeping explain readable as English while remaining machine-verifiable. AI can generate plausible-looking explanations, but they won't verify — operations must match real function behaviors, and references must be real identifiers.

```prove
transforms merge_sort(xs List<T>) Sorted<List<T>>
  explain
      split the list at the midpoint
      recursively sort the first half
      recursively sort the second half
      merge both sorted halves preserving order
  terminates: len(xs)
from
    halves as Pair<List<T>> = split_at(xs, len(xs) / 2)
    left as Sorted<List<T>> = merge_sort(halves.first)
    right as Sorted<List<T>> = merge_sort(halves.second)
    merge(left, right)
```

### Verb Purity Enforcement

The compiler enforces that pure verbs (`transforms`, `validates`, `reads`, `creates`, `matches`) cannot perform IO, cannot be failable, and cannot call IO functions. This is checked at compile time — errors E361, E362, E363.

### Exhaustive Match

Match expressions on algebraic types must cover all variants or include a wildcard. The compiler rejects non-exhaustive matches (E371) and warns about unreachable arms (I301). AI-generated code that forgets a variant does not compile.

### Adversarial Type Puzzles (Refinement Types)

Refinement types encode constraints requiring genuine reasoning, not just pattern matching:

```prove
type BalancedTree<T> is
  Node(left BalancedTree<T>, right BalancedTree<T>)
  where abs(left.depth - right.depth) <= 1

transforms insert(tree BalancedTree<T>, val T) BalancedTree<T>
  // Can't just pattern match — you need to construct a value
  // that satisfies the depth constraint, which requires
  // understanding rotation logic
```

### Adversarial Near-Miss Examples

`near_miss` declares inputs that *almost* break the code but don't. The compiler verifies each near-miss exercises a distinct branch or boundary condition. Redundant near-misses are rejected (W322). AI can memorize correct implementations but cannot identify the *diagnostic* inputs that prove understanding.

```prove
validates leap_year(y Year)
  near_miss: 1900  => false
  near_miss: 2000  => true
  near_miss: 2100  => false
from
    y % 4 == 0 && (y % 100 != 0 || y % 400 == 0)
```

### Epistemic Checking (Basic)

`know`, `assume`, and `believe` are parsed and type-checked — their expressions must be Boolean (E384, E385, E386). `believe` requires `ensures` to be present (E393). Full semantic enforcement (proving `know` claims, inserting runtime checks for `assume`, generating adversarial tests for `believe`) is upcoming.

```prove
transforms process_order(order Order) Receipt
  know: len(order.items) > 0            // must be Boolean (E384 if not)
  assume: order.total == sum(prices)    // must be Boolean (E385 if not)
  believe: order.user.is_verified       // requires ensures (E393 if missing)
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

## Parsed (Syntax Ready, Enforcement Upcoming)

These keywords are parsed and stored in the AST, but the compiler does not yet enforce their semantic claims. They currently serve as documentation.

### Counterfactual Annotations: `why_not`, `chosen`

Every non-trivial design choice can explain what would break under alternative approaches.

```prove
transforms evict(cache Cache:[Mutable]) Option<Entry>
  why_not: "FIFO would evict still-hot entries under burst traffic"
  why_not: "Random eviction has unbounded worst-case for repeated keys"
  chosen: "LRU because access recency correlates with reuse probability"
from
    // LRU implementation
```

*Upcoming:* The compiler will verify the `chosen` rationale is consistent with the implementation's actual behavior. `why_not` clauses will be checked for plausibility against the function's type signature and effects.

### Temporal Effect Ordering

Not just *what* effects a function has, but the *required order* — enforced across function boundaries and call graphs.

```prove
module Auth
  temporal: authenticate -> authorize -> access

  inputs authenticate(creds Credentials) Token!
  transforms authorize(token Token, resource Resource) Permission
  inputs access(perm Permission, resource Resource) Data!
```

*Upcoming:* The compiler will build a call graph and verify temporal constraints are satisfied across all execution paths.

### Intent Annotations

`intent` documents the purpose of a function.

```prove
transforms filter_valid(records List<Record>) List<Record>
  intent: "keep only valid records"
from
  filter(records, valid record)
```

It goes in the function **header**, not inside the body.

### Invariant Networks: `invariant_network`, `satisfies`

Define networks of mutually-dependent invariants. Changing one cascades verification across the entire network.

```prove
invariant_network AccountingRules
  total_assets == total_liabilities + equity
  revenue - expenses == net_income
  every(transaction) preserves total_assets == total_liabilities + equity

transforms post_transaction(ledger Ledger, tx Transaction) Ledger
  satisfies AccountingRules
from
    // implementation
```

*Upcoming:* Constraint solver that scales across modules.

### Domain Declarations

`domain` tags a module's problem domain, potentially enabling domain-specific rules.

```prove
module PaymentService
  domain Finance
```

*Upcoming:* Domain-specific keyword behavior and operator semantics.

---

## Upcoming

These features are designed but not yet implemented (neither parsed nor enforced).

### Refutation Challenges

The compiler deliberately generates plausible-but-wrong alternative implementations and requires the programmer to explain why they fail. Compilation becomes a dialogue.

```
$ prove check src/sort.prv

challenge[C017]: Why doesn't this simpler implementation work?

  transforms sort(xs List<Integer>) Sorted<List<Integer>>
      reverse(dedup(xs))     // appears sorted for some inputs

  refute: _______________

  hint: Consider [3, 1, 2]
```

The programmer must provide a counterexample or logical argument. The compiler verifies the refutation is valid.

### Semantic Commit Verification

The compiler diffs the previous version, reads the commit message, and verifies the change actually addresses the described bug.

```prove
commit "fix: off-by-one in pagination — last page was empty
       when total % page_size == 0"

// Vague messages like "fix stuff" don't compile.
```

### Context-Dependent Syntax

Instead of fixed keywords, the language adapts syntax based on the module's declared domain. AI cannot memorize syntax because it shifts per-context.

```prove
domain Finance
  // "balance" is now a keyword, arithmetic operators
  // follow financial rounding rules
  total as Balance = sum(ledger.entries)

domain Physics
  // "balance" is just an identifier again
  // operators now track units
  balance as Acceleration = force / mass
```

### Non-Local Coherence Enforcement

The compiler enforces that an entire module tells a coherent "story." Functions unrelated to the narrative produce compile errors.

```prove
module UserAuth
  narrative: """
  Users authenticate with credentials, receive a session token,
  and the token is validated on each request.
  """

  inputs login(creds Credentials) Session!
  transforms validate(token Token) User
  outputs expire(session Session)
  // outputs send_email(...)   // compiler error: unrelated to narrative
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

**The design answers both questions:** Prove resists AI *writing* the code (generation resistance) and resists AI *training on* the code (anti-training).
