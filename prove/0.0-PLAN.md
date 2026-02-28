# Prove Compiler v0.1 — Implementation Plan

## Context

Prove is a new programming language where "if it compiles, it ships." The compiler is a Python POC that transpiles `.prv` source files to C, then invokes gcc/clang for native binaries. The first program to compile: a RESTful HTTP server.

This plan covers the full compiler from zero to a working `prove build` that produces a native binary.

## Already Done

- `/workspace/philosophy.md` — Complete language specification
- `/workspace/LICENSE` — Prove Source License v1.0
- `/workspace/example.prv` — Comprehensive example exercising all features
- `/workspace/tree-sitter-prove/` — Tree-sitter grammar + Neovim integration

---

## Scope

**In v0.1:**
- 4 verbs + main (`transforms`, `inputs`, `outputs`, `validates`, `main`)
- Verb-dispatched function identity `(verb, name, param_types)`
- Refinement types, algebraic types, record types, generics
- Type modifiers `Type:[Modifier ...]`
- `!` fallibility (IO verbs only), `!` propagation at call sites
- `from` body marker, `as` variable declarations
- Proof obligations (structural verification, not SMT)
- Contracts (`ensures`/`requires`) with auto-generated property tests
- AI-resistance Phase 1: proof obligations, counterfactual annotations (`why_not`/`chosen`), near-miss testing, epistemic annotations (`know`/`assume`/`believe`)
- Implicit match (algebraic first param on `inputs`)
- Lambdas (`|params| expression`), pipe operator (`|>`), no loops
- Conversational compiler errors
- C code generation (tagged unions, refcounting, monomorphized generics)
- CLI: `prove build`, `prove check`, `prove test`, `prove new`
- Minimal stdlib: io, http, json, string, list
- C runtime: refcounted String/List, tagged unions, HTTP server via libuv

**Deferred to v0.2+:**
- Binary `.prv` format, semantic normalization, source fragmentation (Phase 3)
- Domain-specific syntax (`domain` keyword), narrative coherence
- Temporal effect ordering, invariant networks
- Refutation challenges
- Ownership/linear types (`File:[Own]`), async/concurrency
- Intent annotation verification (structural check only in v0.1)
- LSP, formatter (stubs only in v0.1)
- Incremental compilation, C FFI
- Context-aware call resolution (verb disambiguation at call sites)
- `valid` as function reference to higher-order functions

---

## Project Structure

