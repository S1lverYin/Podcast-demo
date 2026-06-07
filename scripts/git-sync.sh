#!/usr/bin/env bash
# git-sync.sh — Auto stage, commit, and push changes for VoiceScribe WebUI
set -euo pipefail

cd "$(dirname "$0")/.."

# Stage everything (respects .gitignore)
git add -A

# If nothing to commit, exit cleanly
if git diff --cached --quiet; then
  echo "[git-sync] Nothing to commit"
  exit 0
fi

# Build a sensible auto-commit message from changed files
changed=$(git diff --cached --name-only | head -20)
if [ "$(echo "$changed" | wc -l)" -gt 20 ]; then
  summary="$(echo "$changed" | head -5 | tr '\n' ' ') ... and more"
else
  summary=$(echo "$changed" | tr '\n' ' ')
fi

git commit -m "auto: ${summary}" -m "Co-Authored-By: Claude <noreply@anthropic.com>"

# Push
git push 2>&1 || echo "[git-sync] Push failed (network or auth issue — changes committed locally)"

echo "[git-sync] Done"
