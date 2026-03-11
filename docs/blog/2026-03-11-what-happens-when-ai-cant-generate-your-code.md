---
date: 2026-03-11
title: What Happens When AI Can't Generate Your Code
description: I gave an AI a real task in Prove. It failed six times. Here's exactly why — and why every failure is by design.
keywords: AI code generation, programming language design, intent-first, AI resistance, compiler, type system
categories:
  - programming-languages
  - design
  - ai
author: Magnus
---

# What Happens When AI Can't Generate Your Code

I ran an experiment last week. I took a real task — a small order validation function — and asked a capable AI assistant to write it in Prove.

It failed. Repeatedly. I fixed one error, gave it back the compiler output, and watched it generate new errors. Six rounds before anything close to correct came out, and even then it required manual fixes.

I wasn't frustrated. I was delighted. Because every failure revealed exactly the category of bug Prove was designed to prevent.

## The Task

Write a function that calculates an order total — apply a discount, apply tax, return the final price. Standard stuff. The kind of function that exists in thousands of codebases and is usually fine until the day it isn't.

Here's what the AI generated on the first attempt:

```python
# (AI output — not valid Prove, python actually)
function calculate_total(items, discount, tax):
    if len(items) == 0:
        raise ValueError("empty order")
    subtotal = sum(item.price for item in items)
    discounted = apply_discount(discount, subtotal)
    return apply_tax(tax, discounted)
```

The compiler's response was immediate: `E001: unknown keyword 'function'`.

## Failure 1: You Must Declare Your Intent

In Prove there is no `function`, no `def`, no `fn`. There are verbs:

```prove
transforms calculate_total(items List<OrderItem>, discount Discount, tax TaxRule) Price
```

The word `transforms` is not stylistic. It is a contract with the compiler. A `transforms` function is pure — it cannot perform IO, cannot fail, cannot modify state. If you try, the compiler rejects it at E361/E362/E363.

The AI used `function` because that's what it learned from millions of codebases. But `function` says nothing about intent. It's a keyword for the compiler's benefit, telling the parser what's coming. Prove already knows what's coming — it needs to know *why*.

When the AI switched to `transforms`, it immediately tried to add a network call inside the function body to log the total. The compiler rejected that too. A `transforms` that secretly does IO isn't a transformation — it's a lie. The verb system enforces that the claim in the signature matches the behavior in the body.

## Failure 2: There Is No If

I told the AI about the verb error and sent back the output. The next attempt was better. It got the verb right. Then it hit this:

```prove
# (AI output — not valid Prove)
transforms calculate_total(items List<OrderItem>, discount Discount, tax TaxRule) Price
from
    if len(items) == 0
        error("empty order")
    // ...
```

`E002: unknown keyword 'if'`

Prove has no `if`. No `else`. The only branching construct is `match`. The AI kept reaching for `if` because that's what defensive validation code looks like in every language it was trained on. In Prove, the equivalent is a `requires` clause:

```prove
transforms calculate_total(items List<OrderItem>, discount Discount, tax TaxRule) Price
  requires len(items) > 0
from
    sub as Price = subtotal(items)
    discounted as Price = apply_discount(discount, sub)
    apply_tax(tax, discounted)
```

This is not just syntactic. The `requires` clause is a *contract* — the compiler generates property tests that verify it holds across thousands of random inputs. An `if` guard is checked once, at that point in execution, by whoever remembers to call the function with valid data. A `requires` clause is checked by the compiler, automatically, forever.

The AI's instinct was to validate defensively inside the function. Prove's answer is: that's the caller's problem. Declare what you need, and the compiler enforces it at the boundary.

## Failure 3: The Explain Block Lies

By round four the AI was generating structurally correct Prove. Then it tried to add documentation:

```prove
transforms calculate_total(items List<OrderItem>, discount Discount, tax TaxRule) Price
  ensures result >= 0
  explain
      validate the items list
      calculate subtotal from items
      apply the discount to the total
      apply tax and return final price
from
    sub as Price = subtotal(items)
    discounted as Price = apply_discount(discount, sub)
    apply_tax(tax, discounted)
```

The compiler flagged it: the `explain` block has four rows but the `from` block has three statements. With `ensures` present, explain is in strict mode — each row must correspond to a top-level statement. The counts must match exactly.

The AI had written "validate the items list" as the first explain row, but there was no validation statement in the body. The `requires` clause handles validation — it's not a statement in `from`. The explain block described code that wasn't there.

This is the failure mode that kills real software: documentation that drifts from the implementation. A docstring can say anything. The `explain` block, under strict mode, cannot say something the code doesn't do. Every row is verified against the actual operations in the function body.

The AI generated plausible documentation. It just didn't match the actual code. The compiler caught the gap.

## Failure 4: The Verification Chain

On the fifth attempt, the AI got the explain block right. Then `prove check` reported a warning:

```
W: calculate_total has 'ensures result >= 0' but calls subtotal() with no ensures
   Verification chain has a gap — add 'ensures' to subtotal or mark it 'trusted'
```

The AI had written the outer function correctly, but `subtotal` — a function it also generated — had no contracts. Prove's verification chain propagates: if you claim a result, the compiler needs to trace *why* that claim holds all the way through the call graph. An unverified dependency is a warning, not a silent assumption.

