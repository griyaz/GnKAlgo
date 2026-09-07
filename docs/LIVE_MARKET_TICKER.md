# LiveMarketTicker — Real-time Market Ticker

A production-quality, exchange-style index ticker for the GnKAlgo dashboard.
FYERS is the primary live provider, with optional Dhan and Upstox fallbacks. The
frontend keeps **one** WebSocket to the GnKAlgo backend; the backend owns the
single upstream provider connection and fans out to browsers via Redis.

## Architecture

```
FYERS / Dhan / Upstox WebSocket        (upstream provider — backend only)
        |
        v
MarketDataManager  (app/market_data/manager.py)
  - normalizes broker packets -> Tick
  - computes market status + stale detection
  - single upstream owner via Redis leader-lock
        |
        +--> Redis latest-price cache   market:ticker:<ID>
        +--> Redis pub/sub              market:ticker:updates
        |
        v
FastAPI:  GET /api/v1/market/ticker      (snapshot)
          GET /api/v1/market/health      (health)
          WS  /ws/market/ticker          (snapshot + live fan-out)
        |
        v
Next.js:  marketTickerSocket (single shared WS)
          useMarketTicker (hook, isolated state)
          LiveMarketTicker (component, top of dashboard)
```

Only the leader worker connects upstream. Every worker can serve the WebSocket
by reading Redis and subscribing to the pub/sub channel, so you can scale to
multiple FastAPI workers without opening multiple provider connections. Without
Redis (single-worker dev) the manager owns the feed in-process and fans out via
an in-memory queue.

## Provider configuration

Set the primary provider and (optionally) enable fallbacks in `.env`
(see `.env.example`). All credentials are **backend-only** — never `NEXT_PUBLIC_*`.

```env
MARKET_DATA_PROVIDER=fyers          # fyers | upstox | dhan | mock
MARKET_DATA_FAILOVER_ENABLED=false  # only switch to an enabled fallback if true
MARKET_DATA_STALE_SECONDS=10
MARKET_DATA_MOCK_MODE=false
MARKET_DATA_CACHE_TTL_SECONDS=60
MARKET_DATA_REQUIRE_AUTH=true
MARKET_HOLIDAYS=                    # e.g. 2026-01-26,2026-03-21 (Asia/Kolkata)
MARKET_DATA_SYMBOL_OVERRIDES=       # JSON, see "Symbol mapping"
```

### FYERS setup (primary)

1. The SDK (`fyers-apiv3`) is already bundled in `backend/requirements.txt`, so
   no extra install is needed. It is imported lazily (only when
   `MARKET_DATA_PROVIDER=fyers`), so it never affects mock mode or tests.
2. Generate a v3 access token (app id + auth code flow) and set:
   ```env
   MARKET_DATA_PROVIDER=fyers
   FYERS_CLIENT_ID=XXXXXX-100
   FYERS_ACCESS_TOKEN=<v3 access token>
   ```
   `FYERS_ACCESS_TOKEN` may be the raw token (combined with `FYERS_CLIENT_ID` as
   `APPID:TOKEN` automatically) or an already-combined `APPID:TOKEN` string.
3. The provider subscribes with `data_type="SymbolUpdate"` (full mode) so
   previous-close is available directly for the change calculation. A lighter
   LTP-only "lite" mode is available in the SDK if you maintain previous-close
   separately.

### Dhan setup (optional fallback)

```env
DHAN_MARKET_DATA_ENABLED=true
DHAN_CLIENT_ID=<client id>
DHAN_ACCESS_TOKEN=<market-data token>
```

This reuses the project's existing Dhan binary feed parser
(`app/brokers/dhan_market_feed.py`) and is **separate** from Dhan order
execution — enabling it does not change the trading/execution provider.

### Upstox setup (optional fallback, V3 only)

```bash
pip install upstox-python-sdk
```
```env
UPSTOX_MARKET_DATA_ENABLED=true
UPSTOX_ACCESS_TOKEN=<token>
```

Uses `MarketDataStreamerV3` (never the deprecated V1/V2 feeds) and does not touch
existing historical-candle logic.

## Symbol mapping

