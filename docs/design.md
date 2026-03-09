---
title: Design Decisions - Prove Programming Language
description: Documentation of Prove's design decisions and trade-offs including intent-first philosophy, contracts, and compiler architecture.
keywords: Prove design, language design, intent-first, design decisions
---

# Design Decisions & Trade-offs

## Philosophy

Prove is an **intent-first** language. Every function declares its intent — a verb names the purpose, contracts state the guarantees, and explain documents the reasoning — before a single line of implementation is written. The compiler then enforces that the implementation matches the declared intent.

The compiler is your co-author, not your gatekeeper. Every feature exists to move correctness checks from runtime to compile time, and to generate tests from the code you already write. Most bugs are type errors in disguise — give the type system enough power and they become almost impossible.

---

## Implementation Decisions

### File Extension: `.prv`

Investigated `.pv`, `.prove`, `.prf`, `.pr`, and `.prv`. Chosen: **`.prv`** — short, reads naturally as "Prove", and has no conflicts with existing programming languages or developer tooling.

| Rejected | Reason |
|----------|--------|
| `.pv` | Taken by **ProVerif** (formal methods — same domain, high confusion risk) |
| `.prove` | Taken by **Perl's `prove`** test harness (well-known in dev tooling) |
| `.prf` | Taken by **MS Outlook** profiles and **Qt** feature files |
| `.pr` | Legacy Source Insight 3, but "PR" universally means "pull request" |

### Prototype Implementation: Python

The compiler POC is implemented in Python (>=3.11). The goal is to validate the language design and prove out the compilation pipeline before rewriting in a systems language.

### Compilation Target: Native Code

As close to the CPU as possible. The compiler does the heavy lifting at compile time so the output is fast and memory-efficient. Target: native code via C emission compiled by gcc/clang. An earlier ASM backend (x86_64) was prototyped at v0.2 and archived — C emission provides better portability and optimization. No VM, no interpreter for production output.

### First POC: Self-Hosting Compiler

The first program written in Prove will be the Prove compiler itself. The bootstrap path: (1) write a complete compiler in Python, (2) use it to compile a Prove compiler written in Prove. This exercises the type system (AST node types, token variants), verb system (transforms for pure passes, inputs for file reading, outputs for code emission), pattern matching (exhaustive over AST nodes), and algebraic types — proving the language works by compiling itself. Self-hosting is the strongest possible validation: if Prove can express its own compiler, it can express anything.

### AI-Resistance: Fundamental

AI-resistance features (implementation explanations, intent declarations, narrative coherence, context-dependent syntax, semantic commits) are **mandatory and fundamental to the language identity**, not optional extras. `requires` and `ensures` are hard rules the compiler enforces automatically. `explain` documents the chain of operations in the implementation using controlled natural language — with `ensures` present, references are verified against contracts and row count must match the `from` block.

### Comptime: IO Allowed

Compile-time computation (`comptime`) allows IO operations. This enables reading config files, schema definitions, and static assets at compile time. Files accessed during comptime become build dependencies — changing them triggers recompilation. This may be revisited if reproducibility concerns arise.

### CLI-First Toolchain: `prove`

The `prove` CLI is the central interface for all development:

```bash
prove build              # compile the project (mutation testing runs by default)
prove build --debug      # compile with debug symbols
prove build --no-mutate  # compile without mutation testing
prove test               # run auto-generated + manual tests
prove check              # type-check without building
prove format             # auto-format source code
prove format --status    # check formatting without modifying
prove lsp                # start the language server
prove new <name>         # scaffold a new project
```

### Syntax Philosophy

No shorthands. No abbreviations. Full words everywhere. The language reads like English prose where possible. Since it is inherently a hard-to-learn language (refinement types, implementation explanations, effect tracking), **simplicity is maximized wherever possible**. If something can be simple, it must be. The compiler works for the programmer, not the other way around.

### Secondary Priorities (Deferred)

- **C FFI** — important but not day-one. Will be addressed after the core language is stable.
- **Calling Prove from other languages** — deferred until the FFI story is established.
- **Method syntax** — deferred. All function calls use `function(args)` form. No `object.method()` dot-call syntax. Keeps the language simple and avoids dispatch complexity. Field access (`user.name`) is unaffected.