```
/workspace/prove/
  pyproject.toml                    # Python packaging, `prove` CLI entry point
  CLAUDE.md                         # Dev instructions
  .gitignore

  src/
    prove/
      __init__.py                   # Version
      __main__.py                   # python -m prove
      cli.py                        # Click CLI (build/check/test/new + stubs for format/lsp/view)

      # --- Frontend ---
      source.py                     # Span, SourceFile (no deps)
      tokens.py                     # TokenKind enum, Token dataclass
      lexer.py                      # Hand-written scanner
      ast_nodes.py                  # Frozen dataclass AST hierarchy
      parser.py                     # Recursive descent + Pratt expression parsing

      # --- Middle ---
      types.py                      # Type representations (Primitive, Refinement, Algebraic, Fn, Generic, TypeVar)
      symbols.py                    # Symbol, Scope, SymbolTable
      resolver.py                   # Name resolution (2-pass: collect decls, resolve refs)
      typechecker.py                # Bidirectional type checking + refinement + exhaustiveness
      verb_checker.py               # Verb constraint enforcement (purity, IO, fallibility)
      contracts.py                  # Contract extraction from ensures/requires
      prover.py                     # Structural proof verification

      # --- Backend ---
      codegen/
        __init__.py
        c_types.py                  # Prove type → C type mapping
        c_emitter.py                # C source builder (types, functions, expressions)
        c_runtime.py                # Copies/generates runtime .c/.h files
        c_compiler.py               # Invokes gcc/clang

      # --- Supporting ---
      errors.py                     # Diagnostic, DiagnosticLabel, Suggestion, renderer
      config.py                     # prove.toml loading (PackageConfig, BuildConfig, TestConfig)
      project.py                    # prove new scaffolding
      testing.py                    # Property test generation + runner
      builder.py                    # Build pipeline orchestrator
      formatter.py                  # Stub
      lsp.py                        # Stub

    prove_runtime/
      __init__.py                   # Helpers to locate runtime files via importlib.resources
      include/
        prove_runtime.h             # Core: refcount macros, Prove_Header, arena allocator
        prove_string.h              # Prove_String (refcounted, length-prefixed, immutable)
        prove_list.h                # Prove_List (refcounted, dynamic array)
        prove_option.h              # Prove_Option tagged union
        prove_result.h              # Prove_Result tagged union
        prove_http.h                # HTTP server API (over libuv)
      src/
        prove_runtime.c             # Runtime implementation
        prove_http.c                # HTTP server implementation (libuv + minimal HTTP parser)

  stdlib/                           # Standard library .prv files (package data)
    core/
      prelude.prv                   # Auto-imported: Option, Result, basic types
    io.prv                          # print, println, read_line
    http.prv                        # Server, Request, Response, Status
    json.prv                        # encode, decode
    string.prv                      # String functions
    list.prv                        # List functions (map, filter, reduce)

  tests/
    conftest.py                     # Shared fixtures
    test_lexer.py
    test_parser.py
    test_resolver.py
    test_typechecker.py
    test_verb_checker.py
    test_contracts.py
    test_prover.py
    test_codegen.py
    test_builder.py
    test_cli.py
    fixtures/                       # Sample .prv files
      hello.prv
      types.prv
      contracts.prv
      verbs.prv
      http_server.prv

  examples/
    hello/
      prove.toml
      src/main.prv
    http_server/
      prove.toml
      src/main.prv
```

---

## Compiler Pipeline

```
.prv source (text)
  |
  +- 1. Lexer -----------> list[Token]
  +- 2. Parser ----------> Module (AST)
  +- 3. Resolver --------> AST + SymbolTable (names resolved, verb-dispatched)
  +- 4. Type Checker ----> Typed AST (every expr annotated with type)
  +- 5. Verb Checker ----> Verb constraints verified (purity, IO, fallibility)
  +- 6. Proof Verifier --> Proof obligations structurally verified
  +- 7. Contract Extractor -> Extracted contracts (for test gen)
  |     ^ prove check stops here
  +- 8. C Emitter -------> .c/.h files in build/generated/
  +- 9. C Compiler ------> native binary in build/
  |
  +- prove test: contracts -> generated C test code -> compile -> run
```

---

## Key Design Decisions

### Grammar Highlights
- **Indentation-based blocks** — no braces, no semicolons. Newlines terminate statements. Newlines suppressed after operators, commas, opening brackets, `->`, `=>`
- **Intent verbs** — `transforms`, `inputs`, `outputs`, `validates` declare function purpose. `main` is special (no verb)
- **`from` body marker** — every function body begins with `from`
- **`as` variable declarations** — `name as Type = value`
- **`!` fallibility** — on declarations: can fail. At call sites: propagate failure. IO verbs only
- **Implicit match** — `inputs` with algebraic first param gets pattern matching in body (patterns + `=>` directly after `from`)
- **Verb-dispatched identity** — `(verb, name, param_types)` uniquely identifies a function. Same name, different verbs = different functions
- **Go-style params** — `name Type` (no colon)
- **Type modifiers** — `Type:[Modifier ...]` for storage concerns (size, signedness, mutability, encoding)
- **Expression precedence** (low->high): `|>`, `||`, `&&`, `==`/`!=`, `<`/`>`/`<=`/`>=`, `..`, `+`/`-`, `*`/`/`/`%`, unary `!`/`-`, postfix `!`/`.`/`()`
- **Generic `<` ambiguity** — after CamelCase = type args; after snake_case = comparison
- **String interpolation** — `"hello {name}"` with `\{`/`\}` for literal braces
- **Lambdas** — `|params| expression` — single expression, pure, only as arguments
- **No loops** — iteration via `map`, `filter`, `reduce`, recursion

