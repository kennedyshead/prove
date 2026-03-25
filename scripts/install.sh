#!/bin/sh
# Prove installer — downloads the proof binary for the current platform.
#
# Usage:
#   curl -sSf https://code.botwork.se/Botwork/prove/raw/branch/main/scripts/install.sh | sh
#   curl -sSf ... | sh -s -- --version v1.1.0 --prefix /usr/local/bin
set -eu

GITEA_API="https://code.botwork.se/api/v1/repos/Botwork/prove"
GITEA_REPO="https://code.botwork.se/Botwork/prove"
VERSION=""
PREFIX="${HOME}/.local/bin"

while [ $# -gt 0 ]; do
  case "$1" in
    --version) VERSION="$2"; shift 2 ;;
    --prefix)  PREFIX="$2";  shift 2 ;;
    --help|-h)
      echo "Usage: install.sh [--version VERSION] [--prefix DIR]"
      echo "  --version   Tag to install (default: latest release)"
      echo "  --prefix    Install directory (default: ~/.local/bin)"
      exit 0 ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done

detect_platform() {
  OS=$(uname -s)
  ARCH=$(uname -m)

  case "$OS" in
    Linux)
      case "$ARCH" in
        x86_64)  echo "linux-x86_64" ;;
        aarch64) echo "linux-aarch64" ;;
        *)       echo "Unsupported architecture: $ARCH" >&2; exit 1 ;;
      esac ;;
    Darwin)
      case "$ARCH" in
        arm64)   echo "macos-aarch64" ;;
        x86_64)  echo "macos-x86_64" ;;
        *)       echo "Unsupported architecture: $ARCH" >&2; exit 1 ;;
      esac ;;
    *)
      echo "Unsupported OS: $OS" >&2; exit 1 ;;
  esac
}

PLATFORM=$(detect_platform)
echo "Detected platform: $PLATFORM"

# Resolve version
if [ -z "$VERSION" ]; then
  VERSION=$(curl -sf "${GITEA_API}/releases/latest" \
    | grep -o '"tag_name":"[^"]*"' | head -1 | cut -d'"' -f4)
  if [ -z "$VERSION" ]; then
    echo "Error: could not determine latest release." >&2
    exit 1
  fi
fi
echo "Installing proof $VERSION..."

# Download tarball
TARBALL="proof-${VERSION}-${PLATFORM}.tar.gz"
DOWNLOAD_URL="${GITEA_REPO}/releases/download/${VERSION}/${TARBALL}"

TMPDIR=$(mktemp -d)
trap 'rm -rf "$TMPDIR"' EXIT

if ! curl -sfL -o "${TMPDIR}/${TARBALL}" "$DOWNLOAD_URL"; then
  echo "Error: failed to download $DOWNLOAD_URL" >&2
  echo "No binary available for $PLATFORM at $VERSION." >&2
  exit 1
fi

# Extract and install
tar -xzf "${TMPDIR}/${TARBALL}" -C "$TMPDIR"
mkdir -p "$PREFIX"
cp "${TMPDIR}/proof" "${PREFIX}/proof"
chmod +x "${PREFIX}/proof"

echo "Installed proof to ${PREFIX}/proof"

# --- Install system dependencies needed by prove build ---

install_deps() {
  OS=$(uname -s)
  if [ "$OS" = "Darwin" ] && command -v brew >/dev/null 2>&1; then
    echo "Installing build dependencies (brew)..."
    # tree-sitter: needed for Prove module (syntax tree access)
    # sdl2: needed for Graphic module (GUI)
    brew install tree-sitter sdl2 2>/dev/null || true
  elif [ "$OS" = "Linux" ]; then
    if command -v apt-get >/dev/null 2>&1; then
      echo "Installing build dependencies (apt)..."
      SUDO=""
      if [ "$(id -u)" -ne 0 ] && command -v sudo >/dev/null 2>&1; then SUDO="sudo"; fi
      $SUDO apt-get install -y -qq libtree-sitter-dev libsdl2-dev 2>/dev/null || true
    elif command -v dnf >/dev/null 2>&1; then
      echo "Installing build dependencies (dnf)..."
      SUDO=""
      if [ "$(id -u)" -ne 0 ] && command -v sudo >/dev/null 2>&1; then SUDO="sudo"; fi
      $SUDO dnf install -y tree-sitter-devel SDL2-devel 2>/dev/null || true
    elif command -v pacman >/dev/null 2>&1; then
      echo "Installing build dependencies (pacman)..."
      SUDO=""
      if [ "$(id -u)" -ne 0 ] && command -v sudo >/dev/null 2>&1; then SUDO="sudo"; fi
      $SUDO pacman -S --needed --noconfirm tree-sitter sdl2 2>/dev/null || true
    fi
  fi
}

install_deps

# Verify key dependencies
if command -v pkg-config >/dev/null 2>&1; then
  pkg-config --exists tree-sitter 2>/dev/null && echo "  tree-sitter ........ OK" \
    || echo "  tree-sitter ........ MISSING (needed for Prove module: brew install tree-sitter)"
  pkg-config --exists sdl2 2>/dev/null && echo "  sdl2 ............... OK" \
    || echo "  sdl2 ............... MISSING (optional, needed for Graphic module: brew install sdl2)"
fi

# PATH hint
case ":${PATH}:" in
  *":${PREFIX}:"*) ;;
  *)
    echo ""
    echo "Add ${PREFIX} to your PATH:"
    echo "  export PATH=\"${PREFIX}:\$PATH\""
    echo ""
    echo "Or add it to your shell profile (~/.bashrc, ~/.zshrc, etc.)"
    ;;
esac
