# AI Resistance

## Phase 1 — Generation Resistance

AI models generate code by pattern-matching on statistical regularities in training data. To resist AI generation, a language needs correctness to require deep, holistic understanding — local patterns alone are insufficient.

### Context-Dependent Syntax

Instead of fixed keywords, the language adapts syntax based on the module's declared domain. AI cannot memorize syntax because it shifts per-context.

```prove
domain Finance
  // "balance" is now a keyword, arithmetic operators
  // follow financial rounding rules
  total as Balance = sum(ledger.entries)  // compiler enforces Decimal with financial Scale

domain Physics
  // "balance" is just an identifier again
  // operators now track units
  balance as Acceleration = force / mass   // type: Acceleration, not a keyword
```

### Implementation Explanation as Code

`explain` documents the chain of operations in the `from` block using controlled natural language. With `ensures` present, the compiler parses each row for operations (action verbs), connectors, and references to identifiers — then verifies them against called functions' contracts. Sugar words ("the", "applicable", etc.) are ignored, keeping explain readable as English while remaining machine-verifiable. AI can generate plausible-looking explanations, but they won't verify — operations must match real function behaviors, and references must be real identifiers.

```prove
transforms merge_sort(xs List<T>) Sorted<List<T>>
  terminates: halves are strictly smaller than xs
  explain
    split the list at the midpoint
    recursively sort the first half
    recursively sort the second half
    merge both sorted halves preserving order
from
    halves as Pair<List<T>> = split_at(xs, len(xs) / 2)
    left as Sorted<List<T>> = merge_sort(halves.first)
    right as Sorted<List<T>> = merge_sort(halves.second)
    merge(left, right)
```

### Intentional Ambiguity Resolution

Constructs that are deliberately ambiguous without understanding intent. The `intent` string is parsed by the compiler using a formal semantics model and must match the code's behavior.

```prove
// Does this filter IN or filter OUT? Depends on the declared intent.
intent: "keep only valid records"
result as List<Record> = filter(records, valid record)

intent: "remove corrupt entries"
result as List<Record> = filter(records, valid corrupt)
// Same filter() call, but the compiler checks that the intent
// matches the predicate's semantics (keep vs discard)
```

### Non-Local Coherence Requirements

The compiler enforces that an entire module tells a coherent "story." Functions unrelated to the narrative produce compile errors.

```prove
module UserAuth
  narrative: """
  Users authenticate with credentials, receive a session token,
  and the token is validated on each request. Tokens expire
  after the configured TTL.
  """

  inputs login(creds Credentials) Session!
  transforms validate(token Token) User
  outputs expire(session Session)
  // outputs send_email(...)   // compiler error: unrelated to narrative
```

Coherence across an entire module requires understanding the *purpose* of the system, not just local patterns.

### Adversarial Type Puzzles

Refinement types that encode constraints requiring genuine reasoning, not just pattern matching:

```prove
type BalancedTree<T> is
  Node(left BalancedTree<T>, right BalancedTree<T>)
  where abs(left.depth - right.depth) <= 1

transforms insert(tree BalancedTree<T>, val T) BalancedTree<T>
  // Can't just pattern match — you need to construct a value
  // that satisfies the depth constraint, which requires
  // understanding rotation logic
```

### Semantic Commit Messages as Compilation Input

The compiler diffs the previous version, reads the commit message, and verifies the change actually addresses the described bug.

```prove
commit "fix: off-by-one in pagination — last page was empty
       when total % page_size == 0"

// The compiler diffs the previous version, reads the commit message,
// and verifies the change actually addresses the described bug.
// Vague messages like "fix stuff" don't compile.
```

---

## Phase 2 — Advanced Generation Resistance

Phase 2 targets deeper failure modes in AI code generation: the inability to reason about alternatives, uncertainty, temporal ordering, and interconnected constraints.

### Counterfactual Annotations

Every non-trivial design choice must explain what would break under alternative approaches. AI cannot reason about paths not taken.

```prove
transforms evict(cache Cache:[Mutable]) Option<Entry>
  why_not: "FIFO would evict still-hot entries under burst traffic"
  why_not: "Random eviction has unbounded worst-case for repeated keys"
  chosen: "LRU because access recency correlates with reuse probability"
from
    // LRU implementation
```

The compiler verifies the `chosen` rationale is consistent with the implementation's actual behavior (e.g., it really does track recency). `why_not` clauses are checked for plausibility against the function's type signature and effects.

### Adversarial Near-Miss Examples

Require inputs that *almost* break the code but don't. This proves the programmer understands the exact boundary between correct and incorrect behavior.

