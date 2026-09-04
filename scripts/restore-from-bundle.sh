#!/usr/bin/env bash
# Restore GnKAlgo from a git bundle and optionally push to GitHub.
set -euo pipefail

BUNDLE="${1:-artifacts/gnkalgo-platform.bundle}"
TARGET_DIR="${2:-gnkalgo-restore}"
BRANCH="${BRANCH:-main}"
REMOTE="${REMOTE:-https://github.com/griyaz/GnKAlgo.git}"

if [[ ! -f "$BUNDLE" ]]; then
  echo "Bundle not found: $BUNDLE" >&2
  exit 1
fi

rm -rf "$TARGET_DIR"
git clone "$BUNDLE" "$TARGET_DIR"
cd "$TARGET_DIR"
git checkout "$BRANCH"
git remote add origin "$REMOTE" 2>/dev/null || git remote set-url origin "$REMOTE"

echo "==> Restored branch ${BRANCH} in $(pwd)"
echo "==> Push with: git push -u origin ${BRANCH}"
