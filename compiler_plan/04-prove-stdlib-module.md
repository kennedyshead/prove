# Phase 4: Prove Stdlib Module

## Goal

A stdlib module called `Prove` that lets Prove programs parse, inspect, and
traverse `.prv` source code. Backed by tree-sitter's C library — no new
parser, just wrappers around the unified grammar.

**Can proceed in parallel with Phase 2** after Phase 1 is complete. This phase
is purely C runtime + stdlib registration work — it doesn't need the Python
compiler to use tree-sitter itself.

## Design

### Module Name: `Prove`

### Types

```
module Prove

type Node is binary
type Tree is binary
```

Both are opaque C types wrapping tree-sitter's C structures.

**Important:** `TSNode` in tree-sitter is a **24-byte value type** (contains
tree pointer, node ID, byte offset), not a pointer. It must be wrapped in a
heap-allocated struct to serve as a Prove binary type:

```c
typedef struct {
    TSTree *tree;   // back-pointer for lifetime safety
    TSNode node;    // 24-byte value copy
} Prove_Node_Impl;

typedef Prove_Node_Impl* Prove_Node;
typedef TSTree* Prove_Tree;
```

**Tree lifetime:** `TSTree` must outlive all `TSNode`s derived from it. The
`Prove_Node_Impl` holds a back-pointer to the tree. `Prove_Tree` itself is
reference-counted via the runtime's region system — as long as any `Node`
exists, the tree stays alive.

### Functions in Prove Module

```
/// Root node of a parsed tree
reads root(tree Tree) Node

/// Node kind name (e.g. "function_definition", "call_expression")
reads kind(node Node) String

/// Source text of a node
reads string(node Node) String

/// Child nodes
reads children(node Node) List<Node>

/// Named child by field name
reads child(node Node, name String) Option<Node>

/// Line number (1-based)
reads line(node Node) Integer

/// Column number (0-based)
reads column(node Node) Integer

/// Whether the node represents a syntax error
validates error(node Node) Boolean

/// Number of children
reads count(node Node) Integer

/// Named children only (skipping anonymous tokens)
reads named_children(node Node) List<Node>
```

### Parse Function in Parse Module

```
/// Parse Prove source into an AST
creates tree(source String) Result<Tree>
```

This lives in `Parse`, not `Prove`, because parsing is Parse's responsibility.
It returns `Result<Tree>` because parsing can fail with syntax errors (null
tree from tree-sitter). Partial parses with error nodes still return Ok —
the caller checks individual nodes with `Prove.error()`.

**Name collision check:** The Parse module does not currently have a `tree`
function. No conflict.

## Implementation Steps

### 4.1 C Runtime: tree-sitter wrapper

**New files:**
- `prove-py/src/prove/runtime/prove_prove.h`
- `prove-py/src/prove/runtime/prove_prove.c`

```c
#include <tree_sitter/api.h>

// Forward declare the tree-sitter-prove language function
const TSLanguage *tree_sitter_prove(void);

// Opaque types
typedef TSTree* Prove_Tree;
typedef struct {
    TSTree *tree;
    TSNode node;
    const char *source;     // source text pointer (owned by tree)
    uint32_t source_len;
} Prove_Node_Impl;
typedef Prove_Node_Impl* Prove_Node;

// Parse (lives in prove_prove.c but registered under Parse module)
Prove_Result prove_parse_tree(Prove_String *source);

// Tree accessors
Prove_Node prove_prove_root(Prove_Tree tree);

// Node accessors
Prove_String* prove_prove_kind(Prove_Node node);
Prove_String* prove_prove_string(Prove_Node node);
Prove_List* prove_prove_children(Prove_Node node);
Prove_Option prove_prove_child(Prove_Node node, Prove_String *name);
int64_t prove_prove_line(Prove_Node node);
int64_t prove_prove_column(Prove_Node node);
bool prove_prove_error(Prove_Node node);
int64_t prove_prove_count(Prove_Node node);
Prove_List* prove_prove_named_children(Prove_Node node);
```

### 4.2 Vendor tree-sitter source

**Strategy:** Vendor C source files into `prove-py/src/prove/runtime/vendor/`:

1. **tree-sitter core:** `tree_sitter/lib.c` — the tree-sitter amalgamation.
   tree-sitter doesn't ship an official amalgamation, but the source is in
   `lib/src/lib.c` (which includes all other `.c` files). Copy this file plus
   the required headers.
2. **tree-sitter-prove parser:** `parser.c` (1.4MB, generated) + `scanner.c`
   from `tree-sitter-prove/src/`. These are already generated artifacts.

**Compile flow in builder.py:** When a module imports `Prove`, compile the
vendored C files alongside `prove_prove.c`. No external library needed —
fully self-contained.

**Update script:** `scripts/vendor_tree_sitter.sh` — copies the latest
tree-sitter core + generated parser.c/scanner.c into vendor/. Run when
grammar.js changes or tree-sitter is updated.

**Future fallback (not implemented now):** A future enhancement could add
`pkg_config="tree-sitter"` support to use a system-installed tree-sitter
instead of vendored. This would be tracked in a `future/planned/` file if
needed.

