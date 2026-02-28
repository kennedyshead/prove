# Philosophy & Design Decisions

> **A programming language that fights back against AI slop and code scraping.**

Prove is a strongly typed, compiler-driven language where contracts generate tests, intent verbs enforce purity, and the compiler rejects code that can't demonstrate understanding. Source is stored as binary AST — unscrapable, unnormalizable, unlicensed for training. If it compiles, the author understood what they wrote. If it's AI-generated, it won't.

## Philosophy

The compiler is your co-author, not your gatekeeper.

Every feature exists to move correctness checks from runtime to compile time, and to generate tests from the code you already write. Most bugs are type errors in disguise — give the type system enough power and they become almost impossible.

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

As close to the CPU as possible. The compiler does the heavy lifting at compile time so the output is fast and memory-efficient. Target: native code via direct assembly emission (x86_64 + ARM64). No VM, no interpreter for production output.

### First POC: RESTful Server

The first program written in Prove will be a RESTful HTTP server. This exercises the type system (request/response types, route matching), verb system (inputs/outputs), error handling, and IO — proving the language works for real-world backend development.

### AI-Resistance: Fundamental

AI-resistance features (proof obligations, intent declarations, narrative coherence, context-dependent syntax, semantic commits) are **mandatory and fundamental to the language identity**, not optional extras. Proof obligations are required for every function that has `ensures` clauses — if you declare what a function guarantees, you must prove why.

### Comptime: IO Allowed

Compile-time computation (`comptime`) allows IO operations. This enables reading config files, schema definitions, and static assets at compile time. Files accessed during comptime become build dependencies — changing them triggers recompilation. This may be revisited if reproducibility concerns arise.

### CLI-First Toolchain: `prove`

The `prove` CLI is the central interface for all development:

```
prove build          # compile the project
prove test           # run auto-generated + manual tests
prove check          # type-check without building
prove format         # auto-format source code
prove lsp            # start the language server
prove build --mutate # run mutation testing
prove new <name>     # scaffold a new project
```

### Syntax Philosophy

No shorthands. No abbreviations. Full words everywhere. The language reads like English prose where possible. Since it is inherently a hard-to-learn language (refinement types, proof obligations, effect tracking), **simplicity is maximized wherever possible**. If something can be simple, it must be. The compiler works for the programmer, not the other way around.

### Secondary Priorities (Deferred)

- **C FFI** — important but not day-one. Will be addressed after the core language is stable.
- **Calling Prove from other languages** — deferred until the FFI story is established.
- **Method syntax** — deferred. All function calls use `function(args)` form. No `object.method()` dot-call syntax. Keeps the language simple and avoids dispatch complexity. Field access (`user.name`) is unaffected.
