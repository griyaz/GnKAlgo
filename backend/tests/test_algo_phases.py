from datetime import datetime, timezone
from types import SimpleNamespace

from app.schemas.trading import StrategyUpdateRequest
from app.services.backtest_service import run_backtest
from app.services.strategy_service import StrategyService


def _flat_candles(count: int, start: int = 1) -> list[dict]:
    return [
        {"time": start + i, "open": 100, "high": 101, "low": 99, "close": 100}
        for i in range(count)
    ]


def _smc_fvg_then_fill() -> list[dict]:
    """Bullish FVG on completed bars, plus one extra bar for the no-lookahead fill."""
    candles = []
    for i in range(10):
        candles.append(
            {
                "time": i + 1,
                "open": 100.0,
                "high": 100.8,
                "low": 99.4,
                "close": 100.2,
            }
        )
    candles.append({"time": 11, "open": 100.2, "high": 101.0, "low": 100.0, "close": 100.6})
    candles.append({"time": 12, "open": 101.2, "high": 102.4, "low": 101.1, "close": 102.0})
    candles.append({"time": 13, "open": 103.2, "high": 104.0, "low": 103.1, "close": 103.6})
    candles.append({"time": 14, "open": 103.6, "high": 104.0, "low": 103.0, "close": 103.8})
    return candles


def test_backtest_fills_after_signal_candle_without_lookahead():
    result = run_backtest(
        {"type": "simple", "action": "BUY", "stop_loss_pct": 1, "target_pct": 2},
        [
            {"time": 1, "open": 100, "high": 101, "low": 99, "close": 100},
            {"time": 2, "open": 100, "high": 101, "low": 99, "close": 100},
            {"time": 3, "open": 100, "high": 103, "low": 100, "close": 102},
        ],
        initial_capital=1000,
    )
    # The entry is the second candle open, not the first candle close or the
    # third candle open, and the third candle reaches the target.
    assert result["trade_count"] == 1
    assert result["trades"][0]["entry_price"] == 100
    assert result["trades"][0]["exit_price"] == 102
    assert result["trades"][0]["reason"] == "TARGET"


def test_backtest_rejects_unsorted_or_duplicate_candles():
    candles = [
        {"time": 2, "open": 100, "high": 101, "low": 99, "close": 100},
        {"time": 2, "open": 100, "high": 101, "low": 99, "close": 100},
    ]
    try:
        run_backtest({"action": "BUY"}, candles, initial_capital=1000)
    except ValueError as exc:
        assert "chronological" in str(exc)
    else:
        raise AssertionError("duplicate candle timestamps must be rejected")


def test_live_lifecycle_requires_paper_validation():
    strategy = SimpleNamespace(status="PAPER", paper_verified_at=None)
    try:
        StrategyService._validate_transition(strategy, "LIVE")
    except ValueError as exc:
        assert "paper/backtest" in str(exc)
    else:
        raise AssertionError("live transition must require paper validation")


def test_smc_backtest_does_not_always_enter_on_two_candles():
    result = run_backtest(
        {
            "type": "smc_intraday",
            "entry": "fvg",
            "action": "AUTO",
            "stop_loss_buffer_pct": 0.1,
            "target_rr": 2.0,
        },
        _flat_candles(2),
        initial_capital=1000,
    )
    assert result["trade_count"] == 0
    assert result["metrics"]["signal_count"] == 0


def test_smc_backtest_ignores_flat_series_with_no_setup():
    result = run_backtest(
        {
            "type": "smc_intraday",
            "entry": "fvg",
            "action": "AUTO",
            "stop_loss_buffer_pct": 0.1,
            "target_rr": 2.0,
        },
        _flat_candles(15),
        initial_capital=1000,
    )
    assert result["trade_count"] == 0
    assert result["metrics"]["signal_count"] == 0


def test_smc_backtest_enters_on_fvg_without_lookahead():
    result = run_backtest(
        {
            "type": "smc_intraday",
            "entry": "fvg",
            "action": "AUTO",
            "stop_loss_buffer_pct": 0.1,
            "target_rr": 2.0,
        },
        _smc_fvg_then_fill(),
        initial_capital=100000,
    )
    assert result["metrics"]["signal_count"] >= 1
    assert result["trade_count"] >= 1
    assert result["trades"][0]["side"] == "BUY"


def test_live_strategy_symbol_change_clears_validation():
    from datetime import datetime, timezone

    strategy = SimpleNamespace(
        id=None,
        user_id=None,
        name="SMC",
        description=None,
        symbol="RELIANCE",
        rules_json='{"type":"smc_intraday","timeframe":"15m","entry":"fvg","action":"AUTO","qty":1,"stop_loss_buffer_pct":0.1,"target_rr":2.0,"swing_lookback":5}',
        status="LIVE",
        paper_mode=False,
        max_quantity=100,
        max_daily_loss=5000,
        schedule_enabled=True,
        interval_minutes=15,
        last_scheduled_run_at=None,
        current_version=1,
        paper_verified_at=datetime.now(timezone.utc),
    )

    class _FakeResult:
        def scalar_one_or_none(self):
            return strategy

    class _FakeDB:
        def add(self, _obj):
            return None

        async def execute(self, _stmt):
            return _FakeResult()

    async def run():
        svc = StrategyService()
        updated = await svc.update(
            _FakeDB(),
            SimpleNamespace(id="user"),
            "strategy-id",
            StrategyUpdateRequest(symbol="SBIN"),
        )
        assert updated.symbol == "SBIN"
        assert updated.paper_verified_at is None
        assert updated.status == "PAUSED"
        assert updated.current_version == 2

    import asyncio

    asyncio.run(run())


def _scheduled(status: str, paper_mode: bool, last=None):
    return SimpleNamespace(
        schedule_enabled=True,
        interval_minutes=1,
        status=status,
        paper_mode=paper_mode,
        last_scheduled_run_at=last,
    )


def test_scheduler_does_not_treat_draft_live_strategies_as_due():
    """Create-with-live + schedule used to stay DRAFT and still auto-fire."""
    now = datetime.now(timezone.utc)
    svc = StrategyService()
    assert svc.is_due(_scheduled("DRAFT", paper_mode=False), now) is False
    assert svc.is_due(_scheduled("PAPER", paper_mode=False), now) is False
    assert svc.is_due(_scheduled("PAPER", paper_mode=True), now) is True
    assert svc.is_due(_scheduled("LIVE", paper_mode=False), now) is True
