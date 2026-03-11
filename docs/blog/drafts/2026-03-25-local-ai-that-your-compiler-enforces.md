---
date: 2026-03-25
title: Local AI That Your Compiler Enforces
description: What if your AI assistant couldn't lie to you? Local models help you write intent — the compiler verifies it's true.
keywords: local AI, documentation, compiler enforcement, intent-first, contracts, explain block, LLM
categories:
  - programming-languages
  - ai
  - tooling
author: Magnus
---

# Local AI That Your Compiler Enforces

Most AI coding tools are conversational. You describe what you want, the AI generates something, you check if it looks right, you ship it. The AI has no idea if the output is correct. You have to know enough to evaluate it. If you don't, you accept plausible.

There's a different model. What if the AI's job wasn't to generate code, but to help you express what you intend — and then the compiler verified that the code actually does what you said?

That's the role local AI plays in a Prove workflow. It's a fundamentally different contract than "write code for me."

## The Problem With Documentation AI

The most common use of AI for documentation today is: give the AI some code, ask it to write a docstring. The output looks plausible. You accept it. It drifts from the implementation within weeks.

This is documentation AI as paint. It generates text that describes what the code *probably* does, based on pattern matching. It doesn't know if the description is accurate. It can't — it's a language model, not a verifier.

The result is docstrings that lie politely. "Validates the input and returns a transformed result" — but actually modifies global state and has a side effect nobody documented. Nobody's fault. The AI saw the function signature and generated something reasonable. Reasonable isn't correct.

## A Different Model

Prove's `explain` block isn't documentation. Under strict mode — when `ensures` or `requires` are present — the compiler maps each row of the explain block to a statement in the function body. The counts must match. The semantics must correspond. If they don't, the build fails.

```prove
transforms process_order(order Order) Receipt!
  requires order.items != []
  ensures result.total >= 0
  explain
      calculate the item subtotal
      apply any applicable discounts
      calculate tax on the discounted total
      return the receipt with final amount
from
    sub as Price = subtotal(order.items)
    discounted as Price = apply_discounts(order, sub)
    taxed as Price = apply_tax(order.region, discounted)
    receipt(order, taxed)
```

This is enforced documentation. The explain block is not a description of what the code does — it is a verifiable claim that the compiler will reject if false.

Here's the opportunity: the explain block is *natural language*. It's the right interface for AI assistance.

## Where Local AI Fits

A local model running against your codebase knows three things the cloud AI doesn't:

1. **Your library** — every function you've written, what it does, what it takes
2. **Your conventions** — how your project names things, what patterns repeat
3. **Your data** — it's not leaving your machine

The workflow looks like this. You know what a function needs to do. You write the signature and the contracts:

```prove
transforms process_order(order Order) Receipt!
  requires order.items != []
  ensures result.total >= 0
```

You don't know what to put in the explain block — or you do, but you want to check it against what's actually available in your library. The local AI reads your codebase, sees what functions exist that could handle each step, and suggests:

```
explain
    calculate the item subtotal         → subtotal(order.items)
    apply any applicable discounts      → apply_discounts(order, sub)
    calculate tax on the discounted total → apply_tax(order.region, discounted)
    return the receipt with final amount → receipt(order, taxed)
```

Each suggestion includes which function it maps to. You review the mapping. You write the `from` block. The compiler verifies that the explain rows correspond to the statements.

The AI didn't write the code. The AI didn't write the documentation. It mapped your intent onto your existing library and showed you what building blocks are available. You made the decisions. The compiler verified them.

## Why Local Matters Here

This only works if the AI actually knows your codebase. A cloud model doesn't — it has training data, and your private library isn't in it. Every session you re-explain your types, your conventions, your domain.

A local model runs against your repository. Every `///` doc comment you've written, every `ensures` and `requires` clause, every `explain` block — all of it is in the index. When you write a new function, the model doesn't just know the standard library. It knows *your* library.

This compounds. Every function you write with a proper explain block and contracts makes the local model better at suggesting the next function, because the vocabulary of your codebase grows. The more you've invested in making your functions legible to the compiler, the more legible they are to the model, and the better the suggestions become.

It's the opposite of the docstring AI dynamic, where the better the AI gets, the less you understand the code. Here the better the model gets at suggestions, the better you've documented your code — because the documentation is machine-verified.

## The Compiler as Ground Truth

The key distinction is where the authority sits.

In conventional AI-assisted development, the AI is authoritative — it generates, you accept. If it's wrong, you might notice. If it's subtly wrong, you probably won't.

In a Prove workflow, the compiler is authoritative. The AI helps you express intent. The compiler verifies that the code matches. You can't accept a wrong suggestion and ship it — the build will fail because the explain row doesn't correspond to a real statement, or the function the AI suggested doesn't exist, or the ensures clause doesn't hold.

The AI is a helper. The compiler is the enforcer.

This is a better division of responsibility than most AI tooling produces. The AI is fast at pattern matching and good at knowing what functions exist that could do what you want. The compiler is perfect at verifying that what you claimed you did is what the code actually does. Neither of those is a human job. The human job is: understand the problem, decide what the function should do, and review the mapping.

## What This Looks Like Over Time

Right now the explain block is primarily a verification tool. You write it, the compiler checks it. That's already useful.

But the natural evolution is a local AI that operates on the explain block as a query. You write:

```prove
transforms calculate_shipping_cost(order Order, zone Zone) Price
  explain
      look up the base rate for the zone
      add surcharges for heavy items
      apply any shipping discounts
      return the final shipping cost
```

The local model searches your codebase, finds `base_rate_for_zone`, `heavy_item_surcharge`, `apply_shipping_discount`, and suggests the `from` block. You review. You confirm. The compiler verifies.

You didn't write the implementation. But you wrote the intent in a form the compiler can check, and you reviewed every step the model suggested. You own the result. If it's wrong, you understand it well enough to fix it.

That's the bar: not "who wrote it" but "does anyone understand it."

---

Prove is an intent-first programming language. [The compiler source is on Gitea](https://code.botwork.se). The explain block is in the [contracts documentation](../contracts.md).
