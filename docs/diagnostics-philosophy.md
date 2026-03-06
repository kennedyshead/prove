---
title: Diagnostic Philosophy - Prove Programming Language
description: Learn about Prove's diagnostic philosophy emphasizing human-readable error messages, natural English, and helpful suggestions.
keywords: Prove diagnostics, error messages, diagnostic philosophy, compiler UX
---

# Diagnostic Philosophy

## Why This Matters

Prove is designed to be read and understood by humans. Error messages are not afterthoughts — they are part of the language's user interface. Every diagnostic follows these rules.

---

## Rule 1: Natural English

Messages are complete sentences. They start with a capital letter, end with a period, and read like something a colleague would say.

```
Bad:  "undefined type 'Foo'"
Good: "Type 'Foo' is not defined."
```

---

## Rule 2: Show the Fix

Where possible, include a code suggestion or tell the user exactly what to do. Don't just say what's wrong — say how to fix it.

```
"Cannot use '!' in 'parse' because it is not declared as failable.
 Add '!' after the return type."
```

---

## Rule 3: One Error at a Time

When the parser encounters a catastrophic failure, report only the first error. Cascading errors from a single root cause are noise. Fix the first problem, re-compile, and the cascading errors disappear.

---

## Rule 4: Three Severity Tiers

| Tier | Meaning | Action |
|------|---------|--------|
| **Error** | Won't compile | Must be fixed by hand |
| **Warning** | Compiles but should be improved | Should be fixed by hand |
| **Info** | Compiles and `prove format` can fix it | Run `prove format` |

Strict mode (`--strict`) promotes warnings to errors. Info stays info.

---

## Rule 5: Every Code Has Documentation

Every diagnostic code links to `prove.botwork.se/diagnostics/#CODE` with a full explanation, before/after examples, and fix guidance. Codes are clickable in editors via LSP.

---

## Rule 6: Errors for Broken, Warnings for Improvable

If the code compiles and runs correctly, it is not an error. Errors are reserved for code that genuinely cannot be compiled. Style issues, missing documentation, and code quality improvements are warnings or info.

---

## Rule 7: Suggestions Are Concrete

The `Suggestion` system provides machine-applicable fixes. When a diagnostic includes a suggestion, the LSP can offer a one-click fix. Suggestions must be syntactically valid Prove code.
