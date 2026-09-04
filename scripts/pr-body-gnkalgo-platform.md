## Summary

Upgrades GnKAlgo in place: trading terminal UI, live Dhan market data, instrument master, charts, Redis-backed cache, Finnhub news, SMC intraday strategies, and Oracle VM ops scripts.

## Changes

- **Trading terminal** — orders, positions, holdings, watchlist, broker, themes, profile
- **Phase 1** — Dhan WebSocket feed, quote cache, market WS manager
- **Charts** — Lightweight Charts, symbol search, indicators toolbar
- **Phase 2** — DB instrument master, Dhan CSV sync, search APIs
- **Phase 3** — Redis cache (candles/news), Finnhub news provider, SMC intraday strategy evaluator + UI
- **Cloud Agent** — `.cursor/environment.json`, install script
- **Ops** — `update-oracle-vm.sh` (update/start/stop), `deploy-oracle.sh`, publish helpers

## Test plan

- [ ] Login, paper order on `/orders`
- [ ] Charts: symbol search, candles load
- [ ] Strategies: SMC intraday → Run once (paper)
- [ ] `docker compose -f docker-compose.prod.yml up -d --build` on Oracle VM

## Deploy

```bash
cd /opt/gnkalgo
./scripts/update-oracle-vm.sh update
```