### Verb Enforcement Rules

| Verb | Pure | IO | `!` allowed | Return type |
|------|------|----|-------------|-------------|
| `transforms` | Yes | No | No | Explicit. Failure via `Result<T,E>` / `Option<T>` |
| `validates` | Yes | No | No | Implicitly `Boolean` |
| `inputs` | No | Yes (read) | Yes | Explicit |
| `outputs` | No | Yes (write) | Yes | Explicit |
| `main` | No | Yes (both) | Yes | `Result<Unit, Error>!` |

- `transforms` / `validates` cannot call `inputs` / `outputs` functions
- `!` can only appear on `inputs`, `outputs`, and `main`
- `validates` return type is always `Boolean` — never declared, always implied

### C Code Generation Strategy
- **Algebraic types** -> C tagged unions (enum tag + union of data structs + inline constructors)
- **Record types** -> C structs
- **Pattern matching** -> `switch` on tag with destructuring into locals
- **Refinement types** -> base C type + validation function; compile-time constants checked statically, runtime values require `.check()!`
- **Verb enforcement** -> completely erased at codegen (compile-time only)
- **`!` propagation** -> early return: `if (tmp.tag == ERR) return (Result){.tag=ERR, .err=tmp.err};`
- **Generics** -> monomorphized (each concrete `Result<Config, Error>` gets its own C struct)
- **Memory** -> reference counting (`Prove_Header` with atomic refcount + destructor). Retain on store, release at scope exit. No cycle detection in v0.1 (immutable-by-default makes cycles rare)
- **Strings** -> `Prove_String*` (refcounted, length-prefixed, immutable)
- **Lists** -> `Prove_List*` (refcounted, dynamic array with void* + element_size)
- **HTTP** -> libuv for event loop + minimal HTTP/1.1 parser
- **Pipe operator** -> desugars to nested function calls: `a |> f |> g` -> `g(f(a))`
- **Lambdas** -> anonymous C functions (or inlined where possible)

### Proof Verification (v0.1 Scope)
Structural checks only — NOT SMT/theorem proving:
1. **Completeness**: recursive fns need `base` + `termination` obligations
2. **Keyword matching**: proof text references appropriate concepts for the function
3. **Consistency**: obligation names don't repeat, reference existing params/entities
4. **Contract coverage**: each `ensures` has at least one addressing proof obligation
5. Functions with `ensures` but no `proof` block -> compiler error

### AI-Resistance (v0.1 Scope)
- **Proof obligations** — required for every function with `ensures` clauses
- **Counterfactual annotations** — `why_not`/`chosen` stored, structural plausibility check
- **Near-miss testing** — `near_miss` examples verified to exercise distinct branches
- **Epistemic annotations** — `know` = type-proven (zero cost), `assume` = runtime check inserted, `believe` = adversarial tests generated

### Test Generation (from contracts)
- Extract `ensures`/`requires` clauses per function
- Generate random inputs respecting refinement type bounds + boundary values
- 1000 rounds default (configurable via `--property-rounds`)
- Doc comment examples (`///   split("a,b", ",") == ["a", "b"]`) extracted as test cases
- Edge cases auto-generated from type signatures (0, 1, -1, MAX, MIN, empty list, etc.)
- `near_miss` annotations become explicit test cases
- `believe` annotations trigger adversarial test generation

---

## Python Dependencies

```toml
[project]
requires-python = ">=3.11"
dependencies = ["click>=8.1"]

[project.optional-dependencies]
dev = ["pytest>=7.0", "pytest-cov>=4.0", "ruff>=0.4", "mypy>=1.10"]

[project.scripts]
prove = "prove.cli:main"
```

No parser generators, no ANTLR, no PLY. Hand-written lexer and recursive descent parser for full control over error messages.

---

## Implementation Phases

