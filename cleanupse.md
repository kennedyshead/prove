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

## Type Unit should never be needed in code 

The Unit type is what is returned if last expression do not return anything. It can never be used to indicate a null return and should not exist in the code explicitly anywhere.
main() function always return Unit implicitly, nothing else can be allowed.
