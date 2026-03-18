# Post-1.0: Project-Specific Grammars

## Source

`ai-resistance.md` — Future Research (Post-1.0)

## Description

Each project can define syntactic extensions via `prove.toml`. Two Prove
projects may look completely different at the surface level, destroying the
statistical regularities that AI training depends on.

## Prerequisites

- Stable core grammar (V1.0)
- Extension mechanism design
- tree-sitter / Pygments / Chroma must support dynamic grammar loading

## Key decisions

- Extension scope: new keywords? new operators? new block syntax?
- Compilation: extensions desugar to core Prove? or extend the AST?
- Portability: can a project with extensions be read without the project's config?
- Editor support: LSP must load project-specific grammar rules
- Combinatorial complexity: how do extensions compose?

## Scope

Very large. This is essentially a macro/extension system. Requires careful
design to avoid Lisp-style fragmentation where every project is its own
language.

## Risk

High. May make the ecosystem harder to learn and collaborate in. The
anti-training benefit must be weighed against developer experience cost.
