#!/usr/bin/env bash
# Push the current feature branch to GitHub (run from a machine with GitHub access).
set -euo pipefail

BRANCH="${BRANCH:-main}"
REMOTE="${REMOTE:-origin}"

cd "$(git rev-parse --show-toplevel)"

echo "==> Pushing ${BRANCH} to ${REMOTE}"
git push -u "${REMOTE}" "${BRANCH}"

echo "==> PR compare:"
echo "https://github.com/griyaz/GnKAlgo/compare/main...${BRANCH}?expand=1"