### Phase 1: Skeleton + CLI
1. Create `pyproject.toml`, `src/prove/__init__.py`, `__main__.py`
2. `src/prove/cli.py` — Click CLI with all subcommands (build/check/test/new + stubs for format/lsp/view)
3. `src/prove/source.py` — `Span`, `SourceFile`
4. `src/prove/errors.py` — `Diagnostic`, `DiagnosticRenderer` with Rust-style colored output
5. `src/prove/config.py` — `prove.toml` loading
6. `src/prove/project.py` — `prove new` scaffolding (creates prove.toml, src/main.prv, LICENSE, .gitignore)
7. **Verify**: `pip install -e ".[dev]"` -> `prove --help` -> `prove new hello` creates a project

### Phase 2: Frontend — Lexer + Parser + AST
8. `src/prove/tokens.py` — `TokenKind` enum (~65 token types), `Token` dataclass
   - Verbs: `TRANSFORMS`, `INPUTS`, `OUTPUTS`, `VALIDATES`
   - Keywords: `MAIN`, `FROM`, `TYPE`, `IS`, `AS`, `WITH`, `USE`, `WHERE`, `MATCH`, `IF`, `ELSE`, `COMPTIME`, `VALID`, `MODULE`
   - Contracts: `ENSURES`, `REQUIRES`, `PROOF`
   - AI-resistance: `WHY_NOT`, `CHOSEN`, `NEAR_MISS`, `KNOW`, `ASSUME`, `BELIEVE`, `INTENT`, `NARRATIVE`, `TEMPORAL`, `SATISFIES`, `INVARIANT_NETWORK`
   - Literals, operators, punctuation, `BANG` (`!`), `PIPE_ARROW` (`|>`), `FAT_ARROW` (`=>`), `DOT_DOT` (`..`)
9. `src/prove/lexer.py` — Hand-written scanner:
   - Significant newlines (suppressed after operators, commas, `=>`, `|>`)
   - Indentation tracking for block structure
   - String interpolation (`"hello {name}"`)
   - Doc comments (`///`) and line comments (`//`)
   - CamelCase -> `TYPE_IDENTIFIER`, snake_case -> `IDENTIFIER`, UPPER_SNAKE -> `CONSTANT_IDENTIFIER`
10. `src/prove/ast_nodes.py` — Full AST hierarchy (~35 frozen dataclasses):
    - Top-level: `Module`, `FunctionDef`, `MainDef`, `TypeDef`, `ConstantDef`, `ImportDecl`
    - `FunctionDef` includes: `verb`, `name`, `params`, `return_type`, `fail_marker`, `ensures`, `requires`, `proof_block`, AI-resistance annotations, `body`
    - Types: `SimpleType`, `GenericType`, `ModifiedType`, `RefinementType`, `AlgebraicType`, `RecordType`
    - Exprs: `BinaryExpr`, `UnaryExpr`, `CallExpr`, `FieldExpr`, `PipeExpr`, `FailPropExpr`, `LambdaExpr`, `ValidExpr`, `IfExpr`, `MatchExpr`, `ListLiteral`, all literals
    - Patterns: `VariantPattern`, `WildcardPattern`, `LiteralPattern`, `BindingPattern`
    - Statements: `VarDecl` (`as`), `Assignment`
    - Annotations: `ProofBlock`, `ProofObligation`, `WhyNot`, `Chosen`, `NearMiss`, `Know`, `Assume`, `Believe`
11. `src/prove/parser.py` — Recursive descent with Pratt expression parsing:
    - Verb-prefixed function declarations
    - `from` body marker detection
    - Implicit match detection (pattern + `=>` after `from` in `inputs`)
    - Proof blocks (obligation name `:` proof text)
    - `ensures`/`requires` chains between signature and `from`
    - AI-resistance annotation parsing
    - Type modifier syntax `Type:[Modifier ...]`
    - Lambda expressions `|params| expr`
12. **Verify**: Parse `examples/http_server/src/main.prv` to AST, pretty-print

