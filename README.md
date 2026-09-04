# GnKAlgo

Indian algo trading platform for **www.gnkalgo.com**.

Stack: **FastAPI** (backend) + **Python ML service** + **Next.js** (frontend) + PostgreSQL/SQLite + Redis.

Brokers: **DhanHQ** and **Groww**.

## Local development

```bash
# 1. Backend
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# 2. ML service (optional for AI signals)
cd ml-service
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8001

# 3. Frontend
cd frontend
npm install
npm run dev
```

Open http://localhost:3000

API docs: http://localhost:8000/docs

## Docker

```bash
cp .env.example .env
docker compose up --build
```

Default local database is SQLite (`backend/gnkalgo.db`). Set `DATABASE_URL` to PostgreSQL in production.

## Product modules

| Route | Purpose |
|-------|---------|
| `/login` `/register` | Auth with JWT, MFA, password rules |
| `/dashboard` | Portfolio and activity summary |
| `/orders` | Paper and live orders |
| `/strategies` | Strategy builder: BUY/SELL, qty, paper/live, schedule every N minutes |
| `/signals` | AI BUY/SELL/HOLD signals |
| `/webhooks` | TradingView-style inbound webhooks |
| `/subscribe` | **Share this URL with all users.** UPI plans ₹199 / ₹999 / ₹1,999 |
| `/subscribe/pay` | PhonePe, GPay, Paytm intents + UTR |
| `/admin` | Who registered, who logged in, active vs inactive, confirm UPI |

After login, use the dashboard **Next product steps** checklist. Details: `docs/NEXT-STEPS.md`.

## Security

- Argon2 password hashing
- Short-lived JWT access tokens + rotating refresh tokens
- TOTP MFA
- Encrypted broker credentials
- HMAC + token for inbound webhooks
- Risk checks (qty cap, market hours for live orders)
- Audit logs

AI signals are **not investment advice**.

## Email / verification

Set SMTP in `.env` (see `docs/EMAIL.md`). Until then, register shows a verify link in the app.

## Deploy

See `docs/DEPLOY.md`. Production: `docker compose -f docker-compose.prod.yml up -d --build`

**Oracle Cloud + Ubuntu 24 + Nginx + Cloudflare:** `docs/DEPLOY-ORACLE.md`

**E2E flow, all URLs, DB queries, start/stop:** `docs/E2E-PROJECT.md`

**Admin access (fix "Admin only"):** `docs/ADMIN-ACCESS.md`


See `docs/PHASES.md`.
