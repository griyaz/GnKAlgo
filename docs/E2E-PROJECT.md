# GnKAlgo — E2E Flow, Design, URLs, Database & Operations

**Product:** https://www.gnkalgo.com  
**Repo:** `griyaz/GnKAlgo`  
**Branch:** `main`

---

## 1. System design (high level)

```
                    ┌─────────────────────────────────────────┐
                    │           Cloudflare (HTTPS)            │
                    │  gnkalgo.com / www.gnkalgo.com          │
                    └──────────────────┬──────────────────────┘
                                       │ :80 / :443
                    ┌──────────────────▼──────────────────────┐
                    │     Nginx (Oracle VM Ubuntu 24)         │
                    │  /        → 127.0.0.1:3000  Next.js     │
                    │  /api/*   → 127.0.0.1:8000  FastAPI     │
                    │  /health  → 127.0.0.1:8000              │
                    └──────────────────┬──────────────────────┘
                                       │
         ┌─────────────────────────────┼─────────────────────────────┐
         │                    Docker Compose                         │
         │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐ │
         │  │ frontend │  │ backend  │  │ml-service│  │ postgres │ │
         │  │  :3000   │  │  :8000   │  │  :8001   │  │  :5432   │ │
         │  └──────────┘  └────┬─────┘  └────┬─────┘  └──────────┘ │
         │                       │             │         ┌──────────┐ │
         │                       │             └────────►│  redis   │ │
         │                       └──────────────────────►│  :6379   │ │
         │                                                 └──────────┘ │
         └─────────────────────────────────────────────────────────────┘
```

| Layer | Technology | Role |
|-------|------------|------|
| Frontend | Next.js 15 (React) | Login, dashboard, orders, strategies, UPI subscribe, admin |
| Backend API | FastAPI + SQLAlchemy async | Auth, brokers, orders, strategies, webhooks, billing, admin |
| ML service | FastAPI + scikit-learn | RSI/MACD features, Random Forest BUY/SELL/HOLD |
| Database | PostgreSQL (prod) / SQLite (local) | All app data |
| Cache | Redis | Sessions/rate limits (reserved) |
| Brokers | DhanHQ, Groww APIs | Live orders (Dhan needs static IP) |
| Payments | UPI intents + manual UTR confirm | No PhonePe/GPay merchant API |

**Security:** Argon2 passwords, JWT access + refresh rotation, TOTP MFA, encrypted broker credentials, audit logs, webhook HMAC/secret.

---

## 2. End-to-end user flows

### 2.1 New customer (register → subscribe → trade)

```
Landing → Register → Email verify → Login
    → Subscribe (UPI) → Pay PhonePe/GPay/Paytm → Submit UTR
    → Admin confirms payment → Subscription active
    → Settings: MFA (recommended) → Connect Dhan (paper first)
    → Strategies: build BUY/SELL + schedule OR Webhooks (TradingView)
    → Orders: paper order → later live (MFA + broker + Dhan IP)
```

| Step | URL | API |
|------|-----|-----|
| Share / buy | `/subscribe` | `GET /api/v1/billing/plans` |
| Pay | `/subscribe/pay` | `POST /api/v1/billing/checkout`, `POST .../utr` |
| Register | `/register` | `POST /api/v1/auth/register` |
| Verify | `/verify-email?token=...` | `POST /api/v1/auth/verify-email` |
| Login | `/login` | `POST /api/v1/auth/login` |
| Dashboard | `/dashboard` | `GET /api/v1/dashboard/summary` |

### 2.2 Admin flow

```
Login with email in ADMIN_EMAILS → /admin
    → View registered / active / inactive users
    → Confirm UPI payments (UTR review)
    → Share link: https://www.gnkalgo.com/subscribe
```

**Active user** = logged in within last 7 days.  
**Inactive** = registered but no login in 7 days (includes never logged in).

### 2.3 Strategy execution (three paths)

