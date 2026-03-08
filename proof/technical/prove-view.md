# `prove view` — Complete Flow

Step-by-step description of what happens from CLI invocation to final output.

---

## CLI Entry Point

**Command:** `prove view <file>`

| Argument | Type | Required | Description |
|----------|------|----------|-------------|
| `file` | positional | yes | Path to a `.prv` source file (must exist) |

**Source:** `cli.py` → `view()` function

---

## Step 1 — Read source

```python
source = Path(file).read_text()
filename = str(file)
```

---

## Step 2 — Lex

```python
tokens = Lexer(source, filename).lex()
```

- Tokenizes the source file
- **On `CompileError`:** renders all diagnostics to stderr → exit 1

---

## Step 3 — Parse

```python
module = Parser(tokens, filename).parse()
```

- Parses token stream into Module AST
- **On `CompileError`:** renders all diagnostics to stderr → exit 1

---

## Step 4 — Dump AST

```python
_dump_ast(module, 0)
```

### `_dump_ast(node, depth)` — recursive AST printer

The function walks the AST tree recursively:

1. **Compute indent:** `"  " * depth`
2. **Identify node type:** `type(node).__name__`
3. **If dataclass node:**
   - Print node type name at current indent
   - For each field (excluding `span`):
     - **If list:** print field name + `:`, then recursively dump each item at `depth + 2`
     - **If empty list:** print `field_name: []`
     - **If nested dataclass:** print field name + `:`, then recursively dump at `depth + 2`
     - **If other non-None value:** print `field_name: repr(value)`
4. **If non-dataclass node:** print `ClassName: repr(node)`

### Example output

For a simple module:

```prove
module Main
  narrative: """Hello"""

transforms add(a Integer, b Integer) Integer
from
    a + b
```

The view output would be:

```
Module
  declarations:
    ModuleDecl
      name: 'Main'
      narrative: 'Hello'
      imports: []
      types: []
      constants: []
      invariants: []
      body: []
      temporal: []
    FunctionDef
      verb: 'transforms'
      name: 'add'
      params:
        Param
          name: 'a'
          type_expr:
            SimpleType
              name: 'Integer'
          constraint: None
        Param
          name: 'b'
          type_expr:
            SimpleType
              name: 'Integer'
          constraint: None
      return_type:
        SimpleType
          name: 'Integer'
      can_fail: False
      binary: False
      body:
        ExprStmt
          expr:
            BinaryExpr
              op: '+'
              left:
                IdentifierExpr
                  name: 'a'
              right:
                IdentifierExpr
                  name: 'b'
      ensures: []
      requires: []
      ...
```

---

## Notes

- **No type checking is performed.** The view command only runs the lexer and parser.
- **`span` fields are excluded** from the output to reduce noise.
- **No formatting is applied.** The AST reflects the exact parse tree, not the canonical form.
- The output is purely informational — it does not modify any files.

---

## Complete Pipeline Diagram

```
prove view <file>
│
├─ Read source file
├─ Lexer.lex() → tokens
│  └─ [on error] render diagnostics → exit 1
├─ Parser.parse() → Module AST
│  └─ [on error] render diagnostics → exit 1
└─ _dump_ast(module, 0) → print tree to stdout
```

---

## File Map

| File | Role |
|------|------|
| `cli.py` | CLI entry point, `_dump_ast()` recursive printer |
| `lexer.py` | Source → token stream |
| `parser.py` | Token stream → Module AST |
| `errors.py` | Diagnostic rendering (errors only) |
| `ast_nodes.py` | AST node dataclasses (the types being dumped) |
