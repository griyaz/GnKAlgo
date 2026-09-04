#!/usr/bin/env bash
# Merge a git bundle into an existing GnKAlgo repo (e.g. /opt/gnkalgo on Oracle VM).
set -euo pipefail

BUNDLE="${1:?Usage: sync-from-bundle.sh /path/to/gnkalgo-platform.bundle}"
BRANCH="${BRANCH:-main}"
REPO_DIR="${REPO_DIR:-$(git rev-parse --show-toplevel)}"

if [[ ! -f "$BUNDLE" ]]; then
  echo "Bundle not found: $BUNDLE" >&2
  exit 1
fi

cd "$REPO_DIR"
echo "==> Repo: $REPO_DIR"
echo "==> Bundle: $BUNDLE"
echo "==> Before: $(git rev-parse --short HEAD) ($(git log -1 --format=%s))"

git fetch "$BUNDLE" "$BRANCH"
git checkout "$BRANCH"
git merge FETCH_HEAD -m "Sync commits from Cloud Agent bundle"

echo "==> After:  $(git rev-parse --short HEAD) ($(git log -1 --format=%s))"
echo "==> Push:   export GH_TOKEN=... && git push origin $BRANCH"