| Path | Trigger | Source tag on order |
|------|---------|---------------------|
| Manual | **Run once** on Strategies page | `strategy` |
| Scheduled | Backend scheduler every ~60s tick | `strategy_scheduler` |
| Webhook | TradingView POST to inbound URL | `webhook` |
| Manual order | Orders page | `manual` |

Scheduler runs strategies where `schedule_enabled = true`, `status != PAUSED`, and `interval_minutes` elapsed since `last_scheduled_run_at`.

### 2.4 AI signals flow

```
/signals → Generate → backend calls ml-service → stores signals table
User reads BUY/SELL/HOLD (not auto-trade unless you act manually)
```

---

## 3. All URLs

### 3.1 Production (public)

| URL | Type | Description |
|-----|------|-------------|
| https://www.gnkalgo.com | Web | Landing |
| https://gnkalgo.com | Web | Apex (same app) |
| https://www.gnkalgo.com/register | Web | Create account |
| https://www.gnkalgo.com/login | Web | Login |
| https://www.gnkalgo.com/verify-email | Web | Email verification |
| https://www.gnkalgo.com/forgot-password | Web | Password reset request |
| https://www.gnkalgo.com/reset-password | Web | Set new password |
| https://www.gnkalgo.com/dashboard | Web | Dashboard (auth) |
| https://www.gnkalgo.com/subscribe | Web | **Share this for sales** |
| https://www.gnkalgo.com/subscribe/pay | Web | UPI pay + UTR |
| https://www.gnkalgo.com/orders | Web | Orders |
| https://www.gnkalgo.com/strategies | Web | Strategy builder |
| https://www.gnkalgo.com/signals | Web | AI signals |
| https://www.gnkalgo.com/webhooks | Web | Webhook setup |
| https://www.gnkalgo.com/settings | Web | MFA + brokers |
| https://www.gnkalgo.com/admin | Web | Admin (admin emails only) |
| https://www.gnkalgo.com/health | API proxy | Backend health |
| https://www.gnkalgo.com/api/v1/... | API | All REST endpoints |
| https://www.gnkalgo.com/docs | API proxy | OpenAPI (if exposed) |
| https://api.gnkalgo.com | API | Optional dedicated API host |

### 3.2 Local development

| URL | Service |
|-----|---------|
| http://localhost:3000 | Next.js frontend |
| http://localhost:8000 | FastAPI backend |
| http://localhost:8000/docs | API docs |
| http://localhost:8001 | ML service |
| http://localhost:8001/health | ML health |

### 3.3 Production internal (VM only — not public)

| Host | Port | Service |
|------|------|---------|
| 127.0.0.1 | 3000 | frontend container |
| 127.0.0.1 | 8000 | backend container |
| 127.0.0.1 | 8001 | ml-service container |
| postgres (docker) | 5432 | PostgreSQL |
| redis (docker) | 6379 | Redis |

### 3.4 REST API map (`/api/v1` and duplicate `/v1`)

**Auth** (`/auth`)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/auth/register` | No | Register |
| POST | `/auth/resend-verification` | No | Resend verify email |
| POST | `/auth/verify-email` | No | Verify token |
| POST | `/auth/login` | No | JWT tokens |
| POST | `/auth/refresh` | No | Rotate refresh token |
| POST | `/auth/forgot-password` | No | Reset email |
| POST | `/auth/reset-password` | No | Set password |
| GET | `/auth/me` | Yes | Current user |
| POST | `/auth/logout` | No | Revoke refresh |
| POST | `/auth/mfa/setup` | Yes | TOTP QR |
| POST | `/auth/mfa/enable` | Yes | Enable MFA |

**Brokers** (`/brokers`)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/brokers/connect` | Yes | Save Dhan/Groww creds |
| GET | `/brokers/connections` | Yes | List connections |

