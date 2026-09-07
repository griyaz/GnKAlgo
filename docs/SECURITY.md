# Security baseline

- TLS 1.3 in production (Cloudflare / load balancer)
- Argon2 password hashing
- JWT access 15 minutes, rotating refresh tokens
- TOTP MFA before every live execution path (manual, signal, strategy, and
  signed webhook)
- Broker tokens encrypted with Fernet (AES-128-CBC + HMAC via cryptography)
- Webhook tokens + optional HMAC
- Account lockout after 5 failed logins
- Audit log for auth, broker connect, orders
- Dhan order APIs require a static egress IP
- Live orders require an active subscription, market hours (including
  holidays), an inactive kill switch, configured credentials, a recent broker
  health check, and configured risk limits
- Do not log secrets, tokens, or passwords

Use `GET /health/ready` as the deployment readiness probe. It returns HTTP 503
when production configuration, database, Redis, or the selected market-data
provider is not ready. Set `LIVE_TRADING_ENABLED=true` only after the
production checklist in `docs/PRODUCTION-READINESS.md` is complete.

AI signals must always show: **Not investment advice.**
