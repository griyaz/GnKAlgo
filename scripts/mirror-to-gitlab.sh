#!/usr/bin/env bash
# Mirror full GnKAlgo repo from GitHub to GitLab (all branches + tags).
set -euo pipefail

GITLAB_REPO="${GITLAB_REPO:-git@gitlab.com:gnk-algo-trade-group/gnk-algo-trade-project.git}"
GITHUB_REPO="${GITHUB_REPO:-git@github.com:griyaz/GnKAlgo.git}"
WORKDIR="${WORKDIR:-/tmp/gnkalgo-mirror-$$}"

echo "==> Mirror: $GITHUB_REPO -> $GITLAB_REPO"
echo "==> Workdir: $WORKDIR"

rm -rf "$WORKDIR"
git clone --mirror "$GITHUB_REPO" "$WORKDIR"
cd "$WORKDIR"

echo "==> Pushing all branches and tags to GitLab..."
git push --mirror "$GITLAB_REPO"

echo "==> Done. GitLab: https://gitlab.com/gnk-algo-trade-group/gnk-algo-trade-project"
