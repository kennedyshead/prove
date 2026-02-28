#!/usr/bin/env bash
set -euo pipefail

SITE_DIR="/tmp/prove-site-deploy"
BRANCH="gitea-pages"
REPO_DIR="$(cd "$(dirname "$0")" && pwd)"

cd "$REPO_DIR"

# Ensure we're on main
current_branch=$(git branch --show-current)
if [ "$current_branch" != "main" ]; then
    echo "Error: must be on main branch (currently on '$current_branch')"
    exit 1
fi

echo "==> Installing pygments-prove lexer..."
pip install -e pygments-prove --quiet

echo "==> Building MkDocs site from main..."
mkdocs build --clean -d "$SITE_DIR"

echo "==> Preparing $BRANCH branch..."
# Create a temporary worktree for the pages branch
WORK_DIR=$(mktemp -d)
trap 'rm -rf "$WORK_DIR" "$SITE_DIR"' EXIT

git worktree add "$WORK_DIR" "$BRANCH" 2>/dev/null || {
    # Branch doesn't exist locally yet, create it as orphan
    git worktree add --detach "$WORK_DIR"
    git -C "$WORK_DIR" checkout --orphan "$BRANCH"
}

# Clear everything in the worktree (except .git)
find "$WORK_DIR" -mindepth 1 -maxdepth 1 ! -name '.git' -exec rm -rf {} +

# Copy built site into the worktree
cp -r "$SITE_DIR"/. "$WORK_DIR"/

# Add a .nojekyll for GitHub Pages
touch "$WORK_DIR/.nojekyll"

echo "==> Committing..."
git -C "$WORK_DIR" add -A
if git -C "$WORK_DIR" diff --cached --quiet; then
    echo "No changes to deploy."
else
    git -C "$WORK_DIR" commit -m "Deploy docs from main ($(git rev-parse --short HEAD))"

    echo "==> Pushing to origin/$BRANCH..."
    git -C "$WORK_DIR" push origin "$BRANCH"

    echo "==> Pushing to github/$BRANCH..."
    git -C "$WORK_DIR" push github "$BRANCH" || echo "Warning: github push failed (non-fatal)"
fi

# Clean up worktree
git worktree remove "$WORK_DIR" --force 2>/dev/null || true

echo "==> Done! Still on main."