### Phase 3: Analysis — Types + Verbs + Proofs
13. `src/prove/types.py` — Type hierarchy:
    - `PrimitiveType` (Integer, Decimal, Float, Boolean, String, Byte, Character) with modifier support
    - `RefinementType` (base type + constraint expression)
    - `AlgebraicType` (variants with optional fields)
    - `RecordType` (named fields)
    - `FnType` (verb, params, return type, fail marker)
    - `GenericType`, `TypeVar`
    - Builtin: `ResultType`, `OptionType`, `ListType`, `UnitType`
14. `src/prove/symbols.py` — Symbol, Scope, SymbolTable with push/pop scope
    - Functions keyed by `(verb, name, param_types)` triple
    - Variant constructors registered as callable symbols
15. `src/prove/resolver.py` — Two-pass name resolution:
    - Pass 1: collect top-level decls (functions with verbs, types, constants, imports)
    - Pass 2: resolve all references
    - Register builtins: `Integer`, `String`, `Boolean`, `Decimal`, `Float`, `List`, `Option`, `Result`, `print`, `println`
    - Verb-dispatched lookup (same name can resolve to different functions based on verb)
16. `src/prove/typechecker.py` — Bidirectional type checking:
    - Primitive types with modifiers, binary/unary ops
    - Algebraic types + exhaustive pattern matching
    - Record types + field access
    - Generic type inference (Hindley-Milner with unification)
    - Refinement types (range constraints: static check for literals, runtime check insertion for dynamic values)
    - `Result`/`Option` with `!` propagation (IO verbs only)
    - `validates` return type always `Boolean`
    - Implicit match desugaring for `inputs` with algebraic first param
    - Lambda type inference
17. `src/prove/verb_checker.py` — Verb constraint enforcement:
    - `transforms`: no calls to `inputs`/`outputs`, no `!`
    - `validates`: no calls to `inputs`/`outputs`, no `!`, return type is `Boolean`
    - `inputs`/`outputs`: IO allowed, `!` allowed
    - `main`: unrestricted
    - Lambda bodies: must be pure (no IO calls)
18. `src/prove/contracts.py` — Extract `ensures`/`requires` from typed AST
19. `src/prove/prover.py` — Structural proof verification:
    - `ensures` without `proof` block -> compiler error
    - Proof obligation completeness, keyword matching, consistency
    - Near-miss verification (distinct branches exercised)
    - Epistemic annotation handling: `know` -> verify provable, `assume` -> insert runtime check, `believe` -> flag for test gen
20. **Verify**: `prove check examples/http_server/src/main.prv` succeeds with no errors

### Phase 4: Backend — C Codegen + Runtime
21. `src/prove/codegen/c_types.py` — Type mapping:
    - `Integer` -> `int64_t` (with modifier-aware sizing: `Integer:[32 Unsigned]` -> `uint32_t`)
    - `Decimal` -> `double` (v0.1 simplification; proper decimal in v0.2)
    - `Float` -> `double` / `float` based on modifier
    - `Boolean` -> `bool`
    - `String` -> `Prove_String*`
    - `List<T>` -> `Prove_List*`
    - Algebraic types -> tagged unions
    - Record types -> C structs
    - Monomorphization tracking for generics
22. `src/prove/codegen/c_emitter.py` — C source generation:
    - Type definitions (tagged unions, structs)
    - Function definitions: verb is erased, generates normal C functions
    - Name mangling: `verb_name_paramtypes` to avoid collisions (verb-dispatched identity)
    - Expressions (binary ops, calls, field access, match -> switch, `!` -> early return, pipe -> nested calls)
    - Lambda -> anonymous/inlined functions
    - Scope-based retain/release for refcounted values
    - `main()` entry point wrapper
