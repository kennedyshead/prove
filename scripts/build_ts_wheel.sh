#!/usr/bin/env bash
# Build tree-sitter-prove Python wheel and install it.
# Run from the repo root when grammar.js changes.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TS_DIR="$REPO_ROOT/tree-sitter-prove"
VENDOR_DIR="$REPO_ROOT/prove-py/vendor"

echo "Building tree-sitter-prove wheel..."
cd "$TS_DIR"
rm -rf dist/
python -m build --wheel 2>&1

mkdir -p "$VENDOR_DIR"
rm -f "$VENDOR_DIR"/tree_sitter_prove-*.whl
cp dist/tree_sitter_prove-*.whl "$VENDOR_DIR/"

echo "Installing tree-sitter-prove..."
pip install --force-reinstall dist/tree_sitter_prove-*.whl 2>&1

echo "Done. Wheel copied to $VENDOR_DIR/"
