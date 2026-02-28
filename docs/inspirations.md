# Design Inspirations

| Language | What Prove borrows | What Prove avoids |
|---|---|---|
| **Rust** | Ownership model, exhaustive matching, no null | Lifetime annotation burden, borrow checker complexity |
| **Haskell** | Type system, pure functions, algebraic types | IO monad complexity, lazy evaluation surprises |
| **Go** | Parameter syntax (`name Type`), simplicity as goal | Weak type system, error handling verbosity |
| **Python** | Indentation-based blocks, readability philosophy | Dynamic typing, runtime errors |
| **Zig** | `comptime` (compile-time computation with IO) | Manual memory management |
| **Ada/SPARK** | Contract-based programming, formal verification | Verbose syntax |
| **Idris/Agda** | Dependent types for encoding invariants | Academic accessibility barrier |
| **Elm** | Eliminating runtime exceptions, compiler as assistant | Limited to frontend |
| **F#** | Pragmatic algebraic types, pipeline operator | — |