23. `src/prove_runtime/include/*.h` + `src/prove_runtime/src/*.c` — C runtime:
    - `prove_runtime.h/c`: Prove_Header (refcount), retain/release macros, arena allocator
    - `prove_string.h`: Prove_String (create, concat, slice, compare, format, interpolation)
    - `prove_list.h`: Prove_List (create, push, get, map, filter, reduce, len)
    - `prove_option.h`: Prove_Option (Some/None tagged union)
    - `prove_result.h`: Prove_Result (Ok/Err tagged union)
    - `prove_http.h/c`: HTTP server (libuv event loop, request parsing, routing, response)
24. `src/prove/codegen/c_compiler.py` — Find and invoke gcc/clang with flags
25. `src/prove/codegen/c_runtime.py` — Locate and copy runtime files to build dir
26. `src/prove/builder.py` — Wire full pipeline: discover sources -> lex -> parse -> resolve -> typecheck -> verb check -> proofs -> contracts -> emit C -> compile
27. **Verify**: `prove build` on hello world -> native binary that runs

### Phase 5: Integration + Testing
28. `src/prove/testing.py` — Generate C test code from contracts:
    - Random inputs respecting refinement type bounds + boundary values
    - Doc comment examples as test cases
    - Near-miss annotations as explicit test cases
    - `believe` annotations trigger adversarial test generation
    - 1000 rounds default (configurable via `--property-rounds`)
29. Wire `prove test` in CLI
30. `stdlib/` — Standard library .prv files defining types/signatures for io, http, json, string, list
31. `examples/http_server/` — Full REST server example:
    ```prove
    type Route is Get(path String) | Post(path String)

    inputs request(route Route, body String, db Database) Response!
        from
            Get("/health") => ok("healthy")
            Get("/users")  => users(db)! |> encode |> ok
            Post("/users") => create(db, body)! |> encode |> created
            _              => not_found()

    main() Result<Unit, Error>!
        from
            db as Database = connect("postgres://localhost/app")!
            server as Server = new_server()
            route(server, "/", request)
            listen(server, 8080)!
    ```
32. `tests/` — Unit tests for every phase + integration test (`.prv` -> binary -> run -> assert output)
33. **Verify end-to-end**: `prove new myserver` -> write REST server `.prv` -> `prove build` -> run binary -> `curl localhost:8080/health` -> 200 OK

---

## Verification Plan

1. **Unit tests**: `python -m pytest tests/` — test each compiler phase in isolation with fixture `.prv` files
2. **Lint**: `ruff check src/ tests/`
3. **Type check compiler code**: `mypy src/prove/`
4. **Integration test**: Compile `examples/hello/src/main.prv` -> run binary -> check stdout = "Hello from Prove!"
5. **HTTP server test**: Compile `examples/http_server/src/main.prv` -> run binary -> curl endpoints -> verify JSON responses
6. **`prove test` test**: Run `prove test` on a `.prv` file with contracts -> verify property tests pass
7. **Error quality test**: Feed invalid `.prv` files -> verify compiler errors include source location, explanation, and suggestions
8. **Verb enforcement test**: Verify `transforms` calling `inputs` -> compile error. `validates` with `!` -> compile error.

---

## Risk Mitigations

| Risk | Mitigation |
|------|------------|
| Refinement type solving is undecidable | v0.1: only range constraints + literal checks. Complex constraints -> runtime checks |
| Monomorphization code bloat | Acceptable for POC. Track generated instantiations to avoid duplicates |
| Refcount overhead | Only heap types (String, List) are refcounted. Small values (Int, Float, Bool, tagged unions without heap pointers) passed by value |
| HTTP parser correctness | Bundle llhttp (from Node.js) or write minimal HTTP/1.1 parser (~500 lines) |
| Proof verification depth | Structural checks only. Value comes from *requiring* proof thinking, not formal verification |
| Python compiler perf | Acceptable for POC. The gcc step dominates wall-clock time |
| Verb-dispatched resolution complexity | v0.1: require explicit verb at call site when ambiguous. Context-aware resolution deferred to v0.2 |
| Indentation parsing | Use indent/dedent tokens (like Python). Hand-written lexer tracks indent stack |
