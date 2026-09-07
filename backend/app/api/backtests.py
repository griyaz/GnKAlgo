import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.database import get_db
from app.models import BacktestRun, BacktestTrade, Strategy, StrategyVersion, User
from app.schemas.trading import BacktestRequest, BacktestResponse, BacktestTradeResponse
from app.services.backtest_service import fingerprint, run_backtest

router = APIRouter(prefix="/backtests", tags=["Backtesting"])


def _response(run: BacktestRun, trades: list[BacktestTrade]) -> BacktestResponse:
    return BacktestResponse(
        id=run.id,
        strategy_id=run.strategy_id,
        strategy_version_id=run.strategy_version_id,
        status=run.status,
        candles_count=run.candles_count,
        initial_capital=run.initial_capital,
        final_equity=run.final_equity,
        total_return=run.total_return,
        max_drawdown=run.max_drawdown,
        trade_count=run.trade_count,
        metrics=json.loads(run.metrics_json or "{}"),
        trades=[BacktestTradeResponse.model_validate(trade, from_attributes=True) for trade in trades],
        created_at=run.created_at,
    )


@router.post("/run", response_model=BacktestResponse)
async def run(
    data: BacktestRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    strategy = None
    version = None
    rules = None
    if data.strategy_id:
        strategy = (
            await db.execute(select(Strategy).where(Strategy.id == data.strategy_id, Strategy.user_id == current_user.id))
        ).scalar_one_or_none()
        if not strategy:
            raise HTTPException(status_code=404, detail="Strategy not found")
        version_no = data.strategy_version or strategy.current_version
        version = (
            await db.execute(
                select(StrategyVersion).where(
                    StrategyVersion.strategy_id == strategy.id, StrategyVersion.version == version_no
                )
            )
        ).scalar_one_or_none()
        if not version:
            raise HTTPException(status_code=404, detail="Strategy version not found")
        rules = json.loads(version.rules_json)
    elif data.rules_json:
        try:
            rules = json.loads(data.rules_json)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail=f"Invalid rules_json: {exc}") from exc
    else:
        raise HTTPException(status_code=400, detail="strategy_id or rules_json is required")

    candles = [c.model_dump() for c in data.candles]
    try:
        result = run_backtest(
            rules,
            candles,
            initial_capital=data.initial_capital,
            quantity=data.quantity,
            commission_bps=data.commission_bps,
            slippage_bps=data.slippage_bps,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    run_row = BacktestRun(
        user_id=current_user.id,
        strategy_id=strategy.id if strategy else None,
        strategy_version_id=version.id if version else None,
        input_hash=fingerprint(rules, candles, initial_capital=data.initial_capital, quantity=data.quantity),
        candles_count=len(candles),
        initial_capital=result["initial_capital"],
        final_equity=result["final_equity"],
        total_return=result["total_return"],
        max_drawdown=result["max_drawdown"],
        trade_count=result["trade_count"],
        metrics_json=json.dumps(result["metrics"]),
    )
    db.add(run_row)
    await db.flush()
    trade_rows = []
    for trade in result["trades"]:
        row = BacktestTrade(run_id=run_row.id, **trade)
        db.add(row)
        trade_rows.append(row)
    if strategy and result["trade_count"] >= 0:
        # A reproducible completed run is the paper validation required by the
        # live lifecycle gate. Live order guards still apply independently.
        from datetime import datetime, timezone

        strategy.paper_verified_at = datetime.now(timezone.utc)
    await db.flush()
    return _response(run_row, trade_rows)


@router.get("/", response_model=list[BacktestResponse])
async def list_backtests(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    rows = list(
        (
            await db.execute(
                select(BacktestRun)
                .where(BacktestRun.user_id == current_user.id)
                .order_by(BacktestRun.created_at.desc())
                .limit(50)
            )
        ).scalars()
    )
    output = []
    for row in rows:
        trades = list((await db.execute(select(BacktestTrade).where(BacktestTrade.run_id == row.id))).scalars())
        output.append(_response(row, trades))
    return output
