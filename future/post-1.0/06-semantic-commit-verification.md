# Post-1.0: Semantic Commit Verification

## Source

`ai-resistance.md` — Proposed (Post-1.0)

## Description

The compiler diffs the previous version, reads the commit message, and
verifies the change actually addresses the described bug. Vague messages
like "fix stuff" don't compile.

```prove
commit "fix: off-by-one in pagination — last page was empty
       when total % page_size == 0"
```

## Prerequisites

- Robust AST diffing (function-level, not text-level)
- NLP for commit message analysis
- Git integration in the compiler

## Key decisions

- Verification depth: structural (change touches the right function?) or
  semantic (change actually fixes the described behavior)?
- False positive tolerance: how strict before it blocks developers?
- Integration point: pre-commit hook? `prove check`? `prove commit`?
- Commit message format: structured? free-form with extraction?

## Scope

Large. Requires NLP capabilities, AST diffing, and git integration.
Deferred due to inherent complexity of natural language understanding.

## Risk

Medium-high. Commit message verification that's too strict will be
disabled by every developer. The signal-to-noise ratio must be excellent.
