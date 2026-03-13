# Phase 1 — From Prose to Code (and Back)

The goal: a Prove project where the programmer writes a **declaration** (natural language
describing intent), and the toolchain generates most of the code structure automatically.
The linter highlights what's missing. The programmer fills gaps. Those filled gaps feed
back into the model for future generation.

Phase 1 builds the foundation. Phase 2 (future) adds the declaration parser and the
full generative loop.

---

## Current State (what exists today)

### AST Prose Infrastructure — Complete

Every prose field is parsed, stored, and formatted. The AST carries all the natural
language a programmer provides:

| Level | Field | Parsed | Analysed |
|---|---|---|---|
| Module | `narrative` | yes | I340 only (word overlap with function names) |
| Module | `domain` | yes | no |
| Module | `temporal` | yes | no |
| Function | `explain` | yes | W321, W323, W325 + C emission |
| Function | `intent` | yes | W311 (intent without ensures) |
| Function | `chosen` | yes | **no** — completely inert |
| Function | `why_not` | yes | **no** — completely inert |

The parser and AST are ready. The gap is analysis: most prose fields are write-only.

### Coherence Checking — Minimal

`Checker._check_coherence()` does one thing: I340 word-overlap between narrative
and function names. It runs only with `--coherence` CLI flag. The LSP never enables it.

The prover has three explain-related warnings (W321, W323, W325) but they check
structural presence, not semantic meaning.

**No verb-to-prose mapping exists anywhere.** There is no `_nl_intent.py`, no
`implied_verbs()`, no `_PROSE_STEMS` regex table.

### ML N-gram Model — Fully Implemented, Two Tiers

**Global model** (trained from stdlib + examples):
- `data/lsp-ml-store/bigrams/current.prv` — 73KB, ~1600 bigram rows
- `data/lsp-ml-store/completions/current.prv` — 155KB, trigram completions
- Loaded lazily from `.prv` text files by `_load_global_model()`
- Already knows patterns like: after a verb → likely function names; after `List<` → likely types

**Project indexer** (`_ProjectIndexer` in `lsp.py`):
- Indexes all `.prv` files under project root on first `did_open`
- Extracts per-symbol metadata: name, verb, kind, module, signature, docstring
- Writes `.prove_cache/` PDAT binary files — **but never reads them back**
- Incremental `patch_file()` on `did_save` — but **not on `did_change`**

**Completion pipeline** (`_ml_completions()` in `lsp.py`):
- Merges project + global model predictions
- Context-aware: verb keyword → functions; type trigger → types
- Auto-import edits for cross-module symbols

### Cache Persistence — Write-only

`read_pdat()` exists in `store_binary.py` and works. But the indexer never calls it.
Every LSP session re-parses all `.prv` files from scratch. CLI commands (`check`, `build`,
`format`) don't touch the cache at all.

---

## What Phase 1 Builds

Three deliverables, in dependency order:

### 1. `_nl_intent.py` — Verb-Prose Mapping

**Plan:** [narrative-prose-analysis.md](narrative-prose-analysis.md) Phase 1

The foundation for both directions (validation and generation). A pure Python module with:

- `_PROSE_STEMS` — regex table mapping English synonyms to Prove verbs
- `implied_verbs(text)` — extract verb set from prose text
- `body_tokens(fd)` — extract meaningful names from a function's `from` block
- `prose_overlaps(prose, tokens)` — check prose↔code overlap

This is the missing link. Without it:
- Coherence checks can't verify verb↔narrative alignment (W501)
- The generator can't map declaration prose to verbs
- LSP prose completions have no vocabulary to suggest

### 2. Coherence Checks + LSP Prose Mode

**Plan:** [narrative-prose-analysis.md](narrative-prose-analysis.md) Phases 2-4

Five new warnings powered by `_nl_intent.py`:

| Code | What it catches |
|---|---|
| W501 | Function verb not described in module narrative |
| W502 | Explain entry doesn't match from-body operations |
| W503 | Chosen declared without any why_not alternatives |
| W504 | Chosen text doesn't relate to function body |
| W505 | Why_not entry mentions no known function or type |

Plus LSP prose context detection and prose-mode completions — so the editor
actively helps write correct prose that maps to real verbs and real code.

These checks are the **code → prose** direction: making sure what you wrote
in prose actually matches what the code does.

### 3. Cache Warmup

