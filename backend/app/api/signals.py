from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.database import get_db
from app.models import Signal, User
from app.schemas.trading import PlaceOrderRequest, SignalResponse, SignalRouteRequest
from app.services import billing_service
from app.services.signal_service import signal_service
from app.services.order_service import order_service

router = APIRouter(prefix="/signals", tags=["AI Signals"])


@router.get("/", response_model=list[SignalResponse])
async def list_signals(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Signal).where(Signal.user_id == current_user.id).order_by(Signal.created_at.desc()).limit(50)
    )
    return list(result.scalars().all())


@router.post("/generate", response_model=list[SignalResponse])
async def generate_signals(
    symbols: str = Query(default="RELIANCE,TCS,INFY,HDFCBANK"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    sub = await billing_service.active_subscription(db, current_user)
    if not sub:
        raise HTTPException(status_code=402, detail="Active subscription required for AI signals")
    return await signal_service.fetch_and_store(db, current_user, symbols)


@router.post("/{signal_id}/route")
async def route_signal(
    signal_id: str,
    data: SignalRouteRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from uuid import UUID

    try:
        signal_uuid = UUID(signal_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Signal not found") from exc
    signal = (
        await db.execute(select(Signal).where(Signal.id == signal_uuid, Signal.user_id == current_user.id))
    ).scalar_one_or_none()
    if not signal:
        raise HTTPException(status_code=404, detail="Signal not found")
    if signal.status not in {"ACTIVE", "ROUTABLE"}:
        raise HTTPException(status_code=409, detail="Signal is no longer routable")
    if signal.action not in {"BUY", "SELL"}:
        raise HTTPException(status_code=400, detail="Only BUY and SELL signals can be routed")
    live = data.mode == "live"
    if live and data.broker == "paper":
        raise HTTPException(status_code=400, detail="A live signal route requires a configured live broker")
    order = await order_service.place_order(
        db,
        current_user,
        PlaceOrderRequest(
            symbol=signal.symbol,
            exchange=signal.exchange,
            side=signal.action,
            quantity=data.quantity,
            price=signal.price,
            paper_mode=not live,
            broker="paper" if not live else data.broker,
            live_confirmation=data.live_confirmation,
        ),
        request=request,
        source="signal",
    )
    signal.routed_order_id = order.id
    # A rejected live attempt must not be relabeled as paper execution; doing
    # so would hide a failed live gate from callers and audit consumers.
    signal.execution_mode = "LIVE" if live else "PAPER"
    signal.status = "ROUTED" if order.status != "REJECTED" else "ACTIVE"
    return {"signal_id": str(signal.id), "order_id": str(order.id), "status": order.status, "message": order.message}