```prove
validates leap_year(y Year)
  near_miss: 1900  => false
  near_miss: 2000  => true
  near_miss: 2100  => false
from
    y % 4 == 0 && (y % 100 != 0 || y % 400 == 0)
```

The compiler verifies each near-miss actually exercises a distinct branch or boundary condition. Redundant near-misses are rejected. AI can memorize correct implementations but cannot identify the *diagnostic* inputs that prove understanding.

### Epistemic Annotations — `know` vs `assume` vs `believe`

Track the programmer's confidence level about invariants. The compiler treats each tier differently.

```prove
transforms process_order(order Order) Receipt
  know: len(order.items) > 0            // enforced by NonEmpty type — zero cost
  assume: order.total == sum(prices)    // validated at boundary, runtime check inserted
  believe: order.user.is_verified       // generates aggressive property tests to falsify
from
    // implementation
```

- **`know`** — Proven by the type system. Zero runtime cost. Compiler error if not actually provable.
- **`assume`** — Compiler inserts runtime validation at system boundaries. Logged when violated.
- **`believe`** — Compiler generates adversarial test cases specifically targeting this claim.

AI has no model of its own uncertainty — it would either mark everything `know` (fails verification) or `assume` (wasteful and reveals lack of understanding).

### Temporal Effect Ordering

Not just *what* effects a function has, but the *required order* — enforced across function boundaries and call graphs.

```prove
module Auth
  temporal: authenticate -> authorize -> access

  inputs authenticate(creds Credentials) Token!
  transforms authorize(token Token, resource Resource) Permission
  inputs access(perm Permission, resource Resource) Data!

// Compiler error: access() called before authorize()
inputs bad_handler(req Request) Response!
from
    token as Token = authenticate(req.creds)!
    data as Data = access(token, req.resource)!    // ERROR: skipped authorize
```

The compiler builds a call graph and verifies temporal constraints are satisfied across all execution paths. AI generates plausible call sequences but does not reason about protocol ordering.

### Invariant Networks

Instead of isolated `ensures` clauses, define networks of mutually-dependent invariants. Changing one cascades verification across the entire network.

```prove
invariant_network AccountingRules
  total_assets == total_liabilities + equity
  revenue - expenses == net_income
  net_income flows_to equity
  every(transaction) preserves total_assets == total_liabilities + equity

transforms post_transaction(ledger Ledger, tx Transaction) Ledger
  satisfies AccountingRules
from
    // implementation
```

No function can be written in isolation — the compiler checks that the entire network remains consistent after every change. This is the ultimate non-local reasoning requirement. Requires a constraint solver that scales across modules.

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

The programmer must provide a counterexample or logical argument. The compiler verifies the refutation is valid. This ensures the programmer understands not just *what* works, but *why alternatives don't*.

---

## Phase 3 — Anti-Training

Phase 1 and 2 make it hard for AI to *generate* correct Prove code. Phase 3 goes further: making Prove source code **resistant to being useful as AI training data**. Even if scraped, Prove codebases should yield minimal learnable signal.

AI training pipelines assume: (1) source code is plain text, (2) syntax is consistent across projects, (3) individual files are self-contained enough to learn from, and (4) surface patterns correlate with semantics. Prove attacks all four assumptions.

### Project-Specific Grammars

Each project can define syntactic extensions via its `prove.toml` manifest. Two Prove projects may look completely different at the surface level. Training data cannot generalize across projects.

```prove
// prove.toml
[syntax]
pipe_operator = "|>"
match_arrow = "=>"

// Another project's prove.toml
[syntax]
pipe_operator = ">>"
match_arrow = "->"
```

```prove
// Project A
result as List<Data> = data |> filter(valid record) |> map(transform)

// Project B — same semantics, different surface
result as List<Data> = data >> filter(valid record) >> map(transform)
```

The compiler normalizes all syntax variants to the same AST. Scrapers see inconsistent syntax; the compiler sees identical programs. This destroys the statistical regularities that AI training depends on.

### Structured Source Format (`.prv` is not plain text)

`.prv` files are stored as a compact binary AST, not human-readable text. The `prove` CLI provides views:

```
$ prove view src/server.prv              # pretty-print to terminal
$ prove view src/server.prv --raw        # show the binary structure
$ prove edit src/server.prv              # open in editor with LSP decoding
$ prove export src/server.prv --text     # one-time text export
```

The editor experience is seamless — the language server decodes `.prv` on the fly, and the formatter writes binary back. But web scrapers, GitHub raw views, and training pipelines see binary blobs, not parseable source code.