---

## Concurrency — Parallel Map and Effect Types

Prove provides `par_map` as a safe concurrency primitive. Because pure verbs (transforms, validates, reads, creates, matches) guarantee no shared mutable state, thread-based parallelism is safe by construction:

```prove
inputs fetch_all(urls List<Url>) List<Response>!
from
    par_map(urls, fetch)
```

The type system includes effect type scaffolding (`IO`, `Fail`, `Async`) for annotating functions with side effects. The verb system enforces purity boundaries. The async verb family (`detached`, `attached`, `listens`) provides structured concurrency backed by stackful coroutines (`prove_coro`). See the [Syntax Reference](syntax.md#async-verbs) for details.

---

## Error Handling — Errors Are Values

No exceptions. Every failure path is visible in the type signature. Uses `!` for error propagation. Panics exist only for violated `assume:` assertions at system boundaries — normal error handling is always through `Result` values.

```prove
main()!
from
    config as Config = read_config("app.yaml")!
    db as Database = connect(config.db_url)!
    serve(config.port, db)!
```

---

## Zero-Cost Abstractions

- Pure functions auto-memoized and inlined — *v0.9.5 ✓*
- Region-based memory runtime exists — *v0.9.5 ✓ (per-function scoping planned)*
- Basic use-after-move detection for `Own` modifier — *partial (comprehensive tracking planned)*
- No GC pauses, predictable performance
- Native code output

---

## Pain Point Comparison

| Pain in existing languages | How Prove solves it |
|---|---|
| Tests are separate from code | Testing is part of the definition — `ensures`, `requires`, `near_miss` |
| "Works on my machine" | Verb system makes IO explicit (`inputs`/`outputs`) |
| Null/nil crashes | No null — use `Option<Value>`, enforced by compiler |
| Race conditions | Ownership + verb purity guarantee safe `par_map`; structured concurrency planned |
| "I forgot an edge case" | Compiler generates edge cases from types |
| Slow test suites | Property tests generated from contracts |
| Runtime type errors | Refinement types catch invalid values at compile time |

---

## Trade-offs

An honest assessment of the costs:

1. **Compilation speed** — Proving properties is expensive. Incremental compilation and caching are essential. Expect Rust-like compile times, not Go-like.
2. **Learning curve** — Refinement types and effect types are unfamiliar to most developers. The compiler's suggestions help, but there's still a ramp-up.
3. **Ecosystem bootstrap** — A new language needs libraries. A C FFI and a story for wrapping existing libraries is a secondary priority, deferred until the core language is stable.
4. **Not every property is provable** — For complex invariants the compiler falls back to runtime property tests, which is still better than nothing but not a proof.

**The core bet:** Making the compiler do more work upfront saves orders of magnitude more time than writing and maintaining tests by hand.

---

## AI Transparency

Prove is built with honesty about where AI tools are and aren't used.

### What is human-authored

The Prove language itself — its syntax, semantics, type system, intent verbs, contract model, explain verification, AI-resistance mechanisms, refinement types, and every other novel design idea — is entirely human-invented. All `.prv` source code (including the planned self-hosted compiler) is written by humans.

### Where AI tools help

AI tools have been used as implementation aids for the surrounding tooling:

- **Bootstrap compiler** — the Python CLI, checker, emitter, and supporting infrastructure
- **C runtime** — the stdlib implementations backing binary functions
- **Documentation** — writing and maintaining these docs
- **Editor integration** — tree-sitter grammar, Pygments lexer, Chroma lexer

No single AI tool is credited. Multiple LLMs and open source models have been used throughout development as conceptual partners and coding assistants.

### After self-hosting

Once the compiler is self-hosted (V2.0, written in Prove and compiled by the V1.0 bootstrap), AI involvement will be limited to documentation maintenance and conceptual discussion. The self-hosted compiler will be human-authored Prove code.

### Licensing reflects this

The language and `.prv` source code are covered by the **Prove Source License v1.0**, which prohibits use as AI training data. The AI-assisted tooling (bootstrap compiler, docs, lexers) is licensed under **Apache-2.0**. This separation ensures legal clarity: the parts built with AI help use a license compatible with that workflow, while the human-authored language retains its protections.
