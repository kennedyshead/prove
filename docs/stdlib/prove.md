---
title: Prove - Prove Standard Library
description: Parse and traverse Prove source code syntax trees in the Prove standard library.
keywords: Prove AST, syntax tree, tree-sitter, source analysis, metaprogramming
---

# Prove

**Module:** `Prove` — syntax tree access for Prove source code.

Parse `.prv` source with `Parse.tree()`, then traverse nodes with `Prove` accessors. Backed by [tree-sitter](https://tree-sitter.github.io/) for fast, incremental parsing.

### Dependencies

The Prove module requires the `tree-sitter` C library installed on your system:

| Platform | Install command |
|----------|----------------|
| macOS (Homebrew) | `brew install tree-sitter` |
| Debian/Ubuntu | `apt install libtree-sitter-dev` |
| Fedora | `dnf install tree-sitter-devel` |
| Arch Linux | `pacman -S tree-sitter` |

Or run `./scripts/dev-setup.sh` which installs all dependencies automatically.

## Types

| Type | Description |
|------|-------------|
| `Tree` | A parsed syntax tree holding all nodes and source text (binary, opaque) |
| `Node` | A node in the syntax tree (binary, opaque) |

## Parsing (in Parse module)

Use `Parse.tree()` to parse source into a tree and `Types.string(tree)` to extract the source back.

| Verb | Signature | Description |
|------|-----------|-------------|
| `creates` | `tree(source String) Result<Value<Tree>, Error>` | Parse Prove source into a syntax tree |
| `creates` | `string(tree Tree) String` | Extract the full source text from a tree |

## Tree Accessors

| Verb | Signature | Description |
|------|-----------|-------------|
| `derives` | `root(tree Tree) Node` | Root node of a parsed tree |

## Node Accessors

| Verb | Signature | Description |
|------|-----------|-------------|
| `creates` | `kind(node Node) String` | Node kind name (e.g. `"function_definition"`, `"call_expression"`) |
| `creates` | `string(node Node) String` | Source text spanned by a node |
| `creates` | `children(node Node) List<Node>` | All child nodes (including anonymous tokens like punctuation) |
| `creates` | `child(node Node, name String) Option<Node>` | Named child by field name; returns `None` if the field does not exist |
| `creates` | `named_children(node Node) List<Node>` | Named children only (skipping anonymous tokens) |
| `creates` | `count(node Node) Integer` | Number of child nodes |
| `creates` | `line(node Node) Integer` | Line number (1-based) |
| `creates` | `column(node Node) Integer` | Column number (0-based) |
| `validates` | `error(node Node)` | Whether the node represents a syntax error |

## Common Node Kinds

Tree-sitter node kind names correspond to grammar rules. Common kinds:

| Kind | Description |
|------|-------------|
| `source_file` | Root node of any `.prv` file |
| `module_declaration` | `module Name` and its contents |
| `function_definition` | A function with verb, name, params, and body |
| `main_definition` | The `main()` entry point |
| `type_definition` | A `type Name is ...` declaration |
| `import_declaration` | A `Module verb name` import line |
| `variable_declaration` | `name as Type = value` |
| `match_expression` | A `match` branch |
| `call_expression` | A function call |
| `binary_expression` | An operator expression (`+`, `-`, `==`, etc.) |
| `string_literal` | A string value |
| `integer_literal` | An integer value |

## Example

```prove
module Main
  System outputs console
  Parse creates tree
  Prove derives root child creates kind string children named_children count line column

/// Print node kinds at each level
outputs walk(node Node, depth Integer)
from
    indent as String = ""
    i as Integer = 0
    match i < depth
        true =>
            indent = indent + "  "
            i = i + 1
        false => Unit
    console(indent + kind(node))
    match count(node) > 0
        true =>
            each(children(node), walk(_, depth + 1))
        false => Unit

main() Result<Unit, Error>!
from
    source as String = "module Hello\n\nmain()\nfrom\n    console(\"Hi\")\n"
    t = tree(source)!
    walk(root(t), 0)
```

Output:

```
source_file
  module_declaration
    identifier
    main_definition
      from_block
        call_expression
          identifier
          string_literal
```