All index → provider-symbol mappings live in `app/market_data/symbols.py`. The
default provider identifiers are **best-effort and must be verified** against
your live account/SDK. Override any of them (do not guess) with
`MARKET_DATA_SYMBOL_OVERRIDES` (JSON):

```json
{
  "NIFTY50":     {"fyers": "NSE:NIFTY50-INDEX",     "dhan": "IDX_I:13", "upstox": "NSE_INDEX|Nifty 50"},
  "BANKNIFTY":   {"fyers": "NSE:NIFTYBANK-INDEX",   "dhan": "IDX_I:25", "upstox": "NSE_INDEX|Nifty Bank"},
  "INDIAVIX":    {"fyers": "NSE:INDIAVIX-INDEX",    "dhan": "IDX_I:21", "upstox": "NSE_INDEX|India VIX"}
}
```

| Internal id | Display | FYERS (default) | Dhan (default) | Upstox (default) |
|---|---|---|---|---|
| NIFTY50 | NIFTY 50 | `NSE:NIFTY50-INDEX` | `IDX_I:13` | `NSE_INDEX\|Nifty 50` |
| BANKNIFTY | NIFTY BANK | `NSE:NIFTYBANK-INDEX` | `IDX_I:25` | `NSE_INDEX\|Nifty Bank` |
| MIDCAP100 | NIFTY MIDCAP 100 | `NSE:NIFTYMIDCAP100-INDEX` | `IDX_I:38` | `NSE_INDEX\|NIFTY MIDCAP 100` |
| SMALLCAP100 | NIFTY SMALLCAP 100 | `NSE:NIFTYSMLCAP100-INDEX` | `IDX_I:39` | `NSE_INDEX\|NIFTY SMLCAP 100` |
| NIFTYIT | NIFTY IT | `NSE:NIFTYIT-INDEX` | `IDX_I:29` | `NSE_INDEX\|Nifty IT` |
| NIFTYAUTO | NIFTY AUTO | `NSE:NIFTYAUTO-INDEX` | `IDX_I:34` | `NSE_INDEX\|Nifty Auto` |
| NIFTYFMCG | NIFTY FMCG | `NSE:NIFTYFMCG-INDEX` | `IDX_I:31` | `NSE_INDEX\|Nifty FMCG` |
| INDIAVIX | INDIA VIX | `NSE:INDIAVIX-INDEX` | `IDX_I:21` | `NSE_INDEX\|India VIX` |

> The Dhan security ids and some FYERS/Upstox symbols above are placeholders.
> Confirm them from the Dhan instrument master / FYERS symbol master / Upstox
> instrument list and override as needed.

## Redis keys and channels

| Kind | Name | Notes |
|---|---|---|
| Cache key | `market:ticker:<INDEX_ID>` | JSON snapshot per index, TTL `MARKET_DATA_CACHE_TTL_SECONDS` |
| Meta key | `market:ticker:meta` | provider / market status / stale / last update |
| Pub/sub channel | `market:ticker:updates` | JSON `ticker_update` / `market_status` / `provider_status` messages |
| Leader lock | `market:ticker:leader` | `SET NX EX` token; renewed every 5s |

## WebSocket endpoint

`WS /ws/market/ticker` (behind nginx `/ws/` in production).

On connect the server sends a `snapshot`, then live messages:

```json
{ "type": "ticker_update", "provider": "FYERS", "market_status": "OPEN",
  "server_time": "...", "demo": false,
  "data": [ { "symbol": "NIFTY50", "display_name": "NIFTY 50", "ltp": 25123.5,
              "change": 133.2, "change_percent": 0.53, "timestamp": "...",
              "is_stale": false } ] }
```

Other message types: `snapshot`, `market_status`, `provider_status`. No provider
credentials are ever sent to the client. Auth is required by default via the
`gnk_access` session cookie (`MARKET_DATA_REQUIRE_AUTH=true`); tokens are never
placed in the WebSocket URL.

## Reconnect behavior

Both the provider (backend) and the socket (frontend) use exponential backoff
with full jitter: **1s, 2s, 4s, 8s, 15s, 30s (cap)**, resetting after the
connection stays up ~30s. No busy loop. After reconnect the provider
re-subscribes to the full index universe.