**Dashboard** (`/dashboard`)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/dashboard/summary` | Yes | Stats + next steps |

**Orders** (`/orders`)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/orders/` | Yes | List orders |
| POST | `/orders/` | Yes | Place order |

**Strategies** (`/strategies`)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/strategies/` | Yes | List |
| POST | `/strategies/` | Yes | Create |
| PUT | `/strategies/{id}` | Yes | Update builder fields |
| POST | `/strategies/{id}/status` | Yes | Set status |
| POST | `/strategies/{id}/run` | Yes | Run once |

**Signals** (`/signals`)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/signals/` | Yes | List signals |
| POST | `/signals/generate` | Yes | Call ML + store |

**Webhooks** (`/webhooks`)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/webhooks/` | Yes | List |
| POST | `/webhooks/` | Yes | Create inbound/outbound |
| POST | `/webhooks/in/{token}` | Secret/HMAC | Inbound alert → order |

Inbound URL format: `{BACKEND_PUBLIC_URL}/api/v1/webhooks/in/{token}`

**Billing** (`/billing`)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/billing/plans` | No | Plans + share URL |
| GET | `/billing/me` | Yes | My subscription |
| POST | `/billing/checkout` | Yes | UPI checkout |
| POST | `/billing/payments/{id}/utr` | Yes | Submit UTR |

**Admin** (`/admin`) — requires `is_admin`

| Method | Path | Description |
|--------|------|-------------|
| GET | `/admin/stats` | User + payment counts |
| GET | `/admin/users` | All users + activity |
| GET | `/admin/payments` | All payments |
| POST | `/admin/payments/{id}/confirm` | Activate subscription |

**Health**

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | `{"status":"ok"}` |

### 3.5 ML service

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | ML service health |
| POST | `/ml/v1/predict` | Single prediction |
| POST | `/ml/v1/train` | Train on mock OHLCV |
| GET | `/ml/v1/signals/batch?symbols=RELIANCE,TCS` | Batch signals |

### 3.6 UPI pricing (business logic)

| Plan code | Price | Days |
|-----------|-------|------|
| DAILY | ₹199 | 1 |
| 5DAYS | ₹999 | 5 |
| 22DAYS | ₹1,999 | 22 |

---

## 4. Database

### 4.1 Tables

| Table | Purpose |
|-------|---------|
| `users` | Accounts, MFA, admin flag, last_login_at |
| `user_sessions` | Refresh token hashes |
| `email_verification_tokens` | Email verify |
| `password_reset_tokens` | Password reset |
| `broker_connections` | Encrypted Dhan/Groww creds |
| `audit_logs` | Security audit trail |
| `orders` | All orders (paper/live) |
| `strategies` | Strategy config + schedule |
| `strategy_runs` | Each strategy execution |
| `signals` | AI signal history |
| `webhooks` | Inbound/outbound webhook config |
| `webhook_logs` | Inbound webhook payloads |
| `payments` | UPI payment intents + UTR |
| `subscriptions` | Active plan per user |

### 4.2 Key columns

**users:** `id`, `email`, `phone`, `password_hash`, `full_name`, `is_verified`, `mfa_enabled`, `is_admin`, `last_login_at`, `created_at`

**strategies:** `rules_json` (e.g. `{"action":"BUY","qty":1}`), `paper_mode`, `schedule_enabled`, `interval_minutes`, `last_scheduled_run_at`, `status` (DRAFT/PAPER/LIVE/PAUSED)

**payments:** `status` = `pending` → `submitted` (UTR) → `confirmed`

**subscriptions:** one row per user; `expires_at` defines access end

### 4.3 Connect to Postgres (production VM)

```bash
cd /opt/gnkalgo
docker compose -f docker-compose.prod.yml exec postgres \
  psql -U gnkalgo -d gnkalgo
```

### 4.4 Common SQL queries

**Registered users**

```sql
SELECT COUNT(*) AS registered FROM users;
```

**Verified users**

