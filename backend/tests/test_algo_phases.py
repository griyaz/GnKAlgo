from app.services.backtest_service import run_backtest
from app.services.strategy_service import StrategyService
from types import SimpleNamespace


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
