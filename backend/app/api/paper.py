import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.database import get_db
from app.models import PaperPosition, PaperTradingRun, User
from app.schemas.trading import PaperOrderRequest, PaperRunCreateRequest, PaperRunResponse, PaperPositionResponse
from app.services.paper_service import paper_service

router = APIRouter(prefix="/paper", tags=["Paper Trading"])


async def _response(db, run: PaperTradingRun) -> PaperRunResponse:
    positions = list(
        (
            await db.execute(
                select(PaperPosition).where(PaperPosition.run_id == run.id, PaperPosition.quantity != 0).order_by(PaperPosition.symbol)
            )
        ).scalars()
    )
    return PaperRunResponse(
        id=run.id,
        strategy_id=run.strategy_id,
        status=run.status,
        initial_cash=run.initial_cash,
        cash=run.cash,
        realized_pnl=run.realized_pnl,
        unrealized_pnl=run.unrealized_pnl,
        max_daily_loss=run.max_daily_loss,
        max_position_qty=run.max_position_qty,
        started_at=run.started_at,
        finished_at=run.finished_at,
        positions=[PaperPositionResponse.model_validate(position, from_attributes=True) for position in positions],
    )


@router.post("/runs", response_model=PaperRunResponse)
async def start_run(
    data: PaperRunCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if data.strategy_id:
        from app.models import Strategy

        strategy = (
            await db.execute(select(Strategy).where(Strategy.id == data.strategy_id, Strategy.user_id == current_user.id))
        ).scalar_one_or_none()
        if not strategy:
            raise HTTPException(status_code=404, detail="Strategy not found")
    run = await paper_service.start(db, current_user, data)
    return await _response(db, run)


@router.get("/runs", response_model=list[PaperRunResponse])
async def list_runs(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    rows = list(
        (
            await db.execute(
                select(PaperTradingRun)
                .where(PaperTradingRun.user_id == current_user.id)
                .order_by(PaperTradingRun.started_at.desc())
                .limit(50)
            )
        ).scalars()
    )
    return [await _response(db, row) for row in rows]


@router.post("/runs/{run_id}/orders", response_model=PaperRunResponse)
async def place_paper_order(
    run_id: uuid.UUID,
    data: PaperOrderRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        run, _, _ = await paper_service.fill(db, current_user, run_id, data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return await _response(db, run)


@router.post("/runs/{run_id}/stop", response_model=PaperRunResponse)
async def stop_run(
    run_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        run = await paper_service.stop(db, current_user, run_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return await _response(db, run)