The AI's instinct was to silence the warning, not address it. It added `trusted:` the same way it adds `# noqa` in Python — the fastest path to a green build. A human stops and asks "is this actually safe to skip?" The AI doesn't have that instinct. It can't weigh mission-criticality. It just suppresses.

That's the explicit opt-out — you're acknowledging the gap, not hiding it. `prove check` will report trusted functions in its coverage summary. You can ship with gaps if you choose to, but you can't pretend they don't exist.

## Why This Is a Feature

Six rounds. Each failure was in a different category:

1. **No verb** — missing intent declaration
2. **If instead of match** — defensive validation instead of contracts
3. **Explain mismatch** — documentation that drifts from implementation
4. **Unverified dependency** — silent assumptions in the call chain

Every one of these is a real class of production bugs. The AI failed not because it's bad at coding — it's extraordinarily good at generating plausible code. It failed because Prove treats all of those patterns as errors, and AI has no way to reason about whether a guard is actually necessary.

The uncomfortable point is that these aren't just AI patterns. They're human patterns too. Every codebase has functions where the docstring describes something slightly different from what the code does. Every codebase has `if` guards that should be contracts, and `function` declarations that claim neutrality while secretly doing IO. Prove rejects them regardless of who wrote them.

## The Deeper Problem

Most languages are designed around what machines can execute. The syntax exists to feed the parser. Keywords like `def` and `fn` are markers for the compiler's state machine, not information for the reader.

Prove's syntax is information. `transforms` means something. `validates` means something. The `explain` block means something the compiler will check. The `requires` clause isn't documentation — it's both a test and control flow. It gates execution.

When an AI tries to generate Prove code, it pattern-matches against its training data. But Prove's patterns encode intent, and intent isn't something you can pattern-match. The AI can produce syntactically correct Prove relatively quickly. What it can't do is produce *correct* Prove quickly — because correct Prove means the contracts verify, the verb matches the behavior, the explain rows correspond to real statements, and there are actual thoughts about the full system, not just the local context the AI was handed.

That requires understanding what you're writing.

## What Actually Happened

After six rounds and some manual fixes, we had a working function. Let's count the lines honestly.

**Prove — 11 lines, one file:**

```prove
transforms calculate_total(items List<OrderItem>, discount Discount, tax TaxRule) Price
  requires len(items) > 0
  ensures result >= 0
  explain
      calculate subtotal from items
      apply the discount to the total
      apply tax and return final price
from
    sub as Price = subtotal(items)
    discounted as Price = apply_discount(discount, sub)
    apply_tax(tax, discounted)
```

Property tests: 0 lines. The compiler generates them from `requires` and `ensures`.

**Python with equivalent guardrails — 37 lines, two files:**

```python
# calculate.py — 21 lines
def calculate_total(
    items: list[OrderItem],
    discount: Discount,
    tax: TaxRule,
) -> Price:
    """Calculate order total.

    Steps:
    - calculate subtotal from items
    - apply the discount to the total
    - apply tax and return final price
    """
    if not items:
        raise ValueError("items must not be empty")

    sub = subtotal(items)
    discounted = apply_discount(discount, sub)
    result = apply_tax(tax, discounted)

    assert result >= 0, "result must be >= 0"
    return result
```

```python
# test_calculate.py — 16 lines
@given(
    items=st.lists(order_item(), min_size=1),
    discount=discounts(),
    tax=tax_rules(),
)
def test_result_non_negative(items, discount, tax):
    assert calculate_total(items, discount, tax) >= 0

@given(
    items=st.just([]),
    discount=discounts(),
    tax=tax_rules(),
)
def test_rejects_empty_items(items, discount, tax):
    with pytest.raises(ValueError):
        calculate_total(items, discount, tax)
```

37 lines to get the same coverage — more than 3x. But the raw count isn't even the real problem. The Python version has four places where things can go wrong silently: the docstring can drift from the implementation with no one noticing, the `assert` can be stripped in production with `-O`, the test file can go out of sync with the function, and the precondition check is a convention, not a contract — nobody stops you from calling it with an empty list and catching the exception upstream, which is a different thing entirely.

The Prove version has zero of those failure modes. It's also:

- Impossible to call with an empty list (compiler-verified precondition)
- Impossible for the result to go negative without being caught (property-tested postcondition)
- Impossible for the documentation to drift from the implementation (strict explain mode)
- Impossible for a dependency to silently break the guarantee (verification chain)

The AI resistance isn't a filter on who wrote the code. It's a filter on *whether the code demonstrates understanding of what it does*. AI-generated code fails that filter often, for the same reason copy-pasted code fails it: you can produce something that looks right without knowing why it's right. This isn't an anti-AI post — the copy-paste pattern of the last decade produced the same junk, and those were humans. The problem isn't who wrote the code. It's whether anyone had to *understand* it.

If it compiles, you understood what you wrote. If it's AI-generated, it probably won't — not because AI is bad, but because understanding is the point.

---

Prove is an intent-first programming language. [The compiler source is on Gitea](https://code.botwork.se). Syntax reference, contracts, and the full type system are in the [documentation](../syntax.md).
