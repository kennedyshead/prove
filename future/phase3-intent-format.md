# Phase 3 — The `.intent` File Format

A human-readable, human-editable project declaration format that drives code
generation across the entire Prove project. The `.intent` file is the **source
of truth** for what the project does. The toolchain generates code from it,
and coherence checks verify the code stays aligned.

---

## Design Principles

### 1. Human-first

The file must read like a specification document. A non-programmer should be
able to understand the project's purpose by reading it. A programmer should be
able to edit it without consulting a format reference.

### 2. No visual noise

No braces, no brackets, no quotes around text, no semicolons, no commas in
lists. Indentation and natural English word order provide all the structure.
The only punctuation is colons (for labels) and arrows (for flow).

### 3. Every line is meaningful

No decorative lines, no section dividers, no optional boilerplate. Every line
either declares intent or provides structure. If a line can be removed without
losing information, it shouldn't be there.

### 4. Editable with confidence

The format should be hard to break accidentally. If you type a grammatically
sensible English sentence in the right place, it should be valid. The linter
catches semantic problems (verb not recognized, noun not in vocabulary) but
the format itself is forgiving.

### 5. Diffable

Each piece of intent occupies exactly one line. Adding a function intent to a
module is a one-line addition. Renaming a vocabulary term is a one-line change.
Git diffs are clean and reviewable.

---

## File Convention

