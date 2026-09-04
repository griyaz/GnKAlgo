#!/usr/bin/env bash
# Push branch and open a draft PR to main (run where GitHub is reachable).
set -euo pipefail

BRANCH="${BRANCH:-main}"
BASE="${BASE:-main}"
REPO="${GITHUB_REPO:-griyaz/GnKAlgo}"

if [[ -z "${GH_TOKEN:-}" ]]; then
  echo "Set GH_TOKEN to a GitHub PAT with repo scope." >&2
  exit 1
fi

export GH_TOKEN
cd "$(git rev-parse --show-toplevel)"

echo "==> Push $BRANCH"
git push "https://x-access-token:${GH_TOKEN}@github.com/${REPO}.git" "${BRANCH}:${BRANCH}"

echo "==> Create draft PR"
gh pr create \
  --repo "$REPO" \
  --base "$BASE" \
  --head "$BRANCH" \
  --draft \
  --title "GnKAlgo platform upgrade: charts, market data, SMC strategies" \
  --body-file "$(dirname "$0")/pr-body-gnkalgo-platform.md"

echo "==> Done"
