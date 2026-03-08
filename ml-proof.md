# ML-Proof: Machine Learning Features

## Overview

Machine learning features for Prove that operate outside the CLI — background services, topic detection, and user feedback learning. This is a proof-of-concept application built on top of the general-purpose Database stdlib (impl03).

The Database stdlib provides generic lookup table management (storage, versioning, diffs, merges). The ML system uses it as infrastructure and adds domain-specific logic: token co-occurrence weights, merge strategies for numeric data, and feedback learning.

## Prerequisites

- Database stdlib (impl03) — general lookup table storage, diffs, merges
- Binary lookup tables (impl02) — for fast compiled lookups
- Dynamic runtime (impl06) — for runtime modification

---

## Bootstrap Tool

Python tool to create initial database from code/text corpus. Extracts token chains and populates AST lookup tables.

### Location

`scripts/prove_ml_bootstrap.py`

### Usage

```bash
# JSONL: {"text": "parse int from string", "language": "prove"}
python scripts/prove_ml_bootstrap.py --jsonl data.jsonl --output ast/

# Markdown: extract text from code blocks and prose
python scripts/prove_ml_bootstrap.py --markdown docs/ --output ast/

# Prove source files (built-in)
python scripts/prove_ml_bootstrap.py --prv stdlib/ --output ast/
```

### Input Formats

#### JSONL

Line-separated JSON:
```json
{"text": "parse int from string", "language": "prove"}
{"text": "convert to string", "language": "en"}
```

#### Markdown

Extract from code blocks:
```markdown
# Example

Here is how to parse:

```prove
transforms parse_int(s String) Integer
```

The `parse_int` function converts strings to integers.
```
```

#### Prove Source

Parse `.prv` files directly:
- Extract function names
- Extract type names
- Extract usage patterns

### Token Extraction

```
Input: "parse int from string"
Tokenize: ["parse", "int", "from", "string"]
Chains:
    parse → int     (+1)
    int → from      (+1)
    from → string   (+1)
```

### Topic Splitting

Split into topic-specific AST files:

```
ast/
    math.prv       → edges for math operations
    strings.prv    → edges for string operations
    types.prv      → edges for type conversions
    io.prv         → edges for file/network operations
```

### Implementation Steps

1. Parse input files (JSONL/Markdown/Prove)
2. Tokenize text (split on whitespace + extract code identifiers)
3. Generate token chains
4. Cluster by topic (keyword analysis)
5. Output `.prv` files with lookup entries

---

## Topic Detection

Auto-detect new topics when training data grows beyond threshold.

```
- Analyze token distribution
- Detect new cluster (unsupervised)
- Create new AST file if cluster size > threshold
- Compile new binary automatically
```

**Implementation:**
```
Threshold: N tokens not matching existing topics
Action: Create new topic.prv + compile to binary.bin
```

---

## User Feedback Learning

Track which suggestions are accepted/rejected.

```
- LSP returns suggestions
- User picks one → +1 to edge
- User ignores → no change
- User types different → maybe -1 to edge
```

**Feedback Storage:**

Use the database stdlib to store feedback:

```prove
module UserFeedback
    // Store feedback using database module
    table FeedbackStore (suggestion String, accepted Boolean, context String)
end
```

**Integration:**

```
1. LSP shows suggestions
2. User selects → trigger feedback recording
3. Background: merge feedback into AST
4. Recompile binaries
```

---

## Background Training Loop

```
Forever loop for pre-emptive interaction.
- Monitor user code edits
- Extract token chains
- Update local AST
- Commit on interval or explicitly
```

---

## Token Co-occurrence

Track which tokens appear together:

```
Input: "parse int from string"
Tokenize: ["parse", "int", "from", "string"]
Chains:
    parse → int     (+1)
    int → from      (+1)
    from → string   (+1)
