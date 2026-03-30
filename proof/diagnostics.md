# Prove Diagnostic Reference

All static linting errors, warnings, and info diagnostics emitted by the Prove compiler.

---

## Errors

Errors indicate code that will not compile or is semantically invalid.

### Lexer Errors (E100–E109)

| Code | Message |
|------|---------|
| E100 | *(default lexer error)* |
| E101 | Unterminated string literal |
| E102 | Unterminated triple-quoted string |
| E103 | Unterminated character literal |
| E104 | Unterminated regex literal |
| E105 | Unterminated raw string literal |
| E106 | Unterminated f-string literal |
| E107 | Unknown escape sequence `\{ch}` |
| E108 | Unexpected end of escape sequence |
| E109 | Unexpected character `{ch}` |

### Parser Errors (E150–E215)

| Code | Message |
|------|---------|
| E150 | Parser error (match body) |
| E151 | Parser error (main def) |
| E200 | *(default parser error)* |
| ~E210~ | Expected token / module declaration requires a name (e.g. `module MyModule`) |
| E211 | Expected a declaration but found `{token}` |
| E212 | Expected a field definition or variant name after `is` |
| E213 | Expected an expression (name, literal, or parenthesized group) |
| E214 | `{keyword}` is a verb keyword and cannot be used as a variable or function name |
| E215 | Expected a pattern (variant name, literal, binding, or `_`) |

### Definition Errors (E300–E302)

| Code | Message |
|------|---------|
| E300 | Undefined type `{name}` |
| E301 | Duplicate definition of `{name}` |
| E302 | Variable `{name}` already defined in this scope |

### Name Resolution Errors (E310–E318)

| Code | Message |
|------|---------|
| E310 | Undefined name `{name}` |
| E311 | Undefined function `{name}` |
| E312 | Function `{name}` not imported from module `{module}` |
| E313 | Method call on non-object / module does not exist |
| E315 | Function/constant `{name}` not found in module `{module}` |
| E316 | `{name}` shadows the built-in function `{name}` |
| E317 | `{name}` conflicts with the built-in type `{name}` |
| E318 | Module `{module}` cannot import from itself |

### Type Checking Errors (E320–E341)

| Code | Message |
|------|---------|
| E320 | Type mismatch in binary expression |
| E321 | Type mismatch: callback expects `{type}` but element type is `{type}` |
| E322 | Return type mismatch: expected `{type}`, got `{type}` |
| E325 | F-string interpolation requires a stringable type, got `{type}` |
| E326 | Cannot use `Unit` as a variable type |
| E330 | Wrong number of arguments: expected `{n}`, got `{n}` |
| E331 | Field mutation in pure function; construct a new value instead |
| E335 | Argument `{name}`: type `{type}` cannot be used as Value |
| E340 | No field `{field}` on type `{type}` |
| E341 | Cannot pass borrowed value `{name}` to mutable parameter |

### Control Flow Errors (E350–E357)

| Code | Message |
|------|---------|
| E350 | Fail propagation (`!`) in non-failable function |
| E351 | `!` applied to non-failable expression |
| E352 | Function calls are not allowed in `where` constraints |
| E355 | Value `{value}` violates refinement constraint on `{name}` |
| E356 | Know claim is provably false |
| E357 | Division by zero |

### Verb Enforcement Errors (E361–E369)

| Code | Message |
|------|---------|
| E361 | Pure function cannot be failable |
| E362 | Pure function cannot call IO function `{name}` |
| E363 | Pure function cannot call IO function `{name}` (context variant) |
| E365 | `{verb}` verb requires at least one parameter |
| E366 | Recursive function `{name}` missing `terminates` |
| E368 | `{name}` requires a pure callback, but `{callback}` has verb `{verb}` |
| E369 | `par_each` callback cannot be an async verb |

### Pattern Matching Errors (E370–E379)

| Code | Message |
|------|---------|
| E370 | Unknown variant `{name}` / `attached` verb must have a return type |
| E371 | Non-exhaustive match: missing `{variants}` |
| E372 | Async function `{name}` must be called with `&` / unknown variant for Result type |
| E373 | Non-exhaustive match on `{type}`: missing `{variants}` |
| E374 | `{verb}` verb cannot declare a return type |
| E375 | Duplicate value `{value}` in lookup table |
| E376 | Lookup operand must be a literal or variant name |
| E377 | `{type}` is not a `[Lookup]` type |
| E378 | `{operand}` has `{n}` values — reverse lookup is ambiguous |
| E379 | Entry `{variant}` has `{n}` values but binary table has `{m}` columns |

