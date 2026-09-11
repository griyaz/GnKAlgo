from datetime import datetime, timezone
from types import SimpleNamespace

from app.services.backtest_service import run_backtest
from app.services.strategy_service import StrategyService, _candle_epoch_seconds


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


def test_candle_epoch_seconds_normalizes_millis():
    assert _candle_epoch_seconds(1_710_000_000_000) == 1_710_000_000
    assert _candle_epoch_seconds(1_710_000_000) == 1_710_000_000
    assert _candle_epoch_seconds(None) is None
    assert _candle_epoch_seconds("nope") is None


def test_smc_same_bar_guard_compares_stored_candle_time():
    svc = StrategyService()
    strategy = SimpleNamespace(last_signal_bar_ts=1_710_000_000)
    assert svc._already_acted_on_bar(strategy, 1_710_000_000) is True
    assert svc._already_acted_on_bar(strategy, 1_710_000_000 - 900) is True
    assert svc._already_acted_on_bar(strategy, 1_710_000_000 + 900) is False
    assert svc._already_acted_on_bar(SimpleNamespace(last_signal_bar_ts=None), 1_710_000_000) is False