## Stale detection

Every tick carries `timestamp` and `is_stale`. While the market is OPEN, if no
upstream update arrives within `MARKET_DATA_STALE_SECONDS`, the manager marks all
cached ticks `is_stale=true`, logs `market_data.feed.stale`, and the frontend
shows **Data delayed**. A stale value is never shown as if it were live. When the
market is closed the last known price is kept and the ticker shows
**● Market Closed** (it is not cleared).

## Market status

Server-side, `Asia/Kolkata`: `PRE_OPEN` (09:00–09:15), `OPEN` (09:15–15:30),
`CLOSED`, `HOLIDAY` (weekends + `MARKET_HOLIDAYS`), `UNKNOWN`. The calendar
source in `app/market_data/market_status.py` is pluggable for a real NSE
trading-calendar integration.

## Demo mode

`MARKET_DATA_MOCK_MODE=true` (or `MARKET_DATA_PROVIDER=mock`) emits a
deterministic demo feed and the UI shows a **DEMO DATA** badge. Production never
silently falls back to mock data — a failing provider surfaces its real status.

## Local testing

```bash
# Backend (demo feed, no broker token needed)
cd backend
MARKET_DATA_MOCK_MODE=true .venv/bin/uvicorn app.main:app --reload --port 8000

# REST checks
curl -s http://localhost:8000/api/v1/market/ticker | jq .
curl -s http://localhost:8000/api/v1/market/health | jq .

# WebSocket (authenticated): log in first to get the gnk_access cookie, then
# connect a client to ws://localhost:8000/ws/market/ticker sending the cookie.

# Tests
cd backend && .venv/bin/python -m pytest tests/test_market_ticker.py -q
cd frontend && npm run test        # vitest: reducer + rendering helpers
```

Frontend dev (`cd frontend && npm run dev`) connects the ticker directly to the
backend on `:8000`; in production the browser uses same-origin `wss://.../ws/...`
proxied by nginx.

## Production deployment

```bash
cd /opt/gnkalgo
git pull origin main
# The FYERS SDK is bundled in backend/requirements.txt, so a rebuild installs it:
docker compose -f docker-compose.prod.yml up -d --build
sudo cp deploy/nginx/www.gnkalgo.com.conf /etc/nginx/sites-available/
sudo nginx -t && sudo systemctl reload nginx   # picks up the new /ws/ proxy
```

Internal services (`postgres:5432`, `redis:6379`, `ml-service:8001`,
`backend:8000`, `frontend:3000`) are bound to `127.0.0.1` in
`docker-compose.prod.yml` and are never exposed publicly — only nginx serves
`:80/:443`.

### Optional dedicated market-data worker

The manager runs inside the backend and is safe with multiple workers thanks to
the Redis leader-lock. If you prefer a dedicated process, run a second backend
container (same image) as `market-data-worker` — it will win the leader-lock and
own the feed while the web backends only read Redis. Do not expose it publicly.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Ticker shows "Connecting…" forever | Check `GET /api/v1/market/health`; verify provider creds and that the SDK is installed (`fyers-apiv3`). |
| `provider unavailable` in logs | Missing SDK or credentials; install SDK / set `FYERS_*`, or set `MARKET_DATA_MOCK_MODE=true` for local dev. |
| Prices never change | Market may be closed (expected); confirm `market_status` and, during hours, provider connectivity. |
| "Data delayed" during market hours | Upstream feed stalled > `MARKET_DATA_STALE_SECONDS`; check provider status / network. |
| WebSocket 4401 | Not logged in; the ticker WS requires the `gnk_access` session cookie. |
| WebSocket fails only in production | Ensure nginx has the `/ws/` upgrade `location` (reload nginx after `git pull`). |
| Wrong/one index missing | Verify that index's provider symbol and override it via `MARKET_DATA_SYMBOL_OVERRIDES`. |

## Data licensing warning

Live NSE/BSE market data is licensed by the exchanges and your broker. Real-time
index data via FYERS/Dhan/Upstox is subject to their subscription terms and
exchange data policies. Ensure your account is entitled to the data you stream
and displayed to end users, and comply with redistribution restrictions. Prices
shown are **not investment advice**.
