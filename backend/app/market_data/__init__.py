"""Live market data pipeline for the LiveMarketTicker.

Upstream provider (FYERS primary, Dhan/Upstox optional fallback)
    -> MarketDataManager (normalize + stale detection + market status)
    -> Redis latest-price cache + pub/sub fan-out
    -> internal WebSocket /ws/market/ticker
    -> Next.js LiveMarketTicker.

See docs/LIVE_MARKET_TICKER.md for the full architecture.
"""
