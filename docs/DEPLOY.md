# Deploy GnKAlgo

Go live on **www.gnkalgo.com** once SMTP, Postgres, HTTPS, and secrets are real.

This cloud agent cannot attach your domain by itself. You need a VPS or a host (Hetzner, AWS Mumbai, DigitalOcean, Render, Railway).

## What is ready now

| Item | Status |
|------|--------|
| App (auth, dashboard, paper orders, webhooks, AI stub) | Ready |
| Docker production compose | `docker-compose.prod.yml` |
| Live Dhan/Groww orders | Needs broker keys + Dhan static IP |
| Custom domain + TLS | You must point DNS and add HTTPS (Caddy/Nginx/Cloudflare) |

## Option A — Self-hosted VPS (recommended)

Use a VPS in India (Mumbai/Bangalore):

- App: `https://www.gnkalgo.com`
- API: `https://api.gnkalgo.com`

On the server:

```bash
git clone git@github.com:griyaz/GnKAlgo.git
cd GnKAlgo
git checkout main
cp .env.production.example .env
# edit .env: SECRET_KEY, POSTGRES_PASSWORD, SMTP_*, FRONTEND_URL, NEXT_PUBLIC_API_URL
docker compose -f docker-compose.prod.yml up -d --build
```

Put Cloudflare or Caddy in front for HTTPS. Point DNS A records to the VPS public IP.

**Oracle Cloud Ubuntu 24 + Nginx + Cloudflare (full steps):** see `docs/DEPLOY-ORACLE.md`.

## Option B — Public production (`www.gnkalgo.com`)

Production checklist:

1. Postgres (not SQLite)
2. Strong `SECRET_KEY` and `ENCRYPTION_KEY`
3. Working SMTP (verification mail)
4. HTTPS on `www.gnkalgo.com` and `api.gnkalgo.com`
5. CORS `ALLOWED_ORIGINS` set to those URLs
6. Static egress IP for Dhan order APIs
7. MFA required before live orders (next code change)
8. Backups of Postgres

## Option C — Managed hosts (less server work)

- **Frontend:** Vercel/Netlify, env `NEXT_PUBLIC_API_URL`
- **Backend + ML + Postgres + Redis:** Render, Railway, or Fly.io in `ap-south-1` if available

## Local vs production

| | Local | Production |
|--|-------|------------|
| URL | localhost:3000 | www.gnkalgo.com |
| DB | SQLite | Postgres |
| Orders | Paper | Live brokers |
| Email | Link on screen until SMTP | Real SMTP |

## After deploy, smoke test

1. Open the site over HTTPS  
2. Register → email verify → login  
3. Place a **paper** order  
4. Connect Dhan only after static IP is whitelisted  

Do not trade live money until risk checks, MFA, and broker sandbox/test are confirmed.
