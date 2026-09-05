from app.services.strategy_evaluators.smc_intraday import evaluate_smc_intraday


def _candles_bullish_fvg():
    base = 100.0
    candles = []
    for i in range(12):
        candles.append({
            "time": i,
            "open": base,
            "high": base + 1,
            "low": base - 1,
            "close": base + 0.5,
        })
        base += 0.2
    # Force bullish FVG on last three bars
    candles[-3]["high"] = 102.0
    candles[-2]["low"] = 101.5
    candles[-1]["low"] = 103.0
    candles[-1]["close"] = 103.5
    candles[-1]["high"] = 104.0
    return candles


def test_smc_bullish_fvg_auto_buy():
    signal = evaluate_smc_intraday(_candles_bullish_fvg(), entry_mode="fvg", side_mode="AUTO")
    assert signal.should_trade
    assert signal.side == "BUY"
    assert signal.entry is not None
    assert signal.stop_loss is not None
    assert signal.target is not None
    assert signal.target > signal.entry > signal.stop_loss


def test_smc_no_setup_skipped():
    flat = [
        {"time": i, "open": 100, "high": 100.5, "low": 99.5, "close": 100}
        for i in range(15)
    ]
    signal = evaluate_smc_intraday(flat, entry_mode="fvg", side_mode="AUTO")
    assert not signal.should_trade


def test_smc_create_rules_json():
    from app.services.strategy_service import build_rules_json
    from app.schemas.trading import StrategyCreateRequest

    rules = build_rules_json(
        StrategyCreateRequest(
            name="SMC",
            symbol="RELIANCE",
            strategy_type="smc_intraday",
            entry_mode="order_block",
            timeframe="5m",
            action="AUTO",
            qty=2,
            target_rr=2.5,
        )
    )
    assert "smc_intraday" in rules
    assert "order_block" in rules
    assert '"qty":2' in rules.replace(" ", "")


def test_build_rules_json_rejects_invalid_payload():
    import pytest
    from app.schemas.trading import StrategyCreateRequest
    from app.services.strategy_service import build_rules_json, parse_rules

    with pytest.raises(ValueError, match="Invalid rules_json"):
        build_rules_json(StrategyCreateRequest(name="Bad", rules_json="not-json"))

    with pytest.raises(ValueError, match="JSON object"):
        parse_rules("[1, 2, 3]")

    with pytest.raises(ValueError, match="qty"):
        parse_rules('{"action": "BUY", "qty": "abc"}')
