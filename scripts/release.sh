#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# ── Usage ────────────────────────────────────────────────────────────
usage() {
  echo "Usage: $0 <version>"
  echo "  e.g. $0 1.3.1"
  exit 1
}

[ $# -eq 1 ] || usage

VERSION="${1#v}"          # strip leading v if present
TAG="v${VERSION}"

# ── Preflight ────────────────────────────────────────────────────────
if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "ERROR: working tree is dirty — commit or stash first." >&2
  exit 1
fi

if git rev-parse "$TAG" >/dev/null 2>&1; then
  echo "ERROR: tag $TAG already exists." >&2
  exit 1
fi

PREV_TAG=$(git tag --sort=-v:refname | head -1)
if [ -z "$PREV_TAG" ]; then
  echo "ERROR: no previous tags found." >&2
  exit 1
fi

echo "Releasing $TAG  (previous: $PREV_TAG)"
echo ""

# ── Generate changelog entry from commits ────────────────────────────
MONTH=$(date +"%B %Y")
FEATURES=""
FIXES=""
OTHER=""

while IFS= read -r MSG; do
  case "$MSG" in
    feat:*|feat\(*|add:*|Add\ *|add\ *)
      FEATURES="${FEATURES}- ${MSG}\n" ;;
    fix:*|fix\(*|Fix\ *|fix\ *|Bugfix*)
      FIXES="${FIXES}- ${MSG}\n" ;;
    *)
      OTHER="${OTHER}- ${MSG}\n" ;;
  esac
done < <(git log "${PREV_TAG}..HEAD" --pretty=format:"%s" --no-merges)

ENTRY="## ${TAG} — ${MONTH}"$'\n\n'
if [ -n "$FEATURES" ]; then
  ENTRY+="### Features"$'\n\n'
  ENTRY+="$(printf '%b' "$FEATURES")"$'\n\n'
fi
if [ -n "$FIXES" ]; then
  ENTRY+="### Fixes"$'\n\n'
  ENTRY+="$(printf '%b' "$FIXES")"$'\n\n'
fi
if [ -n "$OTHER" ]; then
  ENTRY+="### Other"$'\n\n'
  ENTRY+="$(printf '%b' "$OTHER")"$'\n\n'
fi

# ── Prepend to CHANGELOG.md ─────────────────────────────────────────
CHANGELOG="${REPO_ROOT}/CHANGELOG.md"

if [ -f "$CHANGELOG" ]; then
  # Insert after the "# Changelog" header line
  EXISTING=$(tail -n +2 "$CHANGELOG")   # everything after first line
  {
    echo "# Changelog"
    echo ""
    printf '%s' "$ENTRY"
    echo "---"
    echo ""
    echo "$EXISTING"
  } > "$CHANGELOG"
else
  {
    echo "# Changelog"
    echo ""
    printf '%s' "$ENTRY"
  } > "$CHANGELOG"
fi

# ── Open editor for review ──────────────────────────────────────────
EDITOR="${EDITOR:-${VISUAL:-vi}}"
echo "Opening $CHANGELOG in $EDITOR for review..."
"$EDITOR" "$CHANGELOG"

# ── Bump version in all 3 places ────────────────────────────────────
PYPROJECT="${REPO_ROOT}/prove-py/pyproject.toml"
INIT_PY="${REPO_ROOT}/prove-py/src/prove/__init__.py"
PROVE_TOML="${REPO_ROOT}/proof/prove.toml"

sed -i.bak "s/^version = \".*\"/version = \"${VERSION}\"/" "$PYPROJECT"
rm -f "${PYPROJECT}.bak"

sed -i.bak "s/^__version__ = \".*\"/__version__ = \"${VERSION}\"/" "$INIT_PY"
rm -f "${INIT_PY}.bak"

sed -i.bak "s/^version = \".*\"/version = \"${VERSION}\"/" "$PROVE_TOML"
rm -f "${PROVE_TOML}.bak"

echo ""
echo "Version bumped to ${VERSION} in:"
echo "  $PYPROJECT"
echo "  $INIT_PY"
echo "  $PROVE_TOML"

# ── Commit and tag ──────────────────────────────────────────────────
git add "$CHANGELOG" "$PYPROJECT" "$INIT_PY" "$PROVE_TOML"
git commit -m "Release ${TAG}"
git tag "$TAG"

echo ""
echo "Created commit and tag ${TAG}."
echo ""
echo "To publish:"
echo "  git push && git push --tags"