**Why this works:** Every major AI training pipeline (The Stack, StarCoder, etc.) filters for text files and parses by file extension. Binary files are discarded. Prove code is invisible to these pipelines by default.

The `prove export --text` command exists for code review, diffs, and human sharing — but text is a *view*, not the source of truth.

### Semantic Normalization (Surface Patterns Destroyed)

The compiler canonicalizes all code before storage. Variable names, ordering of declarations, whitespace, and stylistic choices are normalized away. What the programmer writes is not what is stored.

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

// What you see (reconstructed with your naming via the LSP):
transforms calculate_total_price(items List<Item>, tax TaxRate) Price
from
    subtotal as Decimal = sum(prices(items))
    subtotal * (1 + tax.rate)
```

A **name map** is stored alongside the canonical AST. The LSP reconstructs human-readable code on demand. But the stored form strips all semantic signal from identifiers — AI cannot learn naming conventions, domain patterns, or stylistic habits from Prove source.

### Fragmented Source (No File Is Self-Contained)

A function's complete definition is distributed across multiple sections that only make sense together:

```
src/
  server.prv          # implementation (canonical binary AST)
  server.explain      # implementation explanations for server.prv
  server.intent       # intent declarations
  server.near_miss    # adversarial near-miss examples
  server.narrative    # module narrative
```

A scraper that grabs `server.prv` alone gets a canonical binary AST with no variable names, no comments, no documentation, and no explanations. The explain file without the implementation is meaningless. The intent file without both is noise.

**All five files are required to compile.** The compiler assembles the complete picture. No single artifact is useful in isolation.

### Identity-Bound Compilation

Source files carry a cryptographic signature chain. The compiler verifies authorship.

```prove
// Embedded in .prv binary header
[signature]
author = "alice@example.com"
key_fingerprint = "A1B2C3..."
signed_at = 2026-02-27T14:30:00Z
chain = ["alice@example.com", "bob@example.com"]  // co-authors
```

- Unsigned code triggers a compiler warning (or error in strict mode).
- The signature chain tracks who wrote and reviewed each function.
- Scraped code with stripped signatures won't compile.
- The compiler can optionally refuse to build code signed by unknown keys.

This isn't DRM — it's **provenance**. The programmer can always export and re-sign. But mass scraping destroys the signature chain, making the code uncompilable.

### Anti-Training License as Default

Every `prove new` project is initialized with the **Prove Source License v1.0** (see `LICENSE`). It is a permissive MIT-style license with comprehensive AI restrictions covering:

- **Training, fine-tuning, and distillation** (Section 3.1)
- **Dataset inclusion, vector stores, RAG indices, and embedding databases** (Section 3.2)
- **Synthetic data generation** from the Software (Section 3.3)
- **Sublicensing for AI use** — third parties cannot be granted AI rights (Section 3.4)
- **Downstream propagation** — all redistributors must carry the restrictions forward (Section 3.5)
- **Technical protection circumvention** — bypassing binary format, normalization, or signatures for AI training is a breach (Section 4)

The license explicitly permits using AI tools *to write* Prove code and building AI-powered applications *with* Prove — it only prohibits using Prove source *as training data*.

Design draws from: NON-AI-MIT (base structure), Common Paper (precise LLM language), Authors Guild (sublicensing prohibition), Open RAIL-S (downstream propagation). Should be reviewed by legal counsel before production use.

This is not just a legal barrier — combined with the binary format and semantic normalization, it creates a layered defense: the code is hard to scrape, useless if scraped, and illegal to train on.

---

## The Fundamental Tension

Every feature that makes code harder for AI also makes it harder for humans.

The AI-resistance features force the programmer to:

- **Explain their reasoning** (proofs, intents, narratives, counterfactuals)
- **Maintain global coherence** (not just local correctness)
- **Understand *why*, not just *what*** (near-misses, refutation challenges)
- **Acknowledge uncertainty** (epistemic annotations)
- **Respect temporal protocols** (effect ordering)

The uncomfortable truth is that the things AI is bad at are the things lazy humans skip too. A language that resists AI would also resist copy-paste programming, cargo-culting Stack Overflow, and coding without understanding.

The anti-training features (binary format, semantic normalization, fragmented source) add friction to sharing and collaboration. The mitigation is a first-class toolchain: the `prove` CLI and LSP make the experience seamless for developers working inside the ecosystem, while making the code opaque to anything outside it.

**The design answers both questions:** Prove resists AI *writing* the code (Phase 1 + 2) and resists AI *training on* the code (Phase 3).