### Contract Checking Errors (E380–E396)

| Code | Message |
|------|---------|
| E380 | `ensures` expression must be Boolean, got `{type}` |
| E381 | `requires` expression must be Boolean, got `{type}` |
| E382 | `satisfies` references undefined type or invariant network `{name}` |
| E383 | `near_miss` expected type `{type}` doesn't match return type `{type}` |
| E384 | `know` expression must be Boolean, got `{type}` |
| E385 | `assume` expression must be Boolean, got `{type}` |
| E386 | `believe` expression must be Boolean, got `{type}` |
| E387 | Unsupported type `{type}` in lookup column |
| E388 | CSV file not found: `{path}` |
| E389 | Cannot determine return column for lookup `{type}` |
| E391 | Duplicate explain entry name `{name}` |
| E392 | Explain has `{n}` named entries but `{m}` ensures clauses |
| E393 | Function `{name}` has `believe` but no `ensures` |
| E394 | Explain condition must be Boolean, got `{type}` |
| E395 | Implicit Value conversion: body returns `{type}` but function declares `{type}` |
| E396 | Invariant constraint in `{name}` must be Boolean, got `{type}` |

### Keyword & Misc Errors (E397–E409)

| Code | Message |
|------|---------|
| E397 | `binary` is reserved for stdlib type definitions |
| E398 | IO-bearing `attached` function `{name}` can only be called from a `listens` or `attached` body |
| E399 | *(reserved — contract error)* |
| E400 | Match arm returns Unit but other arms return `{type}` |
| E401 | `event_type` must reference an algebraic type |
| E402 | `renders` first parameter must be `List<Listens>` |
| E403 | Registered function `{name}` is not a `{verb}` verb |
| E404 | Return type of `{name}` does not match a variant of event type `{type}` |
| E405 | `event_type` annotation is only valid on `listens`, `renders`, or `attached` verb |
| E406 | `{verb}` verb requires an `event_type` annotation |
| E407 | `state_init` annotation is only valid on `renders` verb |
| E408 | `renders` verb requires a `state_init` annotation |
| E409 | `state_type` annotation is only valid on `listens` verb |

### Comptime Execution Errors (E410–E422)

| Code | Message |
|------|---------|
| E410 | Tail recursion not supported in comptime blocks |
| E411 | Unsupported expression type in comptime: `{type}` |
| E412 | `++` operator requires both operands to be lists or strings |
| E413 | Unsupported binary operator in comptime: `{op}` |
| E414 | Unsupported unary operator in comptime: `{op}` |
| E415 | Implicit match not supported in comptime |
| E416 | Non-exhaustive match in comptime |
| E417 | Comptime evaluation failed: `{error}` |
| E418 | Undefined variable `{name}` in comptime |
| E419 | Only simple function calls supported in comptime |
| E420 | `read()` expects a single string argument / `platform()` takes no arguments / `len()` expects a single argument / `contains()` expects two arguments |
| E421 | File not found: `{path}` |
| E422 | Unknown function `{name}` in comptime |

### Type Recursion & Row Polymorphism Errors (E423–E436)

| Code | Message |
|------|---------|
| E423 | Recursive type `{name}` has no base case |
| E430 | `with` references unknown parameter `{name}` |
| E431 | `with` on parameter `{name}` which is not typed `Struct` |
| E432 | Duplicate `with` for `{param}.{field}` |
| E433 | Field `{field}` not declared in `with` constraints for Struct parameter |
| E434 | Record `{type}` does not satisfy Struct constraints |
| E435 | Field `{name}` has type Unit, which has no runtime representation |
| E436 | `{verb}` with `requires` must be failable (`!`) or return `Option<T>` |

---

## Warnings

Warnings indicate potential issues that do not prevent compilation.

### Unused & Shadowing Warnings (W300–W313)

| Code | Message |
|------|---------|
| W300 | Unused variable `{name}` |
| W304 | Match condition is always true (guaranteed by `requires`) |
| W305 | Duplicate match arm for variant `{name}` |
| W311 | Intent declared but no `ensures` or `requires` to validate it |
| W312 | `{module}` has no `{verb} {name}` |
| W313 | Intent prose doesn't reference any function concepts |

### Verification & Contract Warnings (W321–W328)

