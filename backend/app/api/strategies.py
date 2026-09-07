from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.database import get_db
from app.models import StrategyVersion, User
from app.schemas.trading import StrategyCreateRequest, StrategyResponse, StrategyUpdateRequest, StrategyVersionResponse
from app.services.strategy_service import strategy_service

router = APIRouter(prefix="/strategies", tags=["Strategies"])


@router.get("/", response_model=list[StrategyResponse])
async def list_strategies(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await strategy_service.list_strategies(db, current_user)


@router.post("/", response_model=StrategyResponse)
async def create_strategy(
    data: StrategyCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await strategy_service.create(db, current_user, data)
    except ValueError as exc:
        code = 402 if "subscription" in str(exc).lower() else 400
        raise HTTPException(status_code=code, detail=str(exc))


@router.put("/{strategy_id}", response_model=StrategyResponse)
async def update_strategy(
    strategy_id: UUID,
    data: StrategyUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await strategy_service.update(db, current_user, strategy_id, data)
    except ValueError as exc:
        if "not found" in str(exc).lower():
            raise HTTPException(status_code=404, detail=str(exc))
        code = 402 if "subscription" in str(exc).lower() else 400
        raise HTTPException(status_code=code, detail=str(exc))


@router.post("/{strategy_id}/status")
async def update_status(
    strategy_id: UUID,
    status: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        strategy = await strategy_service.set_status(db, current_user, strategy_id, status)
    except ValueError as exc:
        code = 404 if "not found" in str(exc).lower() else 400
        raise HTTPException(status_code=code, detail=str(exc))
    return strategy


@router.post("/{strategy_id}/run")
async def run_strategy(
    strategy_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        run = await strategy_service.run_once(db, current_user, strategy_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"run_id": str(run.id), "status": run.status, "notes": run.notes}


@router.get("/{strategy_id}/versions", response_model=list[StrategyVersionResponse])
async def list_versions(
    strategy_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # The version table is queried with an ownership subquery to avoid exposing
    # another user's immutable rules.
    from app.models import Strategy

    owned = (
        await db.execute(select(Strategy.id).where(Strategy.id == strategy_id, Strategy.user_id == current_user.id))
    ).scalar_one_or_none()
    if not owned:
        raise HTTPException(status_code=404, detail="Strategy not found")
    result = await db.execute(
        select(StrategyVersion)
        .where(StrategyVersion.strategy_id == strategy_id)
        .order_by(StrategyVersion.version.desc())
    )
    return list(result.scalars())
