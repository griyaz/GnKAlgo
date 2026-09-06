#!/usr/bin/env bash
# GnKAlgo — connect a trading broker account without copy-pasting session tokens.
#
# Logs in to the GnKAlgo API, grabs the Bearer access token from the login
# response, and calls POST /api/v1/brokers/connect. Using the Bearer header means
# no cookie/CSRF juggling is required.
#
# Usage:
#   ./scripts/connect-broker.sh
#   BASE_URL=https://www.gnkalgo.com BROKER=dhan ./scripts/connect-broker.sh
#
# Environment overrides (all optional — the script prompts for anything missing):
#   BASE_URL   API base, default https://www.gnkalgo.com
#   EMAIL      login email
#   PASSWORD   login password
#   BROKER     dhan | groww | fyers | upstox
#   CLIENT_ID  broker client/app id (Dhan, FYERS)
#   TOKEN      broker access token
set -euo pipefail

BASE_URL="${BASE_URL:-https://www.gnkalgo.com}"

need() { command -v "$1" >/dev/null 2>&1 || { echo "Error: '$1' is required." >&2; exit 1; }; }
need curl
need python3   # used only for JSON parsing (stdlib, no extra deps)

prompt() { # prompt VAR "label" [silent]
  local __var="$1" __label="$2" __silent="${3:-}" __val=""
  if [[ -n "${!__var:-}" ]]; then return; fi
  if [[ "$__silent" == "silent" ]]; then
    read -r -s -p "$__label: " __val; echo
  else
    read -r -p "$__label: " __val
  fi
  printf -v "$__var" '%s' "$__val"
}

json_get() { python3 -c 'import sys,json; print(json.load(sys.stdin).get(sys.argv[1],""))' "$1"; }

prompt EMAIL "GnKAlgo email"
prompt PASSWORD "GnKAlgo password" silent

echo "==> Logging in to $BASE_URL ..."
login_resp="$(curl -fsS -X POST "$BASE_URL/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d "$(python3 -c 'import json,os;print(json.dumps({"email":os.environ["EMAIL"],"password":os.environ["PASSWORD"]}))')")"

TOKEN_JWT="$(printf '%s' "$login_resp" | json_get access_token)"
if [[ -z "$TOKEN_JWT" ]]; then
  echo "Login failed (no access_token in response):" >&2
  echo "$login_resp" >&2
  exit 1
fi
echo "==> Logged in."

prompt BROKER "Broker (dhan | groww | fyers | upstox)"
case "$BROKER" in dhan|groww|fyers|upstox) ;; *) echo "Unsupported broker: $BROKER" >&2; exit 1;; esac

# FYERS and Dhan use a client/app id in addition to the token.
if [[ "$BROKER" == "dhan" || "$BROKER" == "fyers" ]]; then
  prompt CLIENT_ID "$BROKER client/app id"
fi
prompt TOKEN "$BROKER access token" silent

payload="$(CLIENT_ID="${CLIENT_ID:-}" BROKER="$BROKER" TOKEN="$TOKEN" python3 - <<'PY'
import json, os
body = {"broker": os.environ["BROKER"], "access_token": os.environ["TOKEN"]}
cid = os.environ.get("CLIENT_ID")
if cid:
    body["client_id"] = cid
print(json.dumps(body))
PY
)"

echo "==> Connecting $BROKER ..."
resp="$(curl -sS -w '\n%{http_code}' -X POST "$BASE_URL/api/v1/brokers/connect" \
  -H "Authorization: Bearer $TOKEN_JWT" \
  -H "Content-Type: application/json" \
  -d "$payload")"

code="$(printf '%s' "$resp" | tail -n1)"
body="$(printf '%s' "$resp" | sed '$d')"

if [[ "$code" == "200" || "$code" == "201" ]]; then
  echo "==> Connected. Broker status:"
  printf '%s\n' "$body"
else
  echo "==> Connect failed (HTTP $code):" >&2
  printf '%s\n' "$body" >&2
  exit 1
fi
