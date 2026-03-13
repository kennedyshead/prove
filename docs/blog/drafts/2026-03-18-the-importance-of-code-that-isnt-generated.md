---
date: 2026-03-18
title: The Importance of Code That Isn't Generated
description: When AI generates all the code, nobody understands any of it. Here's why that's a civilizational problem — and what a language can do about it.
keywords: AI code generation, software quality, open source, programming language design, intent-first, code authorship
categories:
  - programming-languages
  - design
  - ai
author: Magnus
---

# The Importance of Code That Isn't Generated

There's a pattern I've watched unfold in slow motion over the last two years. A developer hits a problem. They prompt an AI. The AI returns something plausible. They tweak it, ship it, and move on. The next developer inherits it, hits a problem, prompts an AI, gets something plausible, and ships it on top of the first thing.

Nobody understood the original code. Nobody understands the new code. It compiles. It passes the tests. It works, until it doesn't, and by then the original developer has moved on and nobody knows why any of it was written that way.

This isn't a productivity story. It's a debt story.

## The Monoculture Problem

AI generates code by finding patterns in existing code. It is extraordinarily good at this — it can produce idiomatic Python, idiomatic Go, idiomatic Rust in seconds, because it has ingested enormous amounts of each. The output looks like code written by a senior developer on that team.

The problem is that it's always senior 2024, on the average team.

AI cannot generate code that breaks from its training distribution. It cannot invent a new pattern because inventing patterns means departing from what already exists. When everyone's code is generated from the same model trained on the same corpus, codebases start converging. The interesting edge cases, the novel approaches, the weird decisions that turned out to be right five years later — those come from developers who understood their problem deeply enough to write something unusual. AI doesn't have problems. It has prompts.

Open source is built on people solving real problems they had and sharing the solution. The incentive is: I built something that works, here it is. That's not the same as: I prompted something that compiles, here it is. The latter produces volume. The former produces libraries.

## The Accountability Gap

When AI writes your code and it fails in production, you're responsible. The AI said "sorry my bad" and generated something different. You shipped the original.

This accountability gap is not an edge case — it's the central design flaw. Systems should be owned by the people who understand them. A surgeon who uses a robot doesn't get to tell the patient "the robot did it." They're accountable because they understood what they were doing and chose the tool. That's the deal.

Most codebases are now operating with code nobody understands and nobody is accountable for. The AI is not accountable. The developer who accepted the output did so without understanding it. The reviewer saw it pass CI and approved. There is no person in that chain who can answer "why does it do this?" because nobody ever knew.

This matters at scale. Individual functions don't matter. But systems built this way accumulate debt invisibly. The `if` guard that makes no sense in 2024 will be the reason a production incident takes four days to debug in 2028.

## What Languages Can Do

Most languages are indifferent to who wrote the code. A function is a function whether a human spent three days designing it or an AI generated it in 300 milliseconds. The compiler cannot tell the difference and doesn't try.

Prove tries.

Not by detecting AI output — that's a cat-and-mouse game. It requires that every function declaration contain information that can only be known by someone who understands what they're writing:

```prove
transforms calculate_discount(price Price, rate Rate) Price
  ensures result <= price
  requires rate >= 0.0 && rate <= 1.0
  explain
      apply the discount rate to the price
      return the discounted amount
from
    discounted as Price = price * (1.0 - rate)
    discounted
```

The `requires` and `ensures` clauses are not comments. The compiler generates property tests from them and runs them. If the postcondition is wrong, the build fails. The `explain` block is not documentation — each row maps to a statement in `from`, and the compiler verifies the mapping. If your explanation doesn't match your code, the build fails.

An AI can generate this. But it takes multiple rounds — the AI must understand the semantics well enough that the contracts verify, the explanation corresponds exactly to the implementation, and the verb matches the actual behavior. As I documented in [the previous post](2026-03-11-what-happens-when-ai-cant-generate-your-code.md), that typically takes six or more iterations and manual fixes. At that point you've done enough understanding to own the result.

## The Cost of Forgetting How to Write Code

There's a softer version of this problem that's harder to see.

When you write code from scratch, you build a mental model of the system. You know why a particular edge case is handled. You know what the function is actually supposed to do versus what it happens to do. You have intuitions about what will break when requirements change.

When you accept generated code without understanding it, you skip the model-building. You have a function that works. You don't have a model. The next time you touch that code, you're back to zero — re-deriving everything the person who generated it also didn't bother to understand.

This compounds. A codebase full of generated code is a codebase where every change requires starting from scratch, because there's no accumulated understanding — just accumulated output. Velocity goes up in the short run because you're not thinking. It collapses in the long run because nobody can think faster than the complexity grows.

The developers who understand their systems are becoming rare. That's not a corporate problem or an AI ethics problem — it's an infrastructure problem. When nobody understands the systems running on the internet, the internet becomes fragile in ways nobody can predict or fix.

## This Isn't Anti-AI

Using AI to generate code isn't wrong. Using AI as a rubber duck, to explain code, to generate boilerplate in a system you already understand — that's using a tool. The problem isn't the tool. It's the pattern of reaching for the tool before understanding the problem.

Prove doesn't prevent AI-assisted development. It requires that the output of that process demonstrate understanding before the compiler accepts it. If you used AI to draft the explain block and then verified that the implementation matches — you understood it. If you used AI to generate the ensures clauses and the property tests pass — the constraints are real.

The filter isn't "did a human write this" — it's "does this code demonstrate that someone understood what it does."

That's a bar worth having.

---

Prove is an intent-first programming language. [The compiler source is on Gitea](https://code.botwork.se). If it compiles, you understood what you wrote.