**Files created:**
- `prove-py/src/prove/runtime/vendor/tree_sitter/` — vendored tree-sitter core
- `prove-py/src/prove/runtime/vendor/tree_sitter_prove/` — vendored parser.c + scanner.c
- `scripts/vendor_tree_sitter.sh`

### 4.3 Stdlib registration

**File:** `prove-py/src/prove/stdlib_loader.py`

Register the `Prove` module using `_register_module()`:

```python
_register_module(
    name="Prove",
    display="Prove",
    prv_file="prove.prv",
    c_map={
        ("reads", "root"): "prove_prove_root",
        ("reads", "kind"): "prove_prove_kind",
        ("reads", "string"): "prove_prove_string",
        ("reads", "children"): "prove_prove_children",
        ("reads", "child"): "prove_prove_child",
        ("reads", "line"): "prove_prove_line",
        ("reads", "column"): "prove_prove_column",
        ("validates", "error"): "prove_prove_error",
        ("reads", "count"): "prove_prove_count",
        ("reads", "named_children"): "prove_prove_named_children",
    },
    c_flags=["-Iruntime/vendor/tree_sitter"],
)
```

**File:** `prove-py/src/prove/c_runtime.py`

Add `prove_prove` to `STDLIB_RUNTIME_LIBS`:

```python
STDLIB_RUNTIME_LIBS["prove"] = {"prove_prove"}
```

Add runtime function metadata to `_RUNTIME_FUNCTIONS` for each accessor.

### 4.4 Parse module extension

Add `tree` to the Parse module registration:

**File:** `prove-py/src/prove/stdlib_loader.py` — Parse module

Add to the Parse module's `c_map`:
```python
("creates", "tree"): "prove_parse_tree",
```

**File:** `prove-py/src/prove/c_runtime.py`

Add Parse module dependency on `prove_prove`:
```python
STDLIB_RUNTIME_LIBS["parse"].add("prove_prove")
```

The C implementation:

```c
Prove_Result prove_parse_tree(Prove_String *source) {
    TSParser *parser = ts_parser_new();
    ts_parser_set_language(parser, tree_sitter_prove());
    TSTree *tree = ts_parser_parse_string(
        parser, NULL, source->data, (uint32_t)source->length);
    ts_parser_delete(parser);
    if (!tree) {
        return prove_result_error(prove_string_from("parse failed"));
    }
    return prove_result_ok_ptr(tree);
}
```

### 4.5 Stdlib .prv file

**New file:** `prove-py/src/prove/stdlib/prove.prv`

```
module Prove

/// A parsed syntax tree
type Tree is binary

/// A node in the syntax tree
type Node is binary

/// Root node of a parsed tree
reads root(tree Tree) Node
    binary

/// Node kind name (e.g. "function_definition")
reads kind(node Node) String
    binary

/// Source text of a node
reads string(node Node) String
    binary

/// Child nodes
reads children(node Node) List<Node>
    binary

/// Named child by field name
reads child(node Node, name String) Option<Node>
    binary

/// Line number (1-based)
reads line(node Node) Integer
    binary

/// Column number (0-based)
reads column(node Node) Integer
    binary

/// Whether the node represents a syntax error
validates error(node Node) Boolean
    binary

/// Number of children
reads count(node Node) Integer
    binary

/// Named children only (skipping anonymous tokens)
reads named_children(node Node) List<Node>
    binary
```

### 4.6 Tests

**New file:** `prove-py/tests/test_prove_runtime_c.py`

```python
def test_parse_and_get_root_kind(compile_and_run):
    """Parse source and verify root node kind."""
    result = compile_and_run('''
    module Main
    from Parse use tree
    from Prove use root, kind

    main
        from
            t = tree("module Test")!
            r = root(t)
            outputs kind(r)
    ''')
    assert "source_file" in result.stdout

def test_children_traversal(compile_and_run):
    """Traverse children of root node."""
    ...

def test_child_by_name(compile_and_run):
    """Named child lookup returns Option."""
    ...

def test_error_node_detection(compile_and_run):
    """Parse invalid source, detect error nodes."""
    ...

def test_node_line_and_column(compile_and_run):
    """Verify line/column accessors."""
    ...

def test_parse_failure_returns_error(compile_and_run):
    """Empty source or null returns Result error."""
    ...
```

## Dependencies

- **Phase 1 complete:** grammar.js is canonical, constants extracted
- **tree-sitter C library** available (vendored or system-installed)
- **tree-sitter-prove** built (`parser.c` + `scanner.c` generated)

Does NOT depend on Phase 2 (Python tree-sitter) or Phase 3 (recursive variants).

## Completion Criteria

- [ ] `prove_prove.c/.h` implements all accessors
- [ ] `TSNode` properly wrapped in heap-allocated struct with tree back-pointer
- [ ] tree-sitter core + parser vendored in `runtime/vendor/`
- [ ] `Prove` module registered in stdlib_loader + c_runtime
- [ ] `Parse.tree()` returns `Result<Tree>`
- [ ] E2e tests: parse → traverse → extract node kinds
- [ ] Build system compiles vendored tree-sitter automatically
- [ ] `prove.prv` stdlib file with doc comments
