# GnKAlgo — Phased Implementation Plan

**Domain:** https://www.gnkalgo.com  
**Stack:** FastAPI + Python ML + Next.js + PostgreSQL + Redis  
**Brokers:** Dhan (DhanHQ) + Groww

---

## Phase 1 — Foundation & Secure Auth (Week 1–2)

**Goal:** Users can register, verify email, login with MFA-ready security.

| Step | Task | Output |
|------|------|--------|
| 1.1 | Monorepo scaffold (`backend`, `ml-service`, `frontend`) | Project structure |
| 1.2 | PostgreSQL + Redis via Docker Compose | Local dev infra |
| 1.3 | User model, sessions, audit logs | Alembic migrations |
| 1.4 | Registration API (email, phone, password validation) | `POST /api/v1/auth/register` |
| 1.5 | Email verification flow | Token + verify endpoint |
| 1.6 | Login API (JWT access + refresh rotation) | `POST /api/v1/auth/login` |
| 1.7 | Password reset flow | Forgot / reset endpoints |
| 1.8 | TOTP MFA setup & verify | `POST /api/v1/auth/mfa/*` |
| 1.9 | Rate limiting + account lockout | Redis-backed limits |
| 1.10 | Next.js login & register pages | `/login`, `/register` |
| 1.11 | Security headers, CORS, HTTPS config | Production-ready defaults |

**Exit criteria:** Register → verify → login → receive JWT; MFA can be enabled.

---

## Phase 2 — Broker Integration (Week 3–4)

**Goal:** Connect Dhan and Groww; read portfolio data on dashboard.

| Step | Task | Output |
|------|------|--------|
| 2.1 | Broker adapter interface (`BrokerAdapter`) | `app/brokers/base.py` |
| 2.2 | DhanHQ adapter (API key auth, token refresh) | `app/brokers/dhan.py` |
| 2.3 | Groww adapter (OAuth / API key + TOTP) | `app/brokers/groww.py` |
| 2.4 | Encrypt broker tokens (AES-256-GCM) | `app/core/encryption.py` |
| 2.5 | Broker connection CRUD API | `POST /api/v1/brokers/connect` |
| 2.6 | Static IP note for Dhan order APIs | Infra doc + env config |
| 2.7 | Holdings, positions, funds endpoints | `GET /api/v1/portfolio/*` |
| 2.8 | Broker health check job | Connection status in DB |
| 2.9 | Dashboard UI — portfolio summary | `/dashboard` page |

**Exit criteria:** User links Dhan or Groww; dashboard shows holdings and funds.

---

## Phase 3 — Orders & Real-time Updates (Week 5–6)

**Goal:** Place, modify, cancel orders; live order book on UI.

| Step | Task | Output |
|------|------|--------|
| 3.1 | Order model + audit trail | `orders` table |
| 3.2 | Place order API (broker routing) | `POST /api/v1/orders` |
| 3.3 | Modify / cancel order APIs | `PUT/DELETE /api/v1/orders/{id}` |
| 3.4 | Order history + filters | `GET /api/v1/orders` |
| 3.5 | Idempotency keys on placement | Prevent duplicate orders |
| 3.6 | WebSocket order updates | `ws://api/orders/stream` |
| 3.7 | Risk pre-checks (max qty, market hours) | `app/services/risk.py` |
| 3.8 | Orders UI page | `/orders` with live status |

**Exit criteria:** Manual buy/sell through UI; orders reflected in broker app.

---

## Phase 4 — Webhooks (Week 7)

**Goal:** Inbound alerts (TradingView) and outbound notifications.

| Step | Task | Output |
|------|------|--------|
| 4.1 | Webhook model (inbound/outbound) | `webhooks` table |
| 4.2 | Inbound endpoint with HMAC verify | `POST /api/v1/webhooks/in/{token}` |
| 4.3 | Payload → order mapping rules | JSON schema validation |
| 4.4 | Outbound dispatcher (HTTP POST) | BullMQ / Celery worker |
| 4.5 | Webhook logs + retry logic | `webhook_logs` table |
| 4.6 | Webhooks management UI | `/webhooks` page |
| 4.7 | TradingView alert template docs | `docs/TRADINGVIEW.md` |

**Exit criteria:** TradingView alert triggers order on linked broker.

---

## Phase 5 — Strategy Engine (Week 8–10)

**Goal:** Create, schedule, and run strategies (paper + live).

| Step | Task | Output |
|------|------|--------|
| 5.1 | Strategy model + versioning | `strategies` table |
| 5.2 | Strategy CRUD API | `POST /api/v1/strategies` |
| 5.3 | Python strategy sandbox (restricted exec) | `app/services/strategy_runner.py` |
| 5.4 | Market-hours scheduler (APScheduler / Celery Beat) | 9:15–15:30 IST |
| 5.5 | Paper trading mode | Simulated fills |
| 5.6 | Live execution via broker adapter | Strategy → Order Service |
| 5.7 | Risk manager (daily loss, position limits) | `app/services/risk.py` |
| 5.8 | Strategy UI (create, edit, backtest stub) | `/strategies` pages |
| 5.9 | Strategy run logs | `strategy_runs` table |

