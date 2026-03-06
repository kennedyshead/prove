---
date: 2026-03-04
title: Why I Built My Own Programming Language
description: How a frustrating "sorry my bad" from an AI became the seed of Prove - the intent-first programming language.
keywords: programming language, AI slop, intent-first, compiler, programming language design
categories:
  - programming-languages
  - design
  - philosophy
author: Magnus
---

# Why I Built My Own Programming Language

Most programming languages weren't built for humans. They were built with computers on center stage — every decision optimized for what machines can parse, not what developers can think. We're forced to translate our intent through a layer of syntax that was designed for compilers, not comprehension.

Then there's AI. It generates code at an unprecedented scale, but it's trained on our collective work without consent, and to be honest most of that code is kind of iffy. The more we rely on it, the more we lose: innovation slows, open source dies, and we're frozen at the exact moment each LLM was trained. When everyone stops writing code, nothing new gets invented.

I started Prove conceptually six years ago. These frustrations built up, but the real trigger came when I shipped AI written code — code with strict guard rails, that failed misserably. The AI's response? "Sorry my bad."

That's when it hit me: I used AI out of laziness, but I'd bear the responsibility for its failures. The lack of accountability, and the never ending ping-pong prompting was the final straw. I realized we need languages that make intent explicit — where code can't be faked, where the compiler enforces understanding.

## The Verb Pattern

Look at most codebases: `def validate_email`, `def new_email`, `def get_email`. We write the cryptic word `def` three times and add the word `validate, new, get` plus a strange looking `_` because we need unique names. The `fn`/`def`/`function` keywords tell us what something is — but we already knew that so its 100% redundant, it's the compiler/interpreter that need the fn/function statement.

Prove uses verbs instead: validates, transforms, reads, creates. A function's purpose is in its signature, not a prefixed name. The compiler enforces it. You can't claim to validate something and secretly modify state.

## The Explain Statement

Here's where things really gets wild. The explain statement isn't just documentation — it's executable natural language. The compiler parses it and translates it directly to code execution.

### Python with docstring

```python
async def update_email(user_id: int, new_email: str) -> User:
    """Update a user's email address.
    
    Preconditions:
    - user_id must be a valid ID (existing user)
    - new_email must be a valid email format
    
    Postconditions:
    - Returned user must exist and be valid
    
    Steps:
    1. Get the email address
    2. Fetch the user from the database
    3. Validate the email format
    4. Set the email on the user
    5. Save and return the user
    """
    if not valid_id(user_id):
        raise ValueError("Invalid user ID")
    
    user = await db.get_user(user_id)
    if not user:
        raise ValueError("User not found")
    
    if not validate_email(new_email):
        raise ValueError("Invalid email")
    
    user.email = new_email
    await user.save()
    
    if not valid_user(user):
        raise ValueError("Failed to save valid user")
    
    return user
```

### Prove with Explain (declerative ensures/requires guards execution)

```prove
outputs update_email(id Option<Integer>, email Option<Email>) User:[Mutable]!
  ensures valid_user(user)
  requires valid id(id) && valid email(email)
  explain
      We fetch the user
      we set the email to user
      save and return the user
from
    user as User:[Mutable] = user(id)!
    set_email(user, email)
    save(dump_user(user))
```

Both have documentation describing the steps. But:

- **Python docstring**: The implementation can drift from the docs — and nobody notices until runtime.

- **Prove explain**: The implementation *cannot* drift from the docs — the compiler checks each phrase against the actual code. If you say "validate the email" but forget the validation, it won't compile.

This is accountability. Documentation can lie. Explain can't — because the compiler checks it against the actual implementation.

For a complete working example with all the supporting types and functions, see the [documentation](../contracts.md).

Documentation can lie. This can't — because the compiler checks it against the actual implementation.

But there's something else that makes explain powerful that isn't obvious at first: it's editable code, not a conversation.

When you use AI to write code, every change is a fresh prompt. You ping-pong with the AI to maybe get a working result, and each refactor requires re-explaining everything from scratch. With explain, you're writing source code. One small edit propagates consistently across your entire codebase.

Here's the thing that gets me excited: as your codebase grows, the compiler can start suggesting functions that fit your intent. The explain statement becomes a query against your library — "I need to transform X by Y" auto-completes to functions that actually do that. Every well-documented function you write makes the next one easier. The more complete your library, the less you need to write explicitly. Anyone can generate correct code by adding the `explain`, but only when the building blocks exist. Each explain + implementation pair builds those blocks.

## The Road Ahead

This is just the beginning. Every problem I hit while writing the compiler becomes a new feature. [Refinement types](https://en.wikipedia.org/wiki/Refinement_type), binary ASTs (un-scrapable), the verb system, [contracts-as-tests](https://en.wikipedia.org/wiki/Design_by_contract) — they're all responses to real pain.

Prove shares roots with other verification-focused languages like Lean[^1], Coq/Rocq[^2], F\*[^3], and Idris[^4] — all take correctness seriously. But unlike those (which are primarily proof assistants), Prove aims to be a practical general-purpose language.

If you've ever felt the frustration of code that "just works" without understanding, or watched AI slop pollute your codebase, or wondered why we still write code the same way we did in the 70s — that's why Prove exists.

It's not about replacing developers. It's about languages that respect them.

---

Prove is an intent-first programming language. If it compiles, you understood what you wrote. If it's AI-generated, it won't.

[^1]: [Lean](https://lean-lang.org/) — a proof assistant and functional programming language
[^2]: [Coq / Rocq](https://rocq-prover.org/) — a proof assistant used for program verification
[^3]: [F\*](https://www.fstar-lang.org/) — a proof-oriented programming language from Microsoft Research
[^4]: [Idris](https://www.idris-lang.org/) — a dependently typed programming language
[^5]: [Python](https://www.python.org/) — the language used in the comparison examples