```

---

## Weight Merge Strategies

The Database stdlib provides generic conflict resolution via a user-written resolver
function (see `future/database-merge-conflicts.md`). The ML system implements its
own resolver specialized for numeric co-occurrence weights.

### The Problem

When the ML system updates edge weights, the underlying lookup table may have
been modified since it was loaded (by another process, or a previous feedback cycle):

```
Loaded:    parse → int: 1423   (version 5)
Computed:  parse → int: 1500   (ML wants to update)
Current:   parse → int: 1450   (version 6 — someone else saved)
```

### ML Conflict Resolver

The ML system provides a custom resolver to the Database `merges` function.
For weight values, it uses exponential moving average. For structural changes,
it rejects:

```prove
/// ML-specific resolver for co-occurrence weight conflicts.
transforms resolve_ml_conflict(conflict Conflict) Resolution
from
    match conflict
        // Numeric weight conflict — blend with EMA
        ValueConflict(_, _, local, remote) =>
            blended as Integer = ema(to_integer(local), to_integer(remote), 0.3)
            UseValue(to_value(blended))
        // Both sides added same edge — keep higher weight
        AdditionConflict(_, local, remote) =>
            match gt(sum_weights(local), sum_weights(remote))
                True => KeepLocal
                False => KeepRemote
        // Schema changes not supported by ML system
        SchemaConflict(_, _) => Reject("ML system cannot handle schema changes")

/// Exponential moving average for weight blending.
transforms ema(current Integer, incoming Integer, alpha Decimal) Integer
from
    round(to_decimal(current) * (1.0 - alpha) + to_decimal(incoming) * alpha)
```

### Usage with Database Stdlib

```prove
inputs update_weights(db Database, topic String, new_edges List<Edge>)!
from
    table as DatabaseTable = loads(db, topic)!
    new_table as DatabaseTable = apply_edges(table, new_edges)
    diff as TableDiff = diffs(table, new_table)!

    match saves(db, new_table)
        Ok(_) => ok()
        Err(StaleVersion(_, _)) =>
            // Stale — reload and do a three-way merge with our resolver
            fresh as DatabaseTable = loads(db, topic)!
            base_diff as TableDiff = diffs(table, fresh)!
            merged as MergeResult = merges(table, base_diff, diff, resolve_ml_conflict)!
            match merged
                Ok(merged_table) => saves(db, merged_table)!
                Err(msg) => fail("ML merge failed: " + msg)
```

### Alternative Strategies

The EMA resolver above is the default. Other strategies can be swapped in
by writing a different resolver function:

| Strategy | When to use | Resolver logic |
|----------|-------------|----------------|
| EMA (default) | Gradual learning from feedback | Blend weights with decay |
| Last-write-wins | Fast iteration, history unimportant | Always `KeepRemote` |
| Accumulate | Counting raw occurrences | `UseValue(local + remote)` |
| Max | Conservative, keep strongest signal | `UseValue(max(local, remote))` |

---

## Runtime Modification

Uses the Database stdlib (impl03) and dynamic lookup (impl06) for all storage
and modification. The ML system does not implement its own storage — it calls
Database functions and provides its own resolver for weight conflicts.

See `future/implementation/impl06-dynamic-lookup.md` for the full runtime
modification flow and `future/database-merge-conflicts.md` for the general
conflict resolution framework.

---

## Data Flow

```
User Code ──▶ Token Extraction ──▶ Edge weights
                     │                    │
                     ▼                    ▼
               [Background]        Database stdlib
                     │              loads / saves
                     ▼                    │
               ML Resolver ◄──── StaleVersion?
            (EMA weight merge)        │
                     │                ▼
                     └──────▶ saves(merged)
                                     │
                                     ▼
                              prove build
                                     │
                                     ▼
                                  Binary
                                     │
                                     ▼
                              Runtime queries
```

---

## CLI Integration

The ML system uses `prove compiler --load/--dump` (impl05) for converting
between AST and binary formats. See `future/implementation/impl05-compiler-cli.md`.

---

## Exit Criteria

- [ ] Bootstrap tool parses JSONL, Markdown, Prove source
- [ ] ML conflict resolver (EMA) implemented
- [ ] Weight merge via Database stdlib works end-to-end
- [ ] Topic detection threshold implemented
- [ ] User feedback tracking works
- [ ] Background training loop functional
- [ ] Tests pass
