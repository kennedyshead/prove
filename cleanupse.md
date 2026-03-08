# Correct formatting

Make sure we follow this exact format pattern! If a key have a " " value we use : (example `narrative: The narrative"`), but if it is referencing function and/or variables or types and alike it should be declared without : (example `satisfies ValidState`)


There is also a need to group things in a certain way to make it more readable! 

Here is correct formatting and syntax for a module:
```prove
module Main
  narrative: """Demonstrates advanced module features: narrative, domain, temporal, invariant_network."""
  
  domain Finance
  temporal authenticate -> authorize -> access
  invariant_network ValidState
    valid_state
  
  InputOutput outputs console

  type State is
    authenticated Boolean
    authorized Boolean
    balance Integer

validates valid_state(s State)
  satisfies ValidState
from
    !s.authenticated || s.authorized

transforms authorize(s State) State
from
    State(s.authenticated, true, s.balance)

main() Result<Unit, Error>!
from
    console("Module features demo")

    // Comment with new line above
    console("Domain: Finance")
    console("Temporal: authenticate -> authorize -> access")
    console("Invariant: ValidState")
```

## Highlighting problems in tree-sitter (not checked Chroma and pygments so we need to check if its something there to)

* module_features_demo example line 3 (domain kw) is @string.documentation.prove links to @string   priority: 100   language: prove and it should not translate to a string 
* math_demo example {sqrt(16.0f)} the float literal causes rest of file to be a String (16.0f)

## Type Unit should never be needed in code 

The Unit type is what is returned if last expression do not return anything. It can never be used to indicate a null return and should not exist in the code explicitly anywhere.
main() function always return Unit implicitly, nothing else can be allowed.

## Loosen match usage

Match Expression Location Restrictions (Major Control Flow Gap)
Documentation Claim (syntax.md, types.md): 

The documentation claims "Prove has no if/else. All branching is done through match." It provides examples demonstrating how to use match directly to control logic flow, implying it can be used anywhere an expression is valid.

Implementation Reality: 
The type-checker strictly forbids using match expressions inline inside most functions. In checker.py, _check_match_restriction explicitly throws E367: match expression is only allowed in 'matches' verb functions if you attempt to use a match expression inside transforms, validates, creates, reads, inputs, or outputs verbs. You must extract all branching logic into a separate matches verb function (or main). This is a massive limitation that is not communicated in the docs.

Solution: Lets allow match and downgrade the E367 to a I367 informing that seperation to a `matched` verb would add better code-flow.

## Refinement Type Evaluation (where constraints)

Documentation Claim (types.md): 
The documentation claims the compiler validates refinement types via runtime checks, giving examples like type Port is Integer:[16 Unsigned] where 1..65535 or Integer where != 0.

Implementation Reality: 
The C code generator (_emit_refinement_validation in _emit_stmts.py) currently completely ignores and drops all numerical or boolean constraints. It only generates runtime verification code for string pattern matching (RegexLit and RawStringLit using prove_pattern_match). Attempting to use constraints like 1..65535 parses correctly but fails to generate any validation in the compiled C code, silently breaking the contract. Furthermore, the range operator (..) used in the docs is not mapped to any C equivalent in the emitter (BINARY_OP_TO_C).

Solution: implement the constraints to match docs.

# Formal Verification Syntax Inaccuracies

Documentation Claim (contracts.md): 
To showcase Prove's contract capabilities, the documentation displays this example:
ensures is_some(result) implies xs[unwrap(result)] == target
ensures is_none(result) implies target not_in xs

Implementation Reality: 
This syntax is entirely non-compilable and fictional in the current parser:
- implies / not_in / in: None of these exist as keywords or operators in the Prove lexer (tokens.py). Using them results in an immediate parsing error.
- is_some / is_none: Neither of these functions exists in the standard library. The correct stdlib implementation (found in stdlib_loader.py) relies on validates some(option Option<Value>) and validates none(option Option<Value>).

Solution: Match the docs to actual implementation!

## Near_miss Expected Identifier Bug

Documentation Claim (contracts.md): 
The documentation shows how to declare explicit negative test cases using rejected:
near_miss -1 => rejected      // negative year

Implementation Reality: 
The keyword rejected is not a recognized built-in or keyword. The parser treats it as a standard identifier (IdentifierExpr). When the testing framework (testing.py) generates the C test file for this, it literally outputs rejected as the expected C value, leading to C compiler failures because the variable rejected is undeclared.

Solution: Make sure the docs match actual implementation!

## Type Modifier Limitations (Decimal precision)

Documentation Claim (types.md): 
Modifiers are supposedly used for explicit size and precision definitions, such as Decimal:[128 Scale:2].

Implementation Reality: 
In c_types.py (_map_float()), the compiler completely disregards scaling and sizes for Decimal types. Any modifier that isn't explicitly "32" immediately falls back to a standard hardware double (CType("double")). The 128 and Scale:2 definitions are parsed but simply discarded during compilation without any static enforcement or specialized C representation.

Solution: Implement the modifiers and document each modifier in docs.

## Standard Library Ghost Functions & Types (stdlib.md)

Documentation Claim vs Reality:
- Missing Ghost Functions: Functions referenced casually in documentation examples like is_sorted or is_permutation_of (used in contracts.md to demonstrate array sorting) are completely absent from the standard library implementation.
- Builder vs StringBuilder: stdlib.md mentions a Builder type for string manipulation in the Text module. The actual type registered in stdlib_loader.py is explicitly named StringBuilder.

Solution: Fix the documentation to mirror the actual implementation