**Plan:** [cache-indexing.md](cache-indexing.md)

Make the ML model instantly available:

- `manifest.json` with file mtimes for staleness detection
- `_ProjectIndexer.load()` reading PDAT back into memory (reader already exists)
- `_ensure_project_indexed` tries warm load before full reindex
- `did_change` patches indexer immediately (not just on save)
- CLI `check`/`build` update the cache as a side effect
- `prove index` command for explicit warmup

**Why this matters for generation:** stub generation needs the model warm. If the
user writes a declaration and asks for stubs, we can't re-parse every `.prv` file
first. The cache makes generation instant.

### 4. Stub Generation

**Plan:** [stub-generation.md](stub-generation.md)

The **prose → code** direction. Given a module's `narrative` (and optionally `domain`
and `temporal`), generate:

- Module skeleton with imports
- Function stubs with correct verbs, predicted names, predicted types
- Empty `from` blocks marked as incomplete
- Contract placeholders (`ensures`, `requires`) where the verb implies them

The linter then highlights everything that needs human attention.

---

## Dependency Graph

```
_nl_intent.py ──────────┬──> Coherence Checks (W501-W505)
(verb↔prose mapping)    │        (code → prose validation)
                        │
                        ├──> LSP Prose Completions
                        │        (editor suggests correct prose)
                        │
                        └──> Stub Generation
                                 (prose → code generation)
                                        │
Cache Warmup ───────────────────────────┘
(instant model access)        (needs warm model for type/name prediction)
```

`_nl_intent.py` is the foundation for everything. Cache warmup is independent but
required before stub generation is useful in practice.

### Cross-cutting: Stdlib Knowledge Base

See [stdlib-knowledge-base.md](stdlib-knowledge-base.md).

Today `ml_extract.py` **discards all `///` doc comments** during training. The model
learns token sequences but not their meaning. Stdlib docstrings like "Hash a byte
array to SHA-256 digest" are the natural language bridge between intent (what the
programmer writes in prose) and code (which stdlib function to call).

The stdlib knowledge base adds `implied_functions()` to `_nl_intent.py`: given prose
text, return concrete stdlib functions ranked by docstring overlap. This powers:

- Phase 1: richer verb mapping (not just "some creates" but "specifically Hash.sha256")
- Phase 2: body generation resolves to stdlib calls via docstring match
- Phase 3: `.intent` LSP suggests stdlib capabilities as you type verb phrases

---

## What This Enables (Phase 1 Complete State)

With all four pieces in place:

1. **Write narrative** → `narrative: """This module validates user credentials..."""`
2. **Get verb suggestions** → LSP suggests "validates", "checks", "verifies" inside the block
3. **Generate stubs** → `prove generate` creates `validates credential(...)` skeleton
4. **Fill in logic** → Programmer writes the `from` block
5. **Coherence check** → W501 flags if you add a `transforms` function that the narrative
   doesn't describe; W502 flags if your explain drifts from the body

The programmer's workflow becomes: **describe → generate → fill → verify**.

---

## Phase Roadmap

### Phase 2 — Declaration ↔ Prove Feedback Loop

See [phase2-feedback-loop.md](phase2-feedback-loop.md).

Phase 2 goes beyond stubs: it generates **complete function bodies** where possible,
using stdlib knowledge as the initial building block set. Functions the system can
resolve (verb + noun → stdlib match) get full bodies with `explain`, `chosen`,
`why_not`. Functions it can't resolve get `todo` stubs. As the programmer fills in
unknowns, those become knowns for re-generation — the loop tightens progressively.

### Phase 3 — The `.intent` File Format

See [phase3-intent-format.md](phase3-intent-format.md).

Phase 3 introduces `project.intent` — a human-readable, human-editable file format
for project-level intent declaration. Not markdown (too free), not TOML (too technical).
A dedicated format where every line maps to something generatable:

- **Vocabulary** defines domain concepts → becomes Prove types
- **Module blocks** list verb phrases → each line becomes a function
- **Flow** declares data paths between modules → drives imports and `temporal:`
- **Constraints** express cross-cutting requirements → maps to contracts

The `.intent` file sits at the top of the generation pyramid. It generates
`narrative:` blocks (which Phase 1 validates) and feeds into body generation
(which Phase 2 fills). `prove check --intent` verifies the whole chain.

Each phase depends on the previous being solid.