**Exit criteria:** Scheduled strategy places paper/live orders with risk checks.

---

## Phase 6 — AI / ML Signals (Week 11–13)

**Goal:** Generate BUY/SELL/HOLD signals; display and optionally auto-trade.

| Step | Task | Output |
|------|------|--------|
| 6.1 | ML service scaffold (separate FastAPI app) | `ml-service/` |
| 6.2 | Feature engineering pipeline | RSI, MACD, volume, returns |
| 6.3 | Historical data ingestion (broker OHLC) | `ml-service/pipelines/data.py` |
| 6.4 | Baseline model (Random Forest / XGBoost) | `ml-service/models/classifier.py` |
| 6.5 | Model training + versioning (MLflow optional) | `models/registry/` |
| 6.6 | Inference API | `POST /ml/v1/predict` |
| 6.7 | Batch signal generation job | Celery task every N minutes |
| 6.8 | Signals API + DB storage | `GET /api/v1/signals` |
| 6.9 | Signals dashboard UI | `/signals` page |
| 6.10 | Optional auto-execute (user opt-in) | Signal → Strategy → Order |
| 6.11 | SEBI disclaimer on all signal views | Legal copy in UI |

**Exit criteria:** Dashboard shows AI signals with confidence; optional webhook on new signal.

---

## Phase 7 — Production Hardening (Week 14–16)

**Goal:** Secure, monitored, deployable on AWS Mumbai with static IP.

| Step | Task | Output |
|------|------|--------|
| 7.1 | AWS ap-south-1 deployment (ECS/EKS or EC2) | Infra runbook |
| 7.2 | Elastic IP for Dhan order APIs | Static outbound IP |
| 7.3 | Secrets Manager for broker tokens | No secrets in env files |
| 7.4 | Cloudflare WAF + TLS | `gnkalgo.com` DNS |
| 7.5 | Sentry + Prometheus + Grafana | Error & latency monitoring |
| 7.6 | Load testing (orders, webhooks) | k6 scripts |
| 7.7 | Penetration test checklist | `docs/SECURITY.md` |
| 7.8 | Backup & disaster recovery | PG daily snapshots |
| 7.9 | API documentation (OpenAPI) | `/docs` + public API docs |
| 7.10 | Mobile-ready API versioning | `v1` stable contract |

**Exit criteria:** Production launch with monitoring, static IP, and compliance docs.

---

## E2E Flow Summary

```
Register → Verify Email → Login → Enable MFA
    → Connect Broker (Dhan/Groww)
    → Dashboard (portfolio, P&L)
    → [Manual Order | Webhook Alert | Strategy | AI Signal]
    → Risk Check → Broker API → Order Fill
    → WebSocket Update → Dashboard + Outbound Webhook
```

---

## Service Topology

| Service | Port | Role |
|---------|------|------|
| `frontend` | 3000 | Next.js UI |
| `backend` | 8000 | Main API (auth, orders, brokers) |
| `ml-service` | 8001 | AI inference & training |
| `postgres` | 5432 | Primary database |
| `redis` | 6379 | Cache, sessions, job queue |

---

## Dependency Order

```
Phase 1 (Auth) → Phase 2 (Brokers) → Phase 3 (Orders)
    → Phase 4 (Webhooks) → Phase 5 (Strategies)
    → Phase 6 (AI/ML) → Phase 7 (Production)
```

Phase 6 can start feature pipeline work in parallel with Phase 3 using mock data.

## Incremental phase slice (implemented)

The backend now provides a controlled vertical slice for the remaining phases:

- Signals persist exchange, entry range, stop/targets, timeframe, lifecycle,
  explanation and model/strategy provenance. `POST /api/v1/signals/{id}/route`
  always goes through the existing risk, kill-switch, broker and audit guards;
  live routing cannot be enabled by a signal payload alone.
- Strategy rules are immutable `strategy_versions`. A successful deterministic
  backtest marks a strategy as paper-validated, while `LIVE` remains an
  explicit lifecycle transition.
- `POST /api/v1/backtests/run` accepts validated OHLC data only. It derives a
  decision from the completed prior candle and fills on the next open, so the
  engine does not execute user Python/JavaScript or look ahead.
- `/api/v1/paper/runs` provides simulated fills, positions, cash/P&L and
  position/daily-loss controls without contacting a broker.

Live deployment still depends on a configured broker connection, MFA,
subscription, market hours, Dhan static-IP allowlisting and the persistent
kill switch. Upstox V3 streaming and the existing instrument master are
available; a provider-specific historical candle adapter remains deployment
configuration dependent and is not silently substituted for real data.