```sql
SELECT COUNT(*) FROM users WHERE is_verified = true;
```

**Logged in last 7 days (active)**

```sql
SELECT COUNT(*) FROM users
WHERE last_login_at >= NOW() - INTERVAL '7 days';
```

**Never logged in**

```sql
SELECT COUNT(*) FROM users WHERE last_login_at IS NULL;
```

**All users with activity label**

```sql
SELECT email, is_verified, created_at, last_login_at,
  CASE
    WHEN last_login_at IS NULL THEN 'never_logged_in'
    WHEN last_login_at >= NOW() - INTERVAL '7 days' THEN 'active'
    ELSE 'inactive'
  END AS activity
FROM users
ORDER BY created_at DESC;
```

**Active subscribers**

```sql
SELECT u.email, s.plan_code, s.expires_at
FROM subscriptions s
JOIN users u ON u.id = s.user_id
WHERE s.expires_at >= NOW()
ORDER BY s.expires_at DESC;
```

**Payments awaiting UTR review**

```sql
SELECT p.reference, p.amount_inr, p.utr, u.email, p.created_at
FROM payments p
JOIN users u ON u.id = p.user_id
WHERE p.status = 'submitted'
ORDER BY p.created_at DESC;
```

**Today's orders**

```sql
SELECT o.symbol, o.side, o.quantity, o.status, o.broker, o.source, o.created_at
FROM orders o
WHERE o.created_at >= CURRENT_DATE
ORDER BY o.created_at DESC;
```

**Scheduled strategies**

```sql
SELECT name, symbol, rules_json, interval_minutes, status, last_scheduled_run_at
FROM strategies
WHERE schedule_enabled = true;
```

**Recent strategy runs**

```sql
SELECT sr.started_at, sr.status, sr.notes, s.name, s.symbol
FROM strategy_runs sr
JOIN strategies s ON s.id = sr.strategy_id
ORDER BY sr.started_at DESC
LIMIT 20;
```

**Revenue (confirmed UPI)**

```sql
SELECT plan_code, COUNT(*) AS count, SUM(amount_inr) AS total_inr
FROM payments
WHERE status = 'confirmed'
GROUP BY plan_code;
```

### 4.5 Backup database

```bash
cd /opt/gnkalgo
docker compose -f docker-compose.prod.yml exec -T postgres \
  pg_dump -U gnkalgo gnkalgo > backup_$(date +%Y%m%d).sql
```

---

## 5. Services — start, stop, restart

### 5.1 Production (Oracle VM — `/opt/gnkalgo`)

Always use:

```bash
cd /opt/gnkalgo
docker compose -f docker-compose.prod.yml <command>
```

| Action | Command |
|--------|---------|
| **Start all** | `docker compose -f docker-compose.prod.yml up -d` |
| **Start + rebuild** | `docker compose -f docker-compose.prod.yml up -d --build` |
| **Stop all** | `docker compose -f docker-compose.prod.yml down` |
| **Stop (keep data)** | `docker compose -f docker-compose.prod.yml stop` |
| **Restart all** | `docker compose -f docker-compose.prod.yml restart` |
| **Status** | `docker compose -f docker-compose.prod.yml ps` |
| **Logs (all)** | `docker compose -f docker-compose.prod.yml logs -f` |
| **Logs backend** | `docker compose -f docker-compose.prod.yml logs -f backend` |
| **Logs frontend** | `docker compose -f docker-compose.prod.yml logs -f frontend` |

**Single service**

```bash
docker compose -f docker-compose.prod.yml up -d --build backend
docker compose -f docker-compose.prod.yml up -d --build frontend
docker compose -f docker-compose.prod.yml restart backend
docker compose -f docker-compose.prod.yml stop ml-service
```

**After `.env` change (SMTP, UPI, ADMIN_EMAILS)**

```bash
docker compose -f docker-compose.prod.yml up -d --force-recreate backend
```

