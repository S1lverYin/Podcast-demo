#!/bin/bash
set -e
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_DIR"

git config user.email "s1lveryin@users.noreply.github.com"
git config user.name "S1lverYin"

if git diff --quiet && git diff --cached --quiet; then
    echo "No changes to commit."
    exit 0
fi

git add -A
git commit -m "auto: update $(date '+%Y-%m-%d %H:%M')" || echo "Nothing to commit"
git push origin main 2>&1 || echo "Push failed, will retry next time"
