#!/usr/bin/env bash
# Sync tree-sitter-prove after grammar.js changes.
#
# This is the ONE script to run when grammar.js is modified. It:
#   1. Regenerates parser.c/scanner.c from grammar.js
#   2. Vendors parser.c + scanner.c into prove-py runtime (for C runtime / Prove module)
#   3. Rebuilds the Python wheel (for Python compiler's CST converter)
#   4. Checks ABI compatibility between vendored parser and system libtree-sitter
#
# Usage:
#   ./scripts/sync_tree_sitter.sh            # full sync
#   ./scripts/sync_tree_sitter.sh --no-generate  # skip tree-sitter generate (parser.c already up to date)
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TS_DIR="$REPO_ROOT/tree-sitter-prove"
VENDOR_DEST="$REPO_ROOT/prove-py/src/prove/runtime/vendor/tree_sitter_prove"
WHEEL_DEST="$REPO_ROOT/prove-py/vendor"

NO_GENERATE=false
for arg in "$@"; do
    case "$arg" in
        --no-generate) NO_GENERATE=true ;;
    esac
done

# ── Step 1: Regenerate parser from grammar.js ────────────────

if [ "$NO_GENERATE" = false ]; then
    echo "==> Regenerating parser from grammar.js..."
    if ! command -v tree-sitter &>/dev/null; then
        echo "ERROR: tree-sitter CLI not found. Install it:"
        echo "  brew install tree-sitter   # macOS"
        echo "  npm install -g tree-sitter-cli  # any platform"
        exit 1
    fi
    (cd "$TS_DIR" && tree-sitter generate --no-bindings)
    echo "    parser.c regenerated"
fi

# ── Step 2: Vendor parser.c + scanner.c into C runtime ──────

echo "==> Vendoring parser into prove-py runtime..."
mkdir -p "$VENDOR_DEST/tree_sitter"
cp "$TS_DIR/src/parser.c"              "$VENDOR_DEST/"
cp "$TS_DIR/src/scanner.c"             "$VENDOR_DEST/"
cp "$TS_DIR/src/tree_sitter/parser.h"  "$VENDOR_DEST/tree_sitter/"
echo "    copied to $VENDOR_DEST/"

# ── Step 3: Rebuild Python wheel ────────────────────────────

echo "==> Building tree-sitter-prove Python wheel..."
if ! command -v python3 &>/dev/null; then
    echo "ERROR: python3 not found"
    exit 1
fi
(cd "$TS_DIR" && rm -rf dist/ && python3 -m build --wheel 2>&1 | tail -1)
mkdir -p "$WHEEL_DEST"
rm -f "$WHEEL_DEST"/tree_sitter_prove-*.whl
cp "$TS_DIR"/dist/tree_sitter_prove-*.whl "$WHEEL_DEST/"
echo "    wheel copied to $WHEEL_DEST/"

echo "==> Installing tree-sitter-prove wheel..."
pip3 install --force-reinstall "$TS_DIR"/dist/tree_sitter_prove-*.whl 2>&1 | tail -1

# ── Step 4: ABI version check ───────────────────────────────

echo "==> Checking ABI compatibility..."

# Extract parser ABI version from vendored parser.c
PARSER_ABI=$(grep -m1 '#define LANGUAGE_VERSION' "$VENDOR_DEST/parser.c" | grep -o '[0-9]*')

# Extract system library ABI version from tree_sitter/api.h via pkg-config
SYS_ABI=""
if command -v pkg-config &>/dev/null; then
    TS_INCLUDE=$(pkg-config --variable=includedir tree-sitter 2>/dev/null || true)
    if [ -n "$TS_INCLUDE" ] && [ -f "$TS_INCLUDE/tree_sitter/api.h" ]; then
        SYS_ABI=$(grep -m1 'TREE_SITTER_LANGUAGE_VERSION' "$TS_INCLUDE/tree_sitter/api.h" | grep -o '[0-9]*')
    fi
fi

# Fallback: check common header locations
if [ -z "$SYS_ABI" ]; then
    for hdr in /opt/homebrew/include/tree_sitter/api.h /usr/include/tree_sitter/api.h /usr/local/include/tree_sitter/api.h; do
        if [ -f "$hdr" ]; then
            SYS_ABI=$(grep -m1 'TREE_SITTER_LANGUAGE_VERSION' "$hdr" | grep -o '[0-9]*')
            break
        fi
    done
fi

if [ -z "$SYS_ABI" ]; then
    echo "    WARNING: Could not determine system tree-sitter ABI version."
    echo "    Make sure tree-sitter is installed: brew install tree-sitter"
elif [ "$PARSER_ABI" != "$SYS_ABI" ]; then
    # Check min compatible version
    SYS_MIN=""
    for hdr in "$TS_INCLUDE/tree_sitter/api.h" /opt/homebrew/include/tree_sitter/api.h /usr/include/tree_sitter/api.h /usr/local/include/tree_sitter/api.h; do
        if [ -f "$hdr" ]; then
            SYS_MIN=$(grep -m1 'TREE_SITTER_MIN_COMPATIBLE_LANGUAGE_VERSION' "$hdr" | grep -o '[0-9]*')
            break
        fi
    done
    if [ -n "$SYS_MIN" ] && [ "$PARSER_ABI" -ge "$SYS_MIN" ] && [ "$PARSER_ABI" -le "$SYS_ABI" ]; then
        echo "    OK: parser ABI $PARSER_ABI is within system range [$SYS_MIN, $SYS_ABI]"
    else
        echo "    ERROR: ABI mismatch! Parser: $PARSER_ABI, System library: $SYS_ABI (min: ${SYS_MIN:-?})"
        echo "    Update system tree-sitter: brew upgrade tree-sitter"
        exit 1
    fi
else
    echo "    OK: parser ABI $PARSER_ABI matches system library"
fi

# ── Step 5: Sync keyword lists to Chroma & Pygments lexers ──

echo "==> Syncing keyword lists to lexers..."
python3 "$REPO_ROOT/scripts/sync_lexers.py"

echo ""
echo "==> Tree-sitter sync complete."
echo "    Remember to run: pip install -e prove-py && python scripts/test_e2e.py"
