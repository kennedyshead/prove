#!/usr/bin/env bash
set -euo pipefail

# Prove workspace development environment setup
# Run this script to install all dependencies needed for development.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WORKSPACE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "==> Setting up Prove development environment..."

# --- System packages ---

SUDO=""
if [ "$(id -u)" -ne 0 ] && command -v sudo &>/dev/null; then
    SUDO="sudo"
fi

install_system_packages() {
    if command -v apt-get &>/dev/null; then
        echo "==> Installing system packages (apt)..."
        $SUDO apt-get update -qq
        $SUDO apt-get install -y -qq \
            build-essential \
            gcc \
            make \
            python3 \
            python3-pip \
            python3-venv \
            git
    elif command -v pacman &>/dev/null; then
        echo "==> Installing system packages (pacman)..."
        $SUDO pacman -S --needed --noconfirm \
            base-devel \
            gcc \
            make \
            python \
            python-pip \
            git
    elif command -v dnf &>/dev/null; then
        echo "==> Installing system packages (dnf)..."
        $SUDO dnf install -y \
            gcc \
            make \
            python3 \
            python3-pip \
            git
    elif command -v brew &>/dev/null; then
        echo "==> Installing system packages (brew)..."
        brew install gcc make python3 git
    else
        echo "Warning: Unknown package manager. Install manually: gcc, make, python3, pip, git"
    fi
}

# Check for required system tools
MISSING=()
command -v gcc &>/dev/null || command -v clang &>/dev/null || MISSING+=(c-compiler)
command -v make &>/dev/null || MISSING+=(make)
command -v python3 &>/dev/null || MISSING+=(python3)
command -v pip3 &>/dev/null || command -v pip &>/dev/null || MISSING+=(pip)
command -v git &>/dev/null || MISSING+=(git)

if [ ${#MISSING[@]} -gt 0 ]; then
    echo "==> Missing system tools: ${MISSING[*]}"
    install_system_packages
fi

# --- Determine pip flags ---

PIP_FLAGS=()
# Use --break-system-packages if needed (PEP 668 externally-managed environments)
if pip3 install --help 2>/dev/null | grep -q "break-system-packages"; then
    # Check if we're in a venv already
    if [ -z "${VIRTUAL_ENV:-}" ]; then
        PIP_FLAGS+=(--break-system-packages)
    fi
fi

# --- Bootstrap compiler (prove-py) ---

echo "==> Installing Prove bootstrap compiler (prove-py) in dev mode..."
pip3 install -e "$WORKSPACE_DIR/prove-py[dev]" "${PIP_FLAGS[@]}"

# --- Pygments lexer (needed for docs) ---

echo "==> Installing pygments-prove lexer..."
pip3 install -e "$WORKSPACE_DIR/pygments-prove" "${PIP_FLAGS[@]}"

# --- MkDocs + Material theme (docs) ---

echo "==> Installing MkDocs and extensions..."
pip3 install "${PIP_FLAGS[@]}" \
    mkdocs \
    mkdocs-material \
    pymdown-extensions

# --- Tree-sitter grammar (optional, needs node) ---

if command -v node &>/dev/null && command -v npm &>/dev/null; then
    echo "==> Installing tree-sitter-prove dependencies..."
    (cd "$WORKSPACE_DIR/tree-sitter-prove" && npm install)
else
    echo "==> Skipping tree-sitter-prove (node/npm not found — optional)"
fi

# --- Verify ---

echo ""
echo "==> Verifying installation..."

ERRORS=0

python3 -c "import prove" 2>/dev/null && echo "  prove-py ........... OK" || { echo "  prove-py ........... FAIL"; ERRORS=$((ERRORS+1)); }
command -v prove &>/dev/null && echo "  prove CLI .......... OK" || { echo "  prove CLI .......... FAIL"; ERRORS=$((ERRORS+1)); }
python3 -c "import pygments_prove" 2>/dev/null && echo "  pygments-prove ..... OK" || { echo "  pygments-prove ..... FAIL"; ERRORS=$((ERRORS+1)); }
command -v mkdocs &>/dev/null && echo "  mkdocs ............. OK" || { echo "  mkdocs ............. FAIL"; ERRORS=$((ERRORS+1)); }
command -v ruff &>/dev/null && echo "  ruff ............... OK" || { echo "  ruff ............... FAIL"; ERRORS=$((ERRORS+1)); }
command -v mypy &>/dev/null && echo "  mypy ............... OK" || { echo "  mypy ............... FAIL"; ERRORS=$((ERRORS+1)); }
command -v pytest &>/dev/null && echo "  pytest ............. OK" || { echo "  pytest ............. FAIL"; ERRORS=$((ERRORS+1)); }
(command -v gcc &>/dev/null || command -v clang &>/dev/null) && echo "  C compiler ......... OK" || { echo "  C compiler ......... FAIL (needed for prove build)"; ERRORS=$((ERRORS+1)); }

echo ""
if [ "$ERRORS" -eq 0 ]; then
    echo "==> All dependencies installed successfully!"
else
    echo "==> WARNING: $ERRORS dependency check(s) failed. See above."
fi