- Filename: `project.intent` at the project root (next to `prove.toml`)
- One `.intent` file per project (it's a project-level document)
- Encoding: UTF-8, LF line endings
- Indentation: 2 spaces (matches Prove source convention)

---

## Format Specification

### Project Header

```
project UserAuth
  purpose: Authenticate users and manage their sessions
  domain: Security
```

- `project` — required, first line. Project name (PascalCase, matches `prove.toml`).
- `purpose` — one sentence. What the project does. Becomes the root narrative.
- `domain` — optional. Propagates to all module `domain:` fields unless overridden.

### Vocabulary

```
  vocabulary
    Credential is a user identity paired with a secret
    Session is a time-limited access token
    PasswordHash is a one-way derived value from a password
    Role is a named permission level
```

- Each line: `Name is description`
- Names become Prove types (PascalCase enforced by linter)
- Descriptions inform the generator about the type's purpose and structure
- No field definitions — those belong in the `.prv` code
- Vocabulary terms are the shared language between modules

**Why no field definitions here?** Because this is intent, not schema. The
programmer declares *what* a Credential is conceptually. The actual fields
(`username String`, `password_hash String`) are code-level decisions made
when implementing the type in `.prv`. The generator can suggest fields from
the description, but the `.intent` file doesn't prescribe them.

### Module Blocks

```
  module Auth
    validates credentials against stored password hashes
    reads password hashes from the credential store
    transforms plaintext passwords into password hashes
    creates sessions for authenticated users
```

- `module Name` — declares a Prove module. Generates `module Name` in `.prv`.
- Each indented line is a **verb phrase** — parseable because Prove verbs are
  a closed set. The verb is always the first word.
- The rest of the line is natural English describing the operation.
- Each verb phrase generates one function stub (Phase 1) or complete function
  (Phase 2).

**Parsing verb phrases:**

```
validates credentials against stored password hashes
^^^^^^^^^ ^^^^^^^^^^^  ^^^^^^^^^^^^^^^^^^^^^^^^^^^
verb      noun (name)  context (informs params/types)
```

The first word must be a Prove verb. The second word (or compound) becomes the
function name. Everything after is context that helps the generator predict
parameters, types, and the function body.

**Compound nouns:**

```
  reads password hashes from the credential store
```

Here "password hashes" is a two-word noun. The generator resolves it:
1. Check vocabulary: `PasswordHash` exists → function name is `password_hash`
2. "from the credential store" → parameter is likely `Credential` or `String` (path)

**IO and async verbs work the same way:**

```
  module Server
    listens for incoming connections on a port
    streams request data from connected clients
    outputs response data to connected clients
    detaches connection handler for each client
```

### Flow

```
  flow
    Auth creates sessions -> SessionManager validates sessions
    Auth validates credentials -> Auth reads password hashes
```

- Each line: `Module verb phrase -> Module verb phrase`
- Left side produces data, right side consumes it
- Generates: imports, parameter types, function call chains
- The arrow `->` means "the output of the left feeds into the right"

**Flow is optional.** If omitted, the generator infers relationships from
vocabulary overlap between modules. Explicit flow is clearer for complex
projects with non-obvious data paths.

**Multi-step flow:**

```
  flow
    Auth reads password hashes
      -> Auth transforms passwords
      -> Auth validates credentials
      -> Auth creates sessions
      -> SessionManager validates sessions
```

Indented continuation lines form a pipeline. This maps directly to `temporal:`
ordering in the generated module.

### Constraints

```
  constraints
    all credential operations are failable
    password hashing uses a cryptographic algorithm
    sessions have bounded lifetime
    no credential data appears in log output
```

- Natural English sentences expressing cross-cutting requirements
- Anchored to vocabulary terms (Credential, Session, etc.)
- The generator maps these to `ensures`/`requires` contracts and `failable` markers
- The linter verifies constraints are satisfied by the implementation

**Constraint keywords** (recognized by the parser for mapping to Prove features):

| Phrase pattern | Maps to |
|---|---|
| `... are failable` | `ReturnType!` on matching functions |
| `... uses ...` | `chosen:` annotation on generated functions |
| `... have bounded ...` | `ensures` contract with range check |
| `no ... appears in ...` | Negative `ensures` contract |
| `all ... must ...` | `requires` contract on matching functions |

These patterns are not exhaustive — the generator recognizes common English
phrasing and maps conservatively. Unrecognized constraints are preserved as
comments in the generated code for the programmer to implement manually.

---

## Complete Example

```
project Prism
  purpose: Transform and validate structured data between formats
  domain: DataProcessing

  vocabulary
    Schema is a structural definition of expected data fields
    Record is a single data entry conforming to a schema
    Mapping is a transformation rule from one schema to another
    ValidationResult is the outcome of checking a record against a schema

  module SchemaRegistry
    creates schemas from structural definitions
    validates schemas for internal consistency
    reads schemas from persistent storage
    outputs schemas to persistent storage

  module Transform
    transforms records from one schema to another using mappings
    creates mappings between compatible schemas
    validates mappings for completeness

  module Validate
    validates records against schemas
    creates validation results with detailed error reporting
    reads validation rules from schema constraints

  flow
    SchemaRegistry creates schemas
      -> Transform creates mappings
      -> Transform transforms records
      -> Validate validates records
      -> Validate creates validation results

  constraints
    all schema operations are failable
    transformation preserves all non-null fields
    validation results include field-level detail
    no data content appears in error messages
```

This is 37 lines. It describes a complete three-module project with types, data
flow, and constraints. From this, the toolchain generates:

- 3 module files with `narrative:` blocks derived from verb phrases
- 10 function stubs/bodies (Phase 1: stubs, Phase 2: bodies where resolvable)
- Type definitions for Schema, Record, Mapping, ValidationResult
- Import relationships from flow declarations
- Contract stubs from constraints
- `temporal:` ordering from flow pipelines

---

## Editing Workflow

### Adding a new function

The programmer adds one line:

```diff
  module Transform
    transforms records from one schema to another using mappings
    creates mappings between compatible schemas
    validates mappings for completeness
+   reads mappings from persistent storage
```

Running `prove generate --from-intent` adds a new function stub to the
Transform module. Existing functions are untouched.

### Adding a new module

```diff
+ module Export
+   transforms records into CSV format
+   transforms records into JSON format
+   outputs formatted data to files
```

Generates a new `.prv` file with three function stubs.

### Renaming a vocabulary term

```diff
  vocabulary
-   Record is a single data entry conforming to a schema
+   DataRow is a single data entry conforming to a schema
```

Running `prove generate --from-intent --update` renames the type across all
generated code (respecting provenance markers — human-written code is flagged
for manual review).

### Reviewing drift

```
$ prove check --intent
project.intent:14  Transform.transforms records — implementation matches
project.intent:15  Transform.creates mappings — implementation matches
project.intent:16  Transform.validates mappings — NOT IMPLEMENTED (todo)
project.intent:17  Transform.reads mappings — NO MATCHING FUNCTION
project.intent:31  constraint "no data content appears in error messages" — UNVERIFIED
```

The intent file becomes a living checklist. Lines that have matching, complete
implementations show as passing. Lines with todos show as incomplete. Lines with
no matching function at all show as missing.

---

## Parser Design

### Tokenization

The `.intent` format has a minimal token set:

- **Keywords**: `project`, `purpose`, `domain`, `vocabulary`, `module`, `flow`,
  `constraints`
- **Verbs**: the Prove verb set (closed, known at parse time)
- **Arrow**: `->`
- **Colon**: `:` (only after `purpose`, `domain`)
- **Indent**: 2-space increments (determines nesting)
- **Text**: everything else is free-form English text

### AST

```python
@dataclass
class IntentProject:
    name: str
    purpose: str
    domain: str | None
    vocabulary: list[VocabularyEntry]
    modules: list[IntentModule]
    flows: list[FlowDecl]
    constraints: list[ConstraintDecl]

@dataclass
class VocabularyEntry:
    name: str          # PascalCase type name
    description: str   # "is ..." text

@dataclass
class IntentModule:
    name: str
    intents: list[VerbPhrase]

@dataclass
class VerbPhrase:
    verb: str          # Prove verb keyword
    noun: str          # function name (derived)
    context: str       # rest of the phrase (informs generation)
    raw_line: str      # original text for error messages

@dataclass
class FlowDecl:
    steps: list[FlowStep]

@dataclass
class FlowStep:
    module: str
    verb_phrase: VerbPhrase

@dataclass
class ConstraintDecl:
    text: str
    anchors: list[str]   # vocabulary terms found in text
```

### Error Recovery

The parser is lenient. If a line in a module block doesn't start with a
recognized verb, it's flagged as a warning (not an error) and preserved as
a comment in generated code:

```
  module Auth
    validates credentials against stored password hashes
    handles session timeout gracefully
    ^^^^^^^ not a Prove verb — W601: unrecognized verb in intent
```

The programmer sees the warning in the editor and can fix it to a recognized
verb or leave it as documentation.

---

## Integration with Prove Toolchain

### CLI Commands

```
prove generate --from-intent          Generate/update .prv files from project.intent
prove check --intent                  Verify code matches intent declarations
prove intent --status                 Show completeness report
prove intent --drift                  Show only mismatches between intent and code
```

### LSP Integration — Dedicated `.intent` Language Support

The `.intent` file gets its own LSP mode, not a bolted-on extension of `.prv`
support. It registers for the `intent` language ID and provides:

#### Syntax Highlighting

- **Verb keywords** colored by family (pure verbs green, IO verbs blue, async verbs purple)
- **Vocabulary names** highlighted as types (PascalCase)
- **Module names** highlighted as namespaces
- **Section keywords** (`vocabulary`, `flow`, `constraints`) as keywords
- **Flow arrows** `->` as operators
- Tree-sitter grammar + Pygments/Chroma lexers for editor and renderer support

#### Completions — Powered by the Stdlib Knowledge Base

See [stdlib-knowledge-base.md](stdlib-knowledge-base.md) for how docstrings become
the training data that powers these completions.

**After indent in a module block** — suggest verb keywords ranked by domain:

```
  module Auth
    |
    ▼
    validates   (pure: check correctness)
    transforms  (pure: convert data)
    reads       (pure: extract information)
    creates     (pure: construct new values)
    inputs      (IO: read from external source)
    outputs     (IO: write to external destination)
```

A fresh project only has stdlib. As the project grows (Phase 2 feedback loop),
project-defined verbs and patterns rank higher.

**After a verb** — suggest nouns from the stdlib knowledge base:

```
  module Auth
    creates |
    ▼
    creates sha256      — Hash a byte array to SHA-256 digest         [Hash]
    creates sha512      — Hash a byte array to SHA-512 digest         [Hash]
    creates blake3      — Hash a byte array to BLAKE3 digest          [Hash]
    creates hmac        — Create an HMAC-SHA256 signature             [Hash]
    creates builder     — Create a new string builder                 [Text]
    creates byte        — Create a byte array from values             [Bytes]
```

Each suggestion shows the stdlib function's docstring and module. The programmer
sees what's available and can pick a stdlib capability or type their own noun.

**After a verb + partial noun** — filter by docstring keyword match:

```
  module Auth
    creates ... hash|
    ▼
    creates sha256      — Hash a byte array to SHA-256 digest         [Hash]
    creates sha512      — Hash a byte array to SHA-512 digest         [Hash]
    creates blake3      — Hash a byte array to BLAKE3 digest          [Hash]
    creates hmac        — Create an HMAC-SHA256 signature             [Hash]
```

The LSP queries `implied_functions("hash", docstring_index)` and filters to
matching entries. This is the stdlib knowledge base in action: the docstring
text "Hash a byte array to SHA-256 digest" matches the user's word "hash".

**In vocabulary section** — suggest existing stdlib type names:

```
  vocabulary
    |
    ▼
    ByteArray is ...    [Bytes]
    StringBuilder is ... [Text]
    Match is ...        [Pattern]
    ProcessResult is ... [System]
    DirEntry is ...     [System]
```

**In flow section** — suggest existing module + verb phrase combinations:

```
  flow
    Auth creates sessions -> |
    ▼
    SessionManager validates sessions
    SessionManager reads session data
    SessionManager creates session records
```

Only verb phrases already declared in the referenced module are suggested.

**In constraints section** — suggest recognized constraint patterns:

```
  constraints
    |
    ▼
    all ... operations are failable
    ... must use ...
    ... have bounded ...
    no ... appears in ...
```

#### Diagnostics

| Code | Severity | Condition |
|---|---|---|
| W601 | warning | Unrecognized verb (first word not in Prove verb set) |
| W602 | warning | Vocabulary term not used by any module |
| W603 | info | Verb phrase has high-confidence stdlib match (shown as hint) |
| E601 | error | Flow references non-existent module |
| E602 | error | Flow references verb phrase not declared in module |
| I601 | info | Module has corresponding `.prv` file — N/M functions implemented |

W603 is the key one for discovery. When the programmer writes:

```
  module Auth
    creates password hashes using cryptographic algorithm
```

The LSP shows an info hint:
```
I603: stdlib match — Hash.sha256 "Hash a byte array to SHA-256 digest" (score: 0.7)
```

This tells the programmer: "the stdlib can do this, and here's the specific
function." They don't need to know the stdlib by heart — the LSP tells them
what's available based on what they wrote in natural language.

#### Code Actions

- **"Generate .prv from this module"** — on a module block, generates the
  corresponding `.prv` file with stubs (Phase 1) or bodies (Phase 2)
- **"Generate all .prv files"** — runs full project generation from intent
- **"Mark as implemented"** — annotates an intent line when the programmer
  confirms the matching function is complete
- **"Add to vocabulary"** — when the LSP detects a capitalized word in a verb
  phrase that's not in vocabulary, offer to add it

### Coherence with Phase 1 and Phase 2

The `.intent` file is the **project-level** equivalent of `narrative:` at the
module level:

| Level | Source of intent | Validation |
|---|---|---|
| Project | `project.intent` | `prove check --intent` |
| Module | `narrative:` block | W501 (verb not in narrative) |
| Function | `explain` block | W502 (explain doesn't match body) |

`prove generate --from-intent` produces `.prv` files whose `narrative:` blocks
are derived from the intent file. This means the Phase 1 coherence checks
(W501-W505) automatically validate the generated code against the intent —
no additional checking infrastructure needed.

---

## What the `.intent` format is NOT

- **Not a programming language** — no types, no expressions, no control flow
- **Not a schema language** — vocabulary describes concepts, not field layouts
- **Not a test spec** — constraints inform contracts but aren't executable tests
- **Not generated** — it's human-written and human-maintained (the toolchain
  never modifies it without explicit `--update` flags)
- **Not required** — projects can use Prove without an `.intent` file. The
  file is an accelerator, not a prerequisite.

---

## Files Changed

| File | Change |
|---|---|
| `prove-py/src/prove/intent_parser.py` | **New** — `.intent` file parser |
| `prove-py/src/prove/intent_ast.py` | **New** — AST nodes for intent declarations |
| `prove-py/src/prove/intent_generator.py` | **New** — generate `.prv` from intent AST |
| `prove-py/src/prove/intent_checker.py` | **New** — verify code matches intent |
| `prove-py/src/prove/cli.py` | Add `prove generate --from-intent`, `prove check --intent`, `prove intent` |
| `prove-py/src/prove/lsp.py` | `.intent` file support: highlighting, completion, diagnostics |
| `prove-py/tests/test_intent_parser.py` | **New** — parser tests |
| `prove-py/tests/test_intent_generator.py` | **New** — generation tests |
| `prove-py/tests/test_intent_checker.py` | **New** — coherence tests |

### Companion projects

| Project | Change |
|---|---|
| `tree-sitter-prove` | Add `.intent` grammar |
| `pygments-prove` | Add `.intent` lexer |
| `chroma-lexer-prove` | Add `.intent` lexer |

---

## Relationship to Phases 1 and 2

**Phase 1** builds the verb-prose mapping (`_nl_intent.py`), coherence checks,
cache warmup, and stub generation from `narrative:` blocks.

**Phase 2** adds body generation from stdlib knowledge and the progressive
feedback loop where unknowns become knowns.

**Phase 3** adds the `.intent` file as the project-level entry point that
feeds into Phase 1 (stub generation) and Phase 2 (body generation). The
`.intent` file doesn't replace `narrative:` — it generates `narrative:` blocks.
The existing coherence checks then validate everything downstream.

```
project.intent                     (Phase 3: project-level intent)
      │
      ▼
module narrative: blocks           (Phase 1: module-level intent)
      │
      ├──▶ function stubs          (Phase 1: prove generate)
      │         │
      │         ▼
      ├──▶ function bodies         (Phase 2: stdlib + project knowns)
      │         │
      │         ▼
      └──▶ coherence checks        (Phase 1: W501-W505 verify alignment)
```

Each phase adds a layer. The `.intent` file is the top of the pyramid.
