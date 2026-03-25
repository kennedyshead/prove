#!/usr/bin/env bash
# Vendor tree-sitter-prove parser + scanner into prove-py runtime.
# Tree-sitter core is linked via pkg-config (system library).
# Run when grammar.js changes.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="$REPO_ROOT/prove-py/src/prove/runtime/vendor"

# Tree-sitter-prove parser + scanner
mkdir -p "$DEST/tree_sitter_prove/tree_sitter"
cp "$REPO_ROOT/tree-sitter-prove/src/parser.c" "$DEST/tree_sitter_prove/"
cp "$REPO_ROOT/tree-sitter-prove/src/scanner.c" "$DEST/tree_sitter_prove/"
cp "$REPO_ROOT/tree-sitter-prove/src/tree_sitter/parser.h" "$DEST/tree_sitter_prove/tree_sitter/"

echo "Vendored tree-sitter-prove parser into $DEST/tree_sitter_prove/"
