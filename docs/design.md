# Design Decisions & Trade-offs

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

### First POC: Self-Hosting Compiler

The first program written in Prove will be the Prove compiler itself. The bootstrap path: (1) write a complete compiler in Python, (2) use it to compile a Prove compiler written in Prove. This exercises the type system (AST node types, token variants), verb system (transforms for pure passes, inputs for file reading, outputs for code emission), pattern matching (exhaustive over AST nodes), and algebraic types — proving the language works by compiling itself. Self-hosting is the strongest possible validation: if Prove can express its own compiler, it can express anything.

### AI-Resistance: Fundamental

AI-resistance features (implementation explanations, intent declarations, narrative coherence, context-dependent syntax, semantic commits) are **mandatory and fundamental to the language identity**, not optional extras. `requires` and `ensures` are hard rules the compiler enforces automatically. `explain` blocks document the chain of operations in the implementation — each key maps to a variable name, and the count must match the `from` block exactly.

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

No shorthands. No abbreviations. Full words everywhere. The language reads like English prose where possible. Since it is inherently a hard-to-learn language (refinement types, implementation explanations, effect tracking), **simplicity is maximized wherever possible**. If something can be simple, it must be. The compiler works for the programmer, not the other way around.

### Secondary Priorities (Deferred)

- **C FFI** — important but not day-one. Will be addressed after the core language is stable.
- **Calling Prove from other languages** — deferred until the FFI story is established.
- **Method syntax** — deferred. All function calls use `function(args)` form. No `object.method()` dot-call syntax. Keeps the language simple and avoids dispatch complexity. Field access (`user.name`) is unaffected.

---

## Concurrency — Structured, Typed, No Data Races

```prove
inputs fetch_all(urls List<Url>) List<Response>!
from
    par_map(urls, fetch)
```

The ownership system and effect types combine to eliminate data races at compile time.

---

## Error Handling — Errors Are Values

No exceptions. Every failure path is visible in the type signature. Uses `!` for error propagation. Panics exist only for violated `assume:` assertions at system boundaries — normal error handling is always through `Result` values.

```prove
main() Result<Unit, Error>!
from
    config as Config = read_config("app.yaml")!
    db as Database = connect(config.db_url)!
    serve(config.port, db)!
```

---

## Zero-Cost Abstractions

- Pure functions auto-memoized and inlined
- Region-based memory for short-lived allocations
- Reference counting only where ownership is shared (compiler-inserted)
- No GC pauses, predictable performance
- Native code output

---

## Pain Point Comparison

| Pain in existing languages | How Prove solves it |
|---|---|
| Tests are separate from code | Testing is part of the definition — `ensures`, `requires`, `near_miss` |
| "Works on my machine" | Verb system makes IO explicit (`inputs`/`outputs`) |
| Null/nil crashes | No null — use `Option<T>`, enforced by compiler |
| Race conditions | Ownership + verb system prevents data races |
| "I forgot an edge case" | Compiler generates edge cases from types |
| Slow test suites | Property tests run at compile time when provable |
| Runtime type errors | Refinement types catch invalid values at compile time |

---

## Trade-offs

An honest assessment of the costs:

1. **Compilation speed** — Proving properties is expensive. Incremental compilation and caching are essential. Expect Rust-like compile times, not Go-like.
2. **Learning curve** — Refinement types and effect types are unfamiliar to most developers. The compiler's suggestions help, but there's still a ramp-up.
3. **Ecosystem bootstrap** — A new language needs libraries. A C FFI and a story for wrapping existing libraries is a secondary priority, deferred until the core language is stable.
4. **Not every property is provable** — For complex invariants the compiler falls back to runtime property tests, which is still better than nothing but not a proof.

**The core bet:** Making the compiler do more work upfront saves orders of magnitude more time than writing and maintaining tests by hand.
