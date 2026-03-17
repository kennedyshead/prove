# Row Polymorphism

**Status:** Exploring
**Roadmap:** Structural subtyping for record types

## Problem

Prove's type system uses nominal typing for records — a function accepting
`User` cannot accept `Admin` even if `Admin` has all the same fields plus more.
This limits code reuse and forces workarounds like manual field copying or
over-broad `Table` usage when functions only need a subset of fields.

## Goal

Add row polymorphism so that a function can accept any record that has (at
least) the fields it needs, without requiring the caller to name a specific
type.

```prove
// A function that works with any record having a `name` field:
transforms greeting(entity Struct) String
  contracts
    entity with
      name String
  from
    result = "Hello, " + entity.name
```

Any record with a `name String` field — `User`, `Admin`, `Contact` — satisfies
the constraint.

### Why This Syntax

- **`Struct` as type** — signals "any record" in the parameter position. No new
  bracketing or inline syntax needed. Reads naturally: "entity is a Struct".
- **`entity with` in contracts** — reuses the existing contracts block.
  Field requirements sit alongside `requires`/`ensures`, keeping the function
  signature clean and the structural constraints declarative.
- **Indented field list** — follows Prove's existing indentation patterns.
  Multiple fields are listed one per line under `with`.

Multi-field example:

```prove
transforms full_name(person Struct) String
  contracts
    person with
      first_name String
      last_name String
  from
    result = person.first_name + " " + person.last_name
```

## Current State

- `RecordType` in `types.py:36` is `{name, fields: dict[str, Type], type_params}`.
- `types_compatible()` in `types.py:296` uses nominal matching: two record types
  are compatible only when their names match.
- `AlgebraicType` follows the same nominal pattern.
- The C emitter generates concrete structs per record type — there is no
  structural dispatch at the C level today.
- The contracts block already supports `requires`, `ensures`, `know`, `assume`,
  `believe`. Adding `<param> with` is a natural extension.

## Design

### `Struct` Type

`Struct` is a new builtin type name (like `Integer`, `String`). A parameter
typed `Struct` accepts any `RecordType`. Without a `with` constraint, it
accepts any record at all. With a `with` constraint, the checker verifies
that the actual record type has the required fields.

### Contracts `with` Clause

The `with` clause is parsed inside the contracts block. Grammar:

```
contract_clause ::= requires_clause
                  | ensures_clause
                  | know_clause
                  | assume_clause
                  | believe_clause
                  | struct_with_clause

struct_with_clause ::= IDENTIFIER "with" NEWLINE INDENT field_list DEDENT
field_list         ::= (IDENTIFIER type_expr NEWLINE)+
```

The identifier must reference a parameter with type `Struct`. Each field in
the list becomes a structural requirement.

### Checker Changes

- Introduce a `StructConstraint` (or `RowConstraint`) in `types.py`
  representing the required fields for a `Struct`-typed parameter.
- When checking a call site, `types_compatible()` must accept any `RecordType`
  where `Struct` is expected, then verify the record has all fields listed
  in the `with` clause with compatible types.
- Field access inference on `Struct`-typed identifiers uses the `with`
  constraint to resolve field types.
- Error: "record `User` is missing field `age` required by struct constraint
  on parameter `entity`".

### C Emission Strategy

Two approaches:

1. **Monomorphisation** — For each concrete record type used where a `Struct`
   parameter is expected, generate a specialised version of the function that
   operates on that specific struct. The optimizer can inline these.
2. **Fat pointer / vtable** — Pass a struct pointer plus a field-offset table.
   Uniform calling convention, but adds indirection.

Approach 1 fits Prove's existing monomorphisation model better and avoids
runtime overhead.

### Interaction with Existing Features

- **Refinement types in `with`:** `entity with age Integer where > 0` should
  compose naturally — the field constraint includes a refinement.
- **Modifiers in `with`:** `entity with data String:[ASCII]` should work.
- **Match expressions:** `Struct` values cannot be matched as algebraic
  variants — they are open, not closed. This is a deliberate limitation.
- **Generics:** `List<Struct>` with constraints would need thought — likely
  deferred.
- **Multiple `Struct` params:** Each gets its own `with` clause in contracts.

## Implementation Phases

### Phase 1: Type System

- Add `Struct` to `BUILTINS` in `types.py` as a `PrimitiveType("Struct")`.
- Add `StructConstraint` dataclass: `{param_name: str, fields: dict[str, Type]}`.
- Store constraints on `FunctionDef` AST node (or in the contracts list).

### Phase 2: Parser

- Parse `<ident> with` inside the contracts block.
- Parse indented field list (name + type pairs) under `with`.
- Validate that the identifier references a `Struct`-typed parameter.

### Phase 3: Checker

- During contract checking, build `StructConstraint` for each `with` clause.
- At call sites, when actual arg is a `RecordType` and expected is `Struct`,
  verify all constraint fields are present with compatible types.
- Field access on `Struct`-typed identifiers resolves through the constraint.
- Error messages reference the specific missing field and parameter.

### Phase 4: C Emitter

- Monomorphise: for each concrete record type used where `Struct` is expected,
  generate a specialised C function operating on that struct.
- The emitter knows the concrete type at each call site, so it can emit
  direct struct field access in the specialised version.

### Phase 5: Integration

- Update formatter to emit `with` clauses in contracts.
- LSP completion for field access on `Struct`-typed parameters.
- Stdlib functions that currently take `Table` for flexibility could offer
  `Struct`-typed overloads.
- tree-sitter grammar: `with` keyword in contracts context.

## Open Questions

- Should `Struct` be allowed as a return type? (Probably not — the caller
  needs to know the concrete type to access fields.)
- Should `with` support nested structs? e.g., `entity with address Struct`
  with its own nested `with` clause.
- Can `with` constraints reference type variables for generic struct functions?
- Should unconstrained `Struct` (no `with`) be useful, or always require at
  least one field?

## Files Likely Touched

- `types.py` — `Struct` builtin, `StructConstraint` dataclass
- `ast_nodes.py` — store `with` constraints on `FunctionDef`
- `parser.py` — parse `<ident> with` + field list in contracts
- `checker.py` / `_check_contracts.py` — constraint building, call-site checking
- `_check_types.py` — field access resolution for `Struct` params
- `types_compatible()` in `types.py` — `RecordType` vs `Struct` matching
- `c_emitter.py` / `_emit_calls.py` — monomorphised call dispatch
- `_emit_types.py` — specialised function generation
- `c_types.py` — `map_type()` for `Struct`
- `formatter.py` — formatting `with` clauses
- `export.py` — tree-sitter grammar updates
