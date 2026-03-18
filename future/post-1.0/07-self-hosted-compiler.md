# Post-1.0: Self-Hosted Compiler (V2.0)

## Source

`roadmap.md` — Exploring

## Description

Rewrite the compiler in Prove. The V1.0 Python bootstrap compiles it,
the resulting binary recompiles itself, and both outputs must match
(bootstrap verification).

## Prerequisites

- V1.0 fully stable (all language features, comprehensive stdlib)
- The `proof/` project (self-hosting target at `/workspace/proof/`) must be
  complete enough to express the compiler
- Prove must be able to express: AST manipulation, string processing,
  file IO, process spawning, error reporting

## Key decisions

- Bootstrap chain: Python → Prove binary → self-compiled binary
- Verification: bitwise identical output? or semantic equivalence?
- Which compiler passes to port first (lexer → parser → checker → emitter)
- How to handle the chicken-and-egg problem during development
- Performance target: self-hosted compiler must not be significantly slower

## Phases

1. **Lexer in Prove** — tokenization is self-contained
2. **Parser in Prove** — depends on AST types and token stream
3. **Checker in Prove** — largest and most complex pass
4. **Emitter in Prove** — string concatenation heavy, needs good String perf
5. **Optimizer in Prove** — AST transformations
6. **CLI in Prove** — ties it all together

## Scope

Very large. This is the entire V2.0 milestone. Planning deferred until
V1.0 is stable.