| Code | Message |
|------|---------|
| W321 | Explain entry `{name}` doesn't reference any function concepts |
| W322 | Duplicate near-miss input |
| W323 | Function `{name}` has `ensures` but no `explain` |
| W324 | Function `{name}` has `ensures` but no `requires` |
| W325 | Function `{name}` has `explain` but no `ensures` |
| W327 | Cannot prove know claim; treating as runtime assertion |
| W328 | `ensures` clause doesn't reference `result` |

### Mutation Testing & Purity Warnings (W330–W332)

| Code | Message |
|------|---------|
| W330 | Function `{name}` had a surviving mutant: `{description}` |
| W332 | Unused result of pure function `{name}` |

### Domain Profile Warnings (W340–W343)

| Code | Message |
|------|---------|
| W340 | Unknown domain `{name}`; known domains: finance, safety, general |
| W341 | Domain `{name}` requires `ensures` contract on `{function}` |
| W342 | Domain `{name}` requires `near_miss` examples on `{function}` |
| W343 | Narrative flow step `{step}` is not a defined function |

### Lookup Table Warnings (W350)

| Code | Message |
|------|---------|
| W350 | Lookup has duplicate column type `{type}`; use named columns to disambiguate |

### Ownership & Failable Warnings (W360–W373)

| Code | Message |
|------|---------|
| W360 | `{path}` is released by function call but also used elsewhere in this expression |
| W361 | *(unwrap panic warning)* |
| W370 | Function `{name}` calls verified function `{callee}` but has no `ensures` clause |
| W371 | Internal function `{name}` calls verified function `{callee}` but has no `ensures` clause |
| W372 | Cannot prove arm-bound know claim; treating as runtime assertion / failable call result discarded |
| W373 | Failable call in lambda without `!` — returns Result instead of unwrapped value |

### Temporal & Satisfies Warnings (W390–W391)

| Code | Message |
|------|---------|
| W390 | Temporal operation `{name}` appears before `{prev}`; declared order violated |
| W391 | Function satisfies invariant `{name}` but has no `ensures` clause |

### Prose Coherence Warnings (W501–W506)

| Code | Message |
|------|---------|
| W501 | Verb `{verb}` not described in module narrative |
| W502 | Explain entry doesn't correspond to any operation in from-block |
| W503 | `chosen` declared without any `why_not` alternatives |
| W504 | `chosen` text doesn't correspond to any operation in from-block |
| W505 | `why_not` entry mentions no known function or type |
| W506 | `why_not` entry rejects an approach that the from-block appears to use |

### Intent Parsing Warnings (W601–W603)

| Code | Message |
|------|---------|
| W601 | Vocabulary entry format error / unrecognized verb in intent |
| W602 | Vocabulary term `{name}` is defined but never referenced |
| W603 | Flow references undefined module `{module}` |

---

## Info

Informational diagnostics — suggestions and style hints that do not affect compilation.

### Module Info (I201)

| Code | Message |
|------|---------|
| I201 | Prove requires a module declaration with narrative |

### Parser Info (I210)

| Code | Message |
|------|---------|
| I210 | Trailing comma in parameter list |

### Unused & Style Info (I300–I320)

| Code | Message |
|------|---------|
| I300 | Unused variable `{name}` |
| I301 | Unreachable match arm after wildcard |
| I302 | `{name}` is imported from `{module}` but never used |
| I303 | Type `{name}` is defined but never used |
| I304 | Constant `{name}` is defined but never used |
| I305 | `{name}` is initialized at function scope but only used inside a single match arm |
| I310 | Implicitly typed variable `{name}` |
| I311 | Value -> `{type}` coercion is checked at runtime |
| I314 | Unknown local module `{module}` |
| I320 | Function `{name}` has `{n}` statements but no contracts |

### Coherence & Async Info (I340–I378)

| Code | Message |
|------|---------|
| I340 | Function `{name}` uses vocabulary not found in module narrative |
| I360 | `validates` has implicit Boolean return |
| I367 | Consider extracting match to a `{verb}` verb function for better code flow |
| I375 | `&` has no effect on non-async function `{name}` |
| I377 | `attached` call `{name}` runs synchronously outside a `listens` body |
| I378 | `detached` function `{name}` called without `&` |

### Completeness Info (I601)

| Code | Message |
|------|---------|
| I601 | Function `{name}` has incomplete implementation (todo) |

---

## Summary

| Severity | Count |
|----------|-------|
| Error    | 113   |
| Warning  | 38    |
| Info     | 18    |
| **Total** | **169** |
