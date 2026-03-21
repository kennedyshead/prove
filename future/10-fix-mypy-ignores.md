# Fix mypy Disabled Error Codes

## Problem

`pyproject.toml` disables 10 mypy error codes globally. This masks real type errors across the entire codebase and makes strict mode meaningless for those categories.

Current suppressions:
```
union-attr, arg-type, list-item, attr-defined, type-arg,
no-untyped-def, no-any-return, import-untyped, import-not-found, no-redef
```

## Approach

Work through each disabled code one at a time:

1. **Remove one code from the global `disable_error_code` list**
2. **Run `mypy src/`** and triage every error:
   - Fix the type annotation if it's genuinely wrong
   - Add a surgical `# type: ignore[code]` with a comment if the code is intentionally dynamic
   - Add a `[[tool.mypy.overrides]]` per-module if a whole file is legitimately untyped
3. **Repeat** until the global list is empty

## Priority order

| Code | Likely effort | Notes |
|------|--------------|-------|
| `import-not-found` | Low | Install `.[dev,nlp]` in CI, or add stubs for optional deps |
| `import-untyped` | Low | Add `py.typed` markers or per-module overrides |
| `no-redef` | Low | Usually just needs variable renaming |
| `attr-defined` | Medium | Dynamic attrs on AST nodes — may need Protocol types |
| `union-attr` | Medium | Narrowing with `isinstance` or `assert` |
| `arg-type` | Medium | Often reveals real mismatches |
| `list-item` | Low | Usually just needs explicit type annotations |
| `type-arg` | Low | Missing generic parameters |
| `no-untyped-def` | High | Every untyped function needs annotations |
| `no-any-return` | Medium | Follows from fixing untyped defs |

## Goal

Zero global suppressions. Every remaining `type: ignore` should be inline with a reason comment.
