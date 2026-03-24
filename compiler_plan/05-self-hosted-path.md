# Phase 5: Self-hosted Path

## Goal

Define how the unified grammar enables the self-hosted compiler (v2.0).
This phase is planning only — implementation is post-v1 as described in
`future/in_progress/07-self-hosted-compiler.md`.

## How Phases 1-4 Enable Self-hosting

### Before this plan

The self-hosted compiler would need to:
1. Rewrite the lexer in Prove (~700 lines of token rules)
2. Rewrite the parser in Prove (~2,900 lines of recursive descent)
3. Somehow keep both parsers in sync forever

### After this plan

The self-hosted compiler:
1. Calls `Parse.tree(source)` — which uses tree-sitter (C library, fast)
2. Traverses the `Tree`/`Node` types from the `Prove` stdlib module
3. Builds its own IR from the tree-sitter nodes

**No parser rewrite needed.** The grammar lives in tree-sitter-prove
(maintained once), and both the Python bootstrap and the self-hosted compiler
consume it through the same C library.

## Self-hosted Compiler Architecture

```
.prv source
    │
    ▼  Parse.tree() — tree-sitter via Prove stdlib
Tree / Node (opaque binary types)
    │
    ▼  Prove code: CST → IR conversion
Compiler IR
    │
    ▼  Prove code: type checking, optimization
Checked IR
    │
    ▼  Prove code: C emission (or direct machine code)
Output
```

### Parser Layer

Zero lines of parsing code in the self-hosted compiler. `Parse.tree()` does
all the work. The compiler only needs to traverse the tree:

```
from Parse use tree
from Prove use root, kind, children, child, string, line

transforms parse_module(source String) CompilerModule!
    from
        t = tree(source)!
        r = root(t)
        // walk CST nodes, build compiler IR
```

### IR Layer

The compiler's internal representation follows a **two-stage strategy:**

**Stage 1: Start with opaque binary types** (no Phase 3 dependency)

```
type IRNode is binary
type IRTree is binary

reads ir_kind(node IRNode) String
reads ir_children(node IRNode) List<IRNode>
// ... accessor functions like the Prove stdlib module
```

Less ergonomic — no pattern matching on IR node kinds, string-based dispatch
instead — but lets self-hosted work begin immediately without waiting for
Phase 3 to be battle-tested.

**Stage 2: Migrate to recursive variant types** (after Phase 3 is stable)

```
type CExpr is
    CLiteral(value String, c_type String)
  | CBinary(op String, left CExpr, right CExpr)
  | CCall(name String, args List<CExpr>)
  | CField(object CExpr, field String)
```

Ergonomic, natural pattern matching, compile-time exhaustiveness checks. This
is the target representation. Migration from Stage 1 is mechanical: replace
string dispatch with match arms, replace accessor calls with field bindings.

Mutual recursion (Phase 3) is particularly valuable here — the compiler IR
naturally has mutually recursive node types (statements reference expressions
which reference statements).

### Checker Layer

**Stage 1** (binary types) — string-based dispatch:

```
validates type_check(node IRNode, env TypeEnv) Boolean
    from
        match ir_kind(node)
            "literal" => validate_literal(node, env)
            "binary" => check_binary(node, env)
            "call" => check_call(node, env)
```

**Stage 2** (recursive variants) — pattern matching:

```
validates type_check(expr CExpr, env TypeEnv) Boolean
    from
        match expr
            CLiteral(value, c_type) => validate_literal(value, c_type, env)
            CBinary(op, left, right) => check_binary(op, left, right, env)
            CCall(name, args) => check_call(name, args, env)
```

The migration from Stage 1 to Stage 2 is a refactor, not a rewrite — the
logic stays the same, only the dispatch mechanism changes.

### Bootstrap Path

1. Python compiler (with tree-sitter backend from Phase 2) compiles the
   self-hosted compiler's `.prv` source
2. Self-hosted compiler binary is produced
3. Self-hosted compiler compiles itself (bootstrap verification)
4. Both outputs must be identical (bit-for-bit or semantically equivalent)

The tree-sitter grammar is the invariant — same grammar, same parse trees,
regardless of which compiler does the type checking and code generation.

## What This Plan Does NOT Cover

- Full self-hosted compiler implementation (see `future/in_progress/07`)
- Timeline or release target
- IR migration timeline from binary types to recursive variants
- Whether to emit C or go directly to machine code

This document only establishes that **the unified grammar plan (Phases 1-4)
eliminates the parser from the self-hosted compiler's scope**, reducing the
v2.0 effort significantly.

## Dependency Summary

```
Phase 1 (grammar unification)
    ├──▶ Phase 2 (Python tree-sitter) ──┐
    │                                    ├──▶ Phase 5 Stage 1 (binary IR)
    └──▶ Phase 4 (Prove stdlib module) ──┘
                                              │
Phase 3 (recursive variants) ────────────────▶├──▶ Phase 5 Stage 2 (variant IR)
```

Phase 3 is required for Stage 2 (recursive variant IR) but not for Stage 1
(binary types). Self-hosted work begins with Stage 1, migrates to Stage 2
once Phase 3 is stable.
