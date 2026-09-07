# Production readiness and secrets

## Deployment gates

1. Use PostgreSQL and Redis; do not run live execution on SQLite.
2. Set unique, randomly generated `SECRET_KEY` and `ENCRYPTION_KEY` values in a
   secret manager. Never put them in git, images, compose files, or logs.
3. Use HTTPS for both public URLs, set `COOKIE_SECURE=true`, and restrict
   `ALLOWED_ORIGINS` to the deployed frontend.
4. Configure SMTP and verify registration, MFA setup, login, and recovery.
5. Configure one real market-data provider. `MARKET_DATA_PROVIDER=mock` is
   rejected in production. FYERS requires `FYERS_CLIENT_ID` and
   `FYERS_ACCESS_TOKEN`; Upstox requires its enabled flag and access token;
   Dhan requires its enabled flag, client ID, and access token.
6. Keep `LIVE_TRADING_ENABLED=false` while validating the deployment.
   Enable it only after connecting and health-checking the intended user broker.

## Broker secrets

Store secrets in a managed store (for example Vault, AWS Secrets Manager,
GCP Secret Manager, or the host's encrypted environment store) and inject
them at runtime. Broker tokens submitted through `/brokers/connect` are
encrypted at rest and never returned by the API. Rotate broker tokens and
`ENCRYPTION_KEY` according to your incident-response policy.

For Dhan execution, reserve a stable public egress IPv4 address, put the same
address in `DHAN_STATIC_IP`, and allowlist it in DhanHQ before connecting the
broker. The live gate rejects missing or invalid addresses. FYERS requires a
client ID plus token; Upstox requires a bearer access token and an HTTPS API
base URL.

## Live execution checklist

- [ ] `GET /health/ready` returns `200` and no configuration errors.
- [ ] Postgres backups and restore verification are scheduled.
- [ ] TLS, firewall rules, rate limiting, and log retention are configured.
- [ ] Admin account is verified and protected by MFA.
- [ ] The user's broker connection reports `connected` and has a recent health
      check.
- [ ] Subscription is active and the admin kill switch is intentionally off.
- [ ] Maximum quantity and daily loss limits are reviewed.
- [ ] A paper order and a rejected off-hours/kill-switch order are observed in
      the audit log.
- [ ] Enable `LIVE_TRADING_ENABLED=true` only for the approved window.

All rejected live attempts are persisted as audit events. Paper orders do not
contact a broker and remain available outside market hours.