**After `NEXT_PUBLIC_API_URL` change**

```bash
docker compose -f docker-compose.prod.yml build --no-cache frontend
docker compose -f docker-compose.prod.yml up -d frontend
```

**Pull latest code + deploy**

```bash
cd /opt/gnkalgo
git pull origin main
docker compose -f docker-compose.prod.yml up -d --build
```

### 5.2 Nginx (host — not Docker)

| Action | Command |
|--------|---------|
| Test config | `sudo nginx -t` |
| Reload | `sudo systemctl reload nginx` |
| Restart | `sudo systemctl restart nginx` |
| Stop | `sudo systemctl stop nginx` |
| Start | `sudo systemctl start nginx` |
| Status | `sudo systemctl status nginx` |

Copy site config after pull:

```bash
sudo cp /opt/gnkalgo/deploy/nginx/www.gnkalgo.com.conf /etc/nginx/sites-available/
sudo nginx -t && sudo systemctl reload nginx
```

### 5.3 Local development

```bash
cd /path/to/gnkalgo
cp .env.example .env

# All services (postgres, redis, backend, ml — no frontend in default compose)
docker compose up --build

# Or run frontend separately:
cd frontend && npm install && npm run dev
```

| Action | Command |
|--------|---------|
| Start | `docker compose up -d` |
| Stop | `docker compose down` |
| Rebuild | `docker compose up -d --build` |
| Backend only (venv) | `cd backend && uvicorn app.main:app --reload --port 8000` |

### 5.4 Health checks after start

```bash
curl -s https://www.gnkalgo.com/health
curl -s http://127.0.0.1:3000
curl -s http://127.0.0.1:8000/health
curl -s http://127.0.0.1:8001/health
```

---

## 6. Environment variables (production)

| Variable | Example | Purpose |
|----------|---------|---------|
| `SECRET_KEY` | random 64 hex | JWT signing |
| `ENCRYPTION_KEY` | random 32+ chars | Broker credential encryption |
| `POSTGRES_PASSWORD` | strong | DB password |
| `FRONTEND_URL` | `https://www.gnkalgo.com` | Verify email links |
| `BACKEND_PUBLIC_URL` | `https://www.gnkalgo.com` | Webhook inbound URLs |
| `NEXT_PUBLIC_API_URL` | empty | Same-origin `/api` on www |
| `ALLOWED_ORIGINS` | `https://www.gnkalgo.com,...` | CORS |
| `SMTP_*` | Namecheap mail | Verification email |
| `ADMIN_EMAILS` | `you@gnkalgo.com` | Admin access |
| `UPI_VPA` | `name@oksbi` | UPI receive |
| `UPI_PAYEE_NAME` | `GNK ALGO` | UPI display name |
| `STRATEGY_SCHEDULER_TICK_SECONDS` | `60` | Scheduler interval |

See `.env.production.example` and `docs/DEPLOY-ORACLE.md`.

---

## 7. Related docs

| Doc | Topic |
|-----|-------|
| `docs/DEPLOY-ORACLE.md` | Full Oracle + Cloudflare setup |
| `docs/DEPLOY.md` | Deploy options overview |
| `docs/NEXT-STEPS.md` | Post-login checklist |
| `docs/EMAIL.md` | SMTP setup |
| `docs/TRADINGVIEW.md` | Webhook alerts |
| `docs/SECURITY.md` | Security practices |
| `docs/PHASES.md` | Product roadmap phases |

---

## 8. Quick reference card

```
Share URL:     https://www.gnkalgo.com/subscribe
Admin:         https://www.gnkalgo.com/admin
API prefix:    https://www.gnkalgo.com/api/v1
Deploy:        git pull && docker compose -f docker-compose.prod.yml up -d --build
DB shell:      docker compose -f docker-compose.prod.yml exec postgres psql -U gnkalgo -d gnkalgo
Stop site:     docker compose -f docker-compose.prod.yml down
```
