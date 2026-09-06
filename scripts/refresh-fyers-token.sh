#!/usr/bin/env bash
# GnKAlgo — refresh the daily FYERS market-data access token on the server.
#
# FYERS access tokens expire every trading day. This script updates
# FYERS_ACCESS_TOKEN (and optionally FYERS_CLIENT_ID) in the deployment .env,
# ensures MARKET_DATA_PROVIDER=fyers, then restarts the backend so the ticker
# reconnects with the fresh token — no manual file editing required.
#
# Usage (run from the deploy dir, e.g. /opt/gnkalgo/DEV):
#   ./scripts/refresh-fyers-token.sh <ACCESS_TOKEN> [CLIENT_ID]
#   FYERS_ACCESS_TOKEN=xxxx ./scripts/refresh-fyers-token.sh
#
# Environment overrides:
#   ENV_FILE=/opt/gnkalgo/DEV/.env
#   COMPOSE_FILE=docker-compose.prod.yml
#   RESTART=1                 # set RESTART=0 to only edit .env (no restart)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="${REPO_DIR:-$(cd "$SCRIPT_DIR/.." && pwd)}"
ENV_FILE="${ENV_FILE:-$REPO_DIR/.env}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
RESTART="${RESTART:-1}"

TOKEN="${1:-${FYERS_ACCESS_TOKEN:-}}"
CLIENT_ID="${2:-${FYERS_CLIENT_ID:-}}"

if [[ -z "$TOKEN" ]]; then
  echo "Usage: $0 <FYERS_ACCESS_TOKEN> [FYERS_CLIENT_ID]" >&2
  exit 1
fi
if [[ ! -f "$ENV_FILE" ]]; then
  echo "Env file not found: $ENV_FILE (set ENV_FILE=... or run from the deploy dir)" >&2
  exit 1
fi

# set_kv KEY VALUE — update KEY in-place if present, else append. Value is written
# literally (no shell/regex interpretation) so tokens with special chars are safe.
set_kv() {
  local key="$1" value="$2"
  if grep -qE "^${key}=" "$ENV_FILE"; then
    KEY="$key" VALUE="$value" ENV_FILE="$ENV_FILE" python3 - <<'PY'
import os
key, value, path = os.environ["KEY"], os.environ["VALUE"], os.environ["ENV_FILE"]
lines = open(path).read().splitlines()
out = [f"{key}={value}" if l.startswith(key + "=") else l for l in lines]
open(path, "w").write("\n".join(out) + "\n")
PY
  else
    printf '%s=%s\n' "$key" "$value" >> "$ENV_FILE"
  fi
}

# Back up once per run so a bad token can be rolled back.
cp "$ENV_FILE" "$ENV_FILE.bak.$(date +%Y%m%d%H%M%S)"

set_kv MARKET_DATA_PROVIDER fyers
set_kv FYERS_ACCESS_TOKEN "$TOKEN"
[[ -n "$CLIENT_ID" ]] && set_kv FYERS_CLIENT_ID "$CLIENT_ID"
echo "==> Updated FYERS token in $ENV_FILE (backup saved)."

if [[ "$RESTART" == "1" ]]; then
  if command -v docker >/dev/null 2>&1 && [[ -f "$REPO_DIR/$COMPOSE_FILE" ]]; then
    echo "==> Restarting backend to pick up the new token ..."
    docker compose -f "$REPO_DIR/$COMPOSE_FILE" up -d backend
    sleep 3
    echo "==> Market-data health:"
    curl -fsS http://127.0.0.1:8000/api/v1/market/health || echo "(health endpoint not reachable yet)"
    echo ""
  else
    echo "==> Docker/compose not found; edit applied. Restart the backend manually to apply."
  fi
else
  echo "==> RESTART=0 set; .env edited only. Restart the backend to apply."
fi
