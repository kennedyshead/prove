---
title: FAQ & Troubleshooting - Prove Programming Language
description: Frequently asked questions and common issues when working with Prove.
keywords: Prove FAQ, troubleshooting Prove, common Prove errors
---

# FAQ & Troubleshooting

## General

### Why does Prove exist?

Prove is designed for developers who want **intent-first programming** — where every function declares its purpose, guarantees, and reasoning before implementation. The compiler enforces that intent matches reality. This also makes Prove naturally resistant to AI-generated code because semantic correctness cannot be faked.

### How is Prove different from other languages?

- **No `if/else`** — use `match` for all branching
- **No `for/while` loops** — use `map`, `filter`, `reduce`
- **No `null`** — use `Option<Value>` instead
- **Verbs as declarations** — `transforms`, `validates`, `inputs`, etc.
- **Contracts are part of the language** — `requires`, `ensures`, `explain`
- **Refinement types** — types carry constraints, not just shapes

---

## Installation

### "Python version not supported"

Prove requires Python 3.11+. Check your version:

```bash
python --version
```

### "gcc/clang not found"

Install a C compiler:

```bash
# macOS
xcode-select --install

# Ubuntu/Debian
sudo apt install build-essential

# Windows (WSL recommended)
# Install via Visual Studio or WSL
```

---

## Compilation Errors

### "Unknown type 'X'"

Make sure you've imported the module. Check the [Stdlib Overview](stdlib/index.md) for which modules provide which types.

### "Pure function cannot call IO function"

You declared a `transforms`, `validates`, `reads`, `creates`, or `matches` function, but it's calling an `inputs` or `outputs` function. Either:
1. Change the verb to `inputs` or `outputs` if it truly needs IO
2. Pass the data as a parameter instead of reading it inside

### "Cannot find function 'X'"

Check:
1. The module is imported in your `module` block
2. The function name is spelled correctly (snake_case for functions)
3. You're using the correct verb at the call site

### "Non-exhaustive match"

Your `match` statement doesn't handle all variants of the algebraic type. Add missing arms or use `_` as a catch-all.

---

## Type Errors

### "Type 'X' is not compatible with 'Y'"

Common causes:
- Mismatched generic parameters: `List<Integer>` vs `List<String>`
- Refinement constraints not satisfied: `Port` expects 1-65535
- Missing `!` on failable function calls

### "Cannot infer type"

The compiler needs more context. Add explicit type annotations:
```prove
# Instead of:
result = compute()

# Use:
result as Integer = compute()
```

---

## Contracts

### "Contract 'ensures' violated"

The function returned a value that doesn't satisfy its `ensures` clause. Check:
1. The contract logic is correct
2. All code paths return values satisfying the contract

### "Function requires 'terminates' annotation"

Recursive functions must have `terminates` to prove they don't loop forever:
```prove
transforms factorial(n Integer) Integer
  terminates  # Prove termination
  requires n >= 0
from
    n == 0 => 1
    _ => n * factorial(n - 1)
```

---

## Runtime Errors

### "Division by zero"

Add a contract or use refinement types:
```prove
transforms safe_divide(a Decimal, b Decimal) Result<Decimal, String>
  requires b != 0  # Contract proves b is non-zero
from
    Ok(a / b)
```

### "Index out of bounds"

Use `Option` for safe access:
```prove
reads get(items List<Value>, index Integer) Option<Value>
from
    index >= 0 && index < len(items) => Some(items[index])
    _ => None
```

---

## Best Practices

### When to use `transforms` vs `reads`?

- `transforms` — conversion, computation, producing a new value
- `reads` — querying, extracting, no modification

### When to use `Result` vs `!`?

- `Result<Value, Error>` — for **expected failures** in pure functions
- `!` — for **IO failures** that should propagate to `main`

### How to structure a module?

```prove
module MyModule
  narrative: """What this module does."""
  OtherModule validates x transforms y  # Import what you need

  type MyType is
    VariantA
    | VariantB(Integer)

  CONSTANT as Integer = 42

  transforms public_function(x Integer) Integer
    from
        x + 1
```

---

## Getting Help

- Check the [Diagnostic Codes](diagnostics.md) for error/warning explanations
- Review the [Tutorial](tutorial.md) for step-by-step guidance
- See [Examples](examples/inventory_service.md) for full applications
