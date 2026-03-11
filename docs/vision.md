---
title: Vision - Prove Programming Language
description: Prove's vision for local, self-contained intent-driven development where the project's own declarations drive code generation.
keywords: Prove vision, intent-first, local generation, self-contained development
---

# Vision

Prove is an **intent-first** language. Today that means every function declares
its purpose before its implementation — a verb names the action, contracts state
the guarantees, and explain documents the reasoning. The compiler enforces that
the implementation matches.

The vision extends this principle to the entire development workflow.

---

## The Problem with Modern Code Generation

The current trajectory of software development ties programmers to external
AI services for code generation. Even with the latest "agentic" tools that
edit code directly, three fundamental problems remain:

1. **Dependency on third-party LLM providers.** Your development workflow
   relies on a company's API staying available, affordable, and uncensored.
   If the service changes terms, raises prices, or disappears, your
   toolchain breaks with it.

2. **Unsafe local execution.** Agentic tools run with broad access to your
   filesystem, shell, and network. Giving a model you don't control the
   ability to execute arbitrary commands on your machine is a security
   liability that no amount of sandboxing fully eliminates.

3. **Unpredictable and opaque output.** The model may confidently generate
   code that is subtly wrong, silently introduce dependencies, or outright
   fabricate APIs that don't exist. There is no declared intent, no
   verifiable contract, and no traceable origin for what ends up in your
   codebase. What is actually "under the hood" is unknowable.

Prove takes a different path.

---

## Local, Self-Contained Development

Prove's generation model is **local and deterministic**. It trains on your
own project code and the Prove standard library — nothing else. Nothing
ever leaves your environment unless you choose to send it.

No network calls. No external model. No training data from other people's
code. No black box.

---

## How It Works

### Declare intent in natural language

The programmer writes what the project should do, using Prove's existing
prose mechanisms:

- **Module `narrative:`** describes what a module is responsible for
- **Function `intent:`** describes why a function exists
- **`explain`** documents how each step satisfies the contract
- **`chosen:` / `why_not:`** records design decisions and rejected alternatives

These aren't comments. The compiler parses them, the coherence checker
([W501–W505](diagnostics.md)) verifies they match the code, and the LSP
suggests correct vocabulary as you write them.

### Generate structure from declared intent

Given a narrative like:

```prove
module Auth
  narrative: """
    This module validates user credentials against stored
    password hashes and creates session tokens for
    authenticated users.
  """
```

The toolchain can derive:

- The verbs in use: `validates`, `creates` (extracted from the prose)
- The domain nouns: `credentials`, `password`, `hashes`, `session`, `tokens`
- Function signatures that combine these verbs and nouns
- Parameter types predicted from the project's ML completion model

The result is function stubs — correct verb, predicted name, predicted types,
empty `from` block — that the programmer fills in.

### Fill in what the machine can't know

Generated stubs mark what needs human attention:

```prove
/// TODO: document credentials
validates credentials(user String, password String) Boolean
from
  todo
```

The `todo` keyword is a first-class incomplete marker. The linter tracks it:

```
Module Auth: 1/4 functions complete (25%)
  - validates credentials    [todo]
  - reads password_hash      [todo]
  - transforms password      [complete]
  - creates session          [todo]
```

As the programmer fills in functions, those become available as building blocks
for future generation. The project teaches itself.

### Verify alignment continuously

The coherence checker ensures that what the programmer declared matches what
they implemented. If the narrative says "validates credentials" but no
`validates` function exists, that's a warning. If an `explain` block describes
operations that don't match the `from` block, that's a warning. The declared
intent and the actual code stay in sync.

---

## What This Is Not

This is **not** a claim about faster development. Writing intent declarations
takes thought. Reviewing generated stubs takes attention. Filling in function
bodies requires domain knowledge. The total effort may be comparable to writing
code from scratch.

What changes is the **shape** of the work:

- The programmer starts by thinking about *what* before *how*
- Generated structure enforces consistency across the project
- The linter acts as a progress tracker, not just an error reporter
- Every piece of generated code has a traceable origin
- No external service has seen your code or influenced it

The goal is development that is **self-contained**: the project's own
declarations are sufficient to generate its structure, and the project's own
code is sufficient to verify its correctness. The programmer remains the
author — the toolchain is a deterministic assistant that works from what the
programmer has explicitly declared.

---

## Current Status

This vision is being built incrementally:

- **Implemented**: verb system, contracts, explain verification, ML completion
  model (global + per-project n-gram), coherence checking (I340)
- **Proposed**: prose coherence analysis (W501–W505), cache warm-start,
  stub generation from narrative
- **Exploring**: intent-driven body generation, project declaration format

See the [Roadmap](roadmap.md) for detailed status of each component.
