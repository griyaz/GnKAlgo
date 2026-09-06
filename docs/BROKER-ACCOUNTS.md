# Broker accounts & operator tooling

GnKAlgo has **two independent broker integrations**. Don't confuse them:

| Concern | What it does | Where it's configured |
|---------|--------------|-----------------------|
| **Market data** (LiveMarketTicker) | Live index prices for the ticker | Backend `.env` (`MARKET_DATA_PROVIDER`, `FYERS_*`, etc.) |
| **Order execution** (trading account) | Places/modifies/cancels real orders | Per-user, in-app (encrypted in DB) |

Switching one never changes the other.

## Supported order-execution brokers

`dhan`, `groww`, `fyers`, `upstox` (see `BrokerType`). Each has a `BrokerAdapter`
implementation under `backend/app/brokers/` that normalizes orders into the shared
`OrderRequest` / `OrderResponse` model:

- `dhan.py` — DhanHQ v2 (also does historical candles + market feed elsewhere).
- `groww.py` — Groww Trading API.
- `fyers.py` — `FyersExecutionAdapter`, FYERS API v3 REST (`Authorization: {client_id}:{access_token}`).
- `upstox.py` — `UpstoxExecutionAdapter`, Upstox API v2 REST (Bearer token; orders use an `instrument_token`).

Credentials are encrypted at rest (`encrypt_data`) and never returned in API responses.

## Connect a trading account

Option 1 — UI: log in → Settings → Broker (`/settings#broker`) → pick the broker → paste
credentials → Connect. Start with paper mode.

Option 2 — helper script (no cookie/CSRF juggling; uses a Bearer token):

```bash
./scripts/connect-broker.sh
# or non-interactively:
BASE_URL=https://www.gnkalgo.com BROKER=fyers CLIENT_ID=APP1234-100 \
  EMAIL=you@example.com PASSWORD=... TOKEN=<fyers token> ./scripts/connect-broker.sh
```

Option 3 — raw API: `POST /api/v1/brokers/connect` with `Authorization: Bearer <jwt>` and
`{"broker":"fyers","client_id":"APP1234-100","access_token":"..."}`. Check status via
`GET /api/v1/brokers/connections`.

Field notes: Dhan and FYERS need `client_id` (+ `access_token`); Groww and Upstox need only
`access_token`.

## FYERS market-data daily token refresh

FYERS access tokens expire every trading day. Instead of hand-editing `.env`, run on the
server (from the deploy dir, e.g. `/opt/gnkalgo/DEV`):

```bash
./scripts/refresh-fyers-token.sh <ACCESS_TOKEN> [CLIENT_ID]
```

It backs up `.env`, sets `MARKET_DATA_PROVIDER=fyers` + `FYERS_ACCESS_TOKEN` (and
`FYERS_CLIENT_ID` if given), restarts the backend, and prints
`/api/v1/market/health`. Set `RESTART=0` to only edit `.env`.

## Upstox market-data SDK

`upstox-python-sdk` is now bundled in `backend/requirements.txt`, so
`MARKET_DATA_PROVIDER=upstox` (with `UPSTOX_MARKET_DATA_ENABLED=true`,
`UPSTOX_ACCESS_TOKEN=...`) works out of the box. The provider imports the SDK lazily.
