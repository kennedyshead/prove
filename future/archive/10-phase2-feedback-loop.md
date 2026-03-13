# Phase 2 — Declaration ↔ Prove Feedback Loop

Prove is an intent-first language: every function declares a verb (its purpose),
contracts (its guarantees), and prose annotations (`explain`, `chosen`, `why_not`)
that document reasoning. This document describes how to generate **complete function
bodies** — not just signatures — from declared intent, using the standard library
and the project's own implemented code as the knowledge base.

**Context:** Phase 1 builds a verb-prose mapping module (`_nl_intent.py` — a pure
Python utility that maps English action words to Prove verb keywords), coherence
checks that verify prose matches code, a warm ML cache for the LSP completion model,
and basic stub generation that produces function signatures with empty `from` blocks
(Prove's function body keyword) marked with `todo`.

Phase 2 makes generation **deep**: function bodies are generated where possible,
complete with `explain` (step-by-step documentation of the `from` block), `chosen`
(which approach was selected and why), `why_not` (rejected alternatives anchored to
real names), and contracts. The system distinguishes **knowns** (things it can infer
and generate) from **unknowns** (things that need the programmer). As the programmer
fills in unknowns, they become knowns for future generation.

---

## Core Concept: Knowns vs Unknowns

A **known** is anything the generator can resolve to concrete code:

- Stdlib functions with matching verb+domain (e.g. "hashes" → `Hash.hash(...)`)
- Project functions already implemented (non-todo `from` blocks)
- Type constructors and their required fields
- Verb-implied contracts (`validates` → `ensures result == true or result == false`)
- Standard patterns per verb family (e.g. `transforms` typically pipes input through operations)

An **unknown** is anything that requires human judgment:

- Business logic not derivable from prose alone
- Choice between multiple valid approaches (until `chosen` is provided)
- Domain-specific validation rules
- External system integration details

### The Spectrum

Functions aren't binary known/unknown — they exist on a spectrum:

| Level | What's generated | What's left |
|---|---|---|
| **Full** | Complete body + explain + contracts | Nothing (programmer reviews) |
| **Partial** | Some statements + todo gaps | Programmer fills gaps |
| **Signature only** | Verb + name + params + return type | Entire from-block |
| **Comment only** | `// Possible: verb name(...)` | Everything |

The generator always produces the **maximum it can**. First-time generation against
a bare declaration with only stdlib knowledge will produce mostly signature-only and
partial stubs. As the programmer fills in code, re-running generation fills more.

---

## How Knowns Are Resolved

### Step 1: Verb + Noun → Stdlib Lookup

The declaration says: *"transforms plaintext passwords into hashes using bcrypt"*

`implied_verbs()` gives: `transforms`
`extract_nouns()` gives: `["passwords", "hashes", "bcrypt"]`

The generator searches stdlib for matching verb+noun combinations:

```python
def _find_stdlib_matches(verb: str, nouns: list[str]) -> list[StdlibMatch]:
    """Search stdlib modules for functions matching verb and domain nouns."""
    matches = []
    for module_name, module_sig in STDLIB_SIGNATURES.items():
        for fn in module_sig.functions:
            if fn.verb != verb:
                continue
            # Score by noun overlap between function name/docs and extracted nouns
            fn_words = set(fn.name.lower().split("_")) | _doc_words(fn.docstring)
            overlap = fn_words & set(nouns)
            if overlap:
                matches.append(StdlibMatch(
                    module=module_name, function=fn,
                    overlap=overlap, score=len(overlap) / len(nouns),
                ))
    return sorted(matches, key=lambda m: -m.score)
```

For "transforms passwords into hashes using bcrypt":
- `Hash.hash` matches: verb `transforms`, noun overlap `{"hash"}` — **known**
- The parameter type (`String`) and return type (`String`) come from the stdlib signature

### Step 2: Known Stdlib Match → Full Body Generation

When a stdlib function matches with high confidence, generate a complete body:

```prove
/// Transforms a plaintext password into a bcrypt hash
transforms password(plaintext String) String
  explain
    Applies bcrypt hashing to the plaintext input
  chosen: "Hash.hash for industry-standard cryptographic hashing"
  why_not: "manual byte manipulation because error-prone and insecure"
from
  Hash.hash(plaintext, "bcrypt")
```

Everything here was generated:
- **Doc comment**: from the declaration sentence that triggered this function
- **Signature**: verb from `implied_verbs`, name from `extract_nouns`, params/return from stdlib
- **Explain**: derived from the declaration prose + stdlib function docstring
- **Chosen**: the stdlib function that was selected + its documented purpose
- **Why_not**: generated from known alternatives in the same stdlib module that were *not*
  chosen (other `Hash` functions, or known-insecure alternatives)
- **From block**: direct call to the matched stdlib function with parameter threading

### Step 3: No Stdlib Match → Unknown (todo)

The declaration says: *"validates user credentials against a stored database"*

`implied_verbs()`: `validates`
`extract_nouns()`: `["credentials", "database"]`

No stdlib function matches "validates" + "credentials" — this is domain-specific
business logic. The generator produces:

```prove
/// Validates user credentials against a stored database
validates credentials(user String, password String) Boolean
from
  todo "validate user credentials against stored database"
```

The `todo` message preserves the original declaration intent so the programmer
knows what this function should do.

### Step 4: Partial Match → Mixed Body

The declaration says: *"reads configuration from a TOML file and validates its structure"*

This implies two operations. The first has a stdlib match (`System.file` for reading),
the second doesn't (structure validation is domain-specific):

```prove
/// Reads configuration from a TOML file and validates its structure
reads configuration(path String) Table!
  explain
    Reads the file contents from disk
    Validates the parsed structure against expected schema
from
  content as String = System.file(path)!
  config as Table = Parse.table(content)!
  todo "validate config structure against expected schema"
  config
```

The generator filled what it could (file reading, TOML parsing via stdlib) and left
a `todo` for the domain-specific validation step. The programmer only needs to
replace that one `todo` line.

---

## The Feedback Loop

### First Generation (cold — stdlib only)

```
Declaration ──→ implied_verbs + extract_nouns
                        │
                        ▼
              Stdlib lookup ──→ Full bodies (knowns)
                    │                    │
                    ▼                    ▼
              No match ──→ todo stubs (unknowns)
```

Result: some functions fully generated, most are stubs.

### Programmer Fills In Unknowns

The programmer implements `validates credentials(...)`:

```prove
validates credentials(user String, password String) Boolean
from
  stored_hash as String = read_password_hash(user)!
  computed as String = password(password)
  stored_hash == computed
```

### Second Generation (warm — stdlib + project)

Now the generator knows about `credentials`, `read_password_hash`, and `password`
as project-defined functions. If the declaration is extended:

*"...and validates admin access using credential verification and role checking"*

The generator can now produce:

```prove
/// Validates admin access using credential verification and role checking
validates admin_access(user String, password String, role String) Boolean
  explain
    Verifies base credentials using existing credential validation
    Checks the user's role against the required admin role
from
  valid as Boolean = credentials(user, password)
  match valid
    when true
      role == "admin"
    when false
      false
```

This was **impossible** in the first generation — `credentials` didn't exist yet.
Now it's a known, so the generator can call it.

### The Loop Continues

Each time the programmer fills in code and re-runs generation:
1. The newly implemented functions become knowns
2. The model's project-level ngrams update (via cache)
3. More stubs can be filled, more bodies can be completed
4. Eventually the module approaches 100% completeness

---

## Explain / Chosen / Why_not Generation

### Explain Generation

For fully generated functions (stdlib matches), `explain` entries map 1:1 to
statements in the `from` block:

```python
def _generate_explain(stmts: list[GeneratedStmt]) -> list[str]:
    """Generate explain entries from generated statements."""
    entries = []
    for stmt in stmts:
        if stmt.is_todo:
            continue  # don't explain what we don't know
        if stmt.stdlib_call:
            # Use the stdlib function's docstring as basis
            doc = stmt.stdlib_call.docstring
            entries.append(f"    {_simplify_doc(doc)}")
        elif stmt.project_call:
            # Use the project function's intent or doc_comment
            doc = stmt.project_call.intent or stmt.project_call.doc_comment
            entries.append(f"    {_simplify_doc(doc)}")
        else:
            # Variable binding or expression — describe the operation
            entries.append(f"    {_describe_operation(stmt)}")
    return entries
```

### Chosen Generation

When the generator picks a stdlib function over alternatives:

```python
def _generate_chosen(selected: StdlibMatch, alternatives: list[StdlibMatch]) -> str:
    """Generate chosen text explaining why this stdlib function was selected."""
    return (
        f"{selected.module}.{selected.function.name} "
        f"for {_summarize_match_reason(selected)}"
    )
```

### Why_not Generation

For each alternative that was *not* selected:

```python
def _generate_why_not(
    selected: StdlibMatch,
    alternatives: list[StdlibMatch],
) -> list[str]:
    """Generate why_not entries for rejected alternatives."""
    entries = []
    for alt in alternatives:
        if alt.function.name == selected.function.name:
            continue
        reason = _compare_functions(selected, alt)
        entries.append(
            f"{alt.module}.{alt.function.name} because {reason}"
        )
    return entries
```

This produces:
```prove
  chosen: "Hash.hash for cryptographic password hashing"
  why_not: "Hash.digest because returns raw bytes, not string"
  why_not: "Text.transform because not cryptographically secure"
```

The `why_not` entries are anchored to real function names (satisfying the future
W505 check — "why_not entry mentions no known function or type") and explain the
rejection reason.

### Progressive Enrichment

On first generation, `explain`/`chosen`/`why_not` are only generated for functions
with stdlib matches. As the programmer fills in unknowns and adds their own prose
annotations, the coherence checks (W501-W505, described in
[narrative-prose-analysis.md](narrative-prose-analysis.md)) ensure everything stays
aligned.

For programmer-written functions that lack `explain`/`chosen`/`why_not`:
- W323 warns about missing `explain` when `ensures` contracts are present (you
  declared what the function guarantees but didn't document how)
- W503 warns about `chosen` without `why_not` (you declared your approach but
  didn't document what you rejected)
- The LSP offers prose completions to help fill them in

Over time, the entire module converges to having complete prose annotations —
some generated, some human-written, all coherence-checked.

---

## Generation State Tracking

The generator needs to know what it has already generated vs what the programmer
wrote by hand, to avoid overwriting human work on re-generation.

### Approach: provenance comments

Generated code includes a provenance marker (invisible to the programmer in normal
editing, preserved by the formatter):

```prove
/// Transforms a plaintext password into a bcrypt hash
/// @generated from declaration line 4
transforms password(plaintext String) String
```

The `@generated` doc comment tag tells the generator:
- This function was auto-generated from declaration line 4
- On re-generation, it CAN be updated if the declaration changed
- If the programmer modifies the function (removes `@generated`), it becomes
  human-owned and the generator will never touch it

### Completeness metadata

`prove check --status` reads provenance markers to report:

```
Module Auth: 3/5 functions implemented
  - validates credentials    [complete, human]
  - reads password_hash      [complete, generated]
  - transforms password      [complete, generated]
  - creates session          [partial, 1 todo remaining]
  - validates admin_access   [todo, generated stub]
```

---

## The stdlib as the initial knowledge base

First-generation quality depends entirely on stdlib coverage. The richer the
stdlib, the more the generator can resolve.

Current stdlib modules and their generation utility:

| Module | Generation use |
|---|---|
| Character | Character classification, validation |
| Text | String manipulation, search, splitting |
| Table | Key-value operations, lookup |
| System | File I/O, process execution, environment |
| Parse | String→structured data conversion |
| Math | Numeric computation |
| Types | Type conversion, coercion |
| List | Collection operations, filtering, mapping |
| Path | File path manipulation |
| Pattern | Regex matching and extraction |
| Format | String formatting, numeric display |
| Error | Error construction and wrapping |
| Random | Random value generation |
| Time | Time/date operations |
| Bytes | Binary data manipulation |
| Hash | Cryptographic hashing, verification |
| Log | Logging and diagnostics |
| Network | HTTP, TCP, network I/O |

For a declaration mentioning "hashes passwords" → Hash module is the stdlib match.
For "parses JSON input" → Parse module. For "formats output as table" → Format + Table.

As the stdlib grows toward V1.0, the generator's first-pass coverage improves
automatically — no generator code changes needed, just more stdlib functions to
match against.

---

## Implementation Order

### 2a. Stdlib signature index

Build a queryable index of all stdlib function signatures, searchable by
verb + noun keywords + parameter types + return types. This is the lookup
table the generator queries.

Source: `stdlib_loader.py` already loads all signatures. The index adds
keyword search on top.

### 2b. Body generation engine

The core: given a verb, noun list, and stdlib matches, produce a list of
`GeneratedStmt` objects that form a valid `from` block.

Handles: direct stdlib calls, parameter threading (pipe output of one call
as input to the next), variable binding, match expressions for branching.

### 2c. Prose generation

Given generated statements, produce `explain`, `chosen`, `why_not` blocks.
Uses stdlib docstrings + declaration text as source material.

### 2d. Project symbol integration

After first generation + programmer fill-in: re-scan the project symbol table,
identify newly available functions, and use them as building blocks for
previously-unknown stubs.

### 2e. `prove generate --update` (re-generation)

Re-run generation respecting provenance markers. Update generated functions
if the declaration changed. Leave human-owned functions alone. Fill in
previously-unknown stubs that now have project-level matches.

### 2f. Completeness reporting

`prove check --status` reports per-module and per-function completeness,
distinguishing generated vs human-written vs todo.

---

## What Phase 2 does NOT do (deferred to Phase 3)

- **Project-level declaration** — a single document spanning multiple modules
- **Cross-module generation** — generating import relationships between modules
- **Declaration regeneration** — updating the declaration text when code changes
- **Contract inference** — predicting `ensures`/`requires` beyond verb defaults
- **Temporal ordering** — using `ModuleDecl.temporal` to sequence operations

---

## Documentation & AGENTS Updates

When Phase 2 is implemented:

- **`docs/roadmap.md`** — Move "Intent-Driven Body Generation" from Exploring to
  Proposed/Preview as the feature ships.
- **`docs/cli.md`** — Extend the `prove generate` command documentation to describe
  body generation: when a full body is produced vs. a `todo` stub, and how to trigger
  regeneration after filling unknowns.
- **`AGENTS.md`** — Document the generation loop: "The body generator resolves verb +
  noun against the stdlib knowledge base; matches produce full bodies with `explain`,
  `chosen`, `why_not`; unresolved functions produce `todo` stubs. Each filled stub
  expands the building block set for subsequent generation passes."
- Run `mkdocs build --strict` after updating docs.
