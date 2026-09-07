"""Deterministic, no-lookahead backtesting primitives.

Signals are derived from the *previous* completed candle and orders fill at the
next candle open.  The engine intentionally accepts data, not executable code.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone


def _time(value) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return datetime.fromtimestamp(int(value), tz=timezone.utc)


def run_backtest(
    rules: dict,
    candles: list[dict],
    *,
    initial_capital: float,
    quantity: int = 1,
    commission_bps: float = 0,
    slippage_bps: float = 0,
) -> dict:
    if len(candles) < 2:
        raise ValueError("At least two candles are required")
    normalized = []
    previous_time = None
    for candle in candles:
        required = ("time", "open", "high", "low", "close")
        if not all(key in candle for key in required):
            raise ValueError("Each candle requires time, open, high, low and close")
        item = {key: float(candle[key]) if key != "time" else _time(candle[key]) for key in required}
        if item["high"] < max(item["open"], item["close"]) or item["low"] > min(item["open"], item["close"]):
            raise ValueError("Invalid candle OHLC values")
        if previous_time and item["time"] <= previous_time:
            raise ValueError("Candles must be strictly chronological with no duplicates")
        previous_time = item["time"]
        normalized.append(item)

    action = rules.get("action", "BUY")
    if action not in ("BUY", "SELL"):
        action = "BUY"
    stop_pct = float(rules.get("stop_loss_pct", rules.get("stop_loss_buffer_pct", 1.0))) / 100
    target_pct = float(rules.get("target_pct", 2.0)) / 100
    if stop_pct <= 0 or target_pct <= 0:
        raise ValueError("stop_loss_pct and target_pct must be positive")

    cash = float(initial_capital)
    equity_peak = cash
    max_drawdown = 0.0
    position = None
    trades = []
    equity_curve = [cash]
    friction = (commission_bps + slippage_bps) / 10000

    def fill_price(price: float, side: str) -> float:
        return price * (1 + friction if side == "BUY" else 1 - friction)

    def close_position(candle, price: float, reason: str):
        nonlocal cash, position
        side = position["side"]
        signed = 1 if side == "BUY" else -1
        exit_side = "SELL" if side == "BUY" else "BUY"
        executed = fill_price(price, exit_side)
        pnl = signed * quantity * (executed - position["price"])
        cash += pnl
        trades.append(
            {
                "side": side,
                "quantity": quantity,
                "entry_time": position["time"],
                "entry_price": position["price"],
                "exit_time": candle["time"],
                "exit_price": executed,
                "pnl": round(pnl, 8),
                "reason": reason,
            }
        )
        position = None

    # i only reads normalized[i - 1] for the decision and normalized[i] for fill.
    for i in range(1, len(normalized)):
        candle = normalized[i]
        if position is None:
            entry_side = "BUY" if action == "BUY" else "SELL"
            entry = fill_price(candle["open"], entry_side)
            position = {"side": entry_side, "price": entry, "time": candle["time"]}
            signed = 1 if entry_side == "BUY" else -1
            position["stop"] = entry * (1 - stop_pct if signed == 1 else 1 + stop_pct)
            position["target"] = entry * (1 + target_pct if signed == 1 else 1 - target_pct)
            continue
        if position["side"] == "BUY":
            if candle["low"] <= position["stop"]:
                close_position(candle, position["stop"], "STOP_LOSS")
            elif candle["high"] >= position["target"]:
                close_position(candle, position["target"], "TARGET")
        elif candle["high"] >= position["stop"]:
            close_position(candle, position["stop"], "STOP_LOSS")
        elif candle["low"] <= position["target"]:
            close_position(candle, position["target"], "TARGET")
        mark = cash
        if position:
            signed = 1 if position["side"] == "BUY" else -1
            mark += signed * quantity * (candle["close"] - position["price"])
        equity_curve.append(mark)
        equity_peak = max(equity_peak, mark)
        max_drawdown = max(max_drawdown, equity_peak - mark)

    if position:
        close_position(normalized[-1], normalized[-1]["close"], "END_OF_DATA")
        equity_curve.append(cash)
    total_return = cash - float(initial_capital)
    wins = sum(1 for trade in trades if trade["pnl"] > 0)
    return {
        "initial_capital": float(initial_capital),
        "final_equity": round(cash, 8),
        "total_return": round(total_return, 8),
        "max_drawdown": round(max_drawdown, 8),
        "trade_count": len(trades),
        "metrics": {
            "win_rate": round(wins / len(trades), 6) if trades else 0.0,
            "profitable_trades": wins,
            "losses": len(trades) - wins,
            "equity_curve": [round(value, 8) for value in equity_curve],
        },
        "trades": trades,
    }


def fingerprint(rules: dict, candles: list[dict], **parameters) -> str:
    payload = json.dumps({"rules": rules, "candles": candles, "parameters": parameters}, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
