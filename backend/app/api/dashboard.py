from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.database import get_db
from app.models import BrokerConnection, Order, Signal, Strategy, User
from app.services import billing_service

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/summary")
async def dashboard_summary(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    orders_count = await db.scalar(select(func.count()).select_from(Order).where(Order.user_id == current_user.id))
    strategies_count = await db.scalar(
        select(func.count()).select_from(Strategy).where(Strategy.user_id == current_user.id)
    )
    signals_count = await db.scalar(select(func.count()).select_from(Signal).where(Signal.user_id == current_user.id))
    brokers = await db.execute(
        select(BrokerConnection).where(BrokerConnection.user_id == current_user.id)
    )
    broker_status = {
        "dhan": "not_connected",
        "groww": "not_connected",
        "fyers": "not_connected",
        "upstox": "not_connected",
    }
    for conn in brokers.scalars():
        broker_status[conn.broker.value] = conn.health_status

    latest_signals = await db.execute(
        select(Signal).where(Signal.user_id == current_user.id).order_by(Signal.created_at.desc()).limit(5)
    )
    latest_orders = await db.execute(
        select(Order).where(Order.user_id == current_user.id).order_by(Order.created_at.desc()).limit(5)
    )
    sub = await billing_service.active_subscription(db, current_user)

    return {
        "user": current_user.full_name or current_user.email,
        "orders_count": orders_count or 0,
        "active_strategies": strategies_count or 0,
        "signals_count": signals_count or 0,
        "broker_status": broker_status,
        "recent_signals": [
            {"symbol": s.symbol, "action": s.action, "confidence": s.confidence} for s in latest_signals.scalars()
        ],
        "recent_orders": [
            {"symbol": o.symbol, "side": o.side, "status": o.status, "quantity": o.quantity}
            for o in latest_orders.scalars()
        ],
        "disclaimer": "Not investment advice. For educational purposes only.",
        "mfa_enabled": current_user.mfa_enabled,
        "email_verified": current_user.is_verified,
        "is_admin": current_user.is_admin,
        "subscription": (
            {"active": True, "plan_code": sub.plan_code, "expires_at": sub.expires_at} if sub else {"active": False}
        ),
        "next_steps": [
            {
                "id": "subscribe",
                "title": "Subscribe (UPI)",
                "done": sub is not None,
                "href": "/subscribe",
                "detail": "₹199 / 1 day · ₹999 / 5 days · ₹1,999 / 22 days. PhonePe, GPay, Paytm.",
            },
            {
                "id": "mfa",
                "title": "Enable MFA",
                "done": current_user.mfa_enabled,
                "href": "/settings#mfa",
                "detail": "Use Google Authenticator or Authy before live orders.",
            },
            {
                "id": "dhan",
                "title": "Connect Dhan (paper first)",
                "done": broker_status.get("dhan") not in (None, "not_connected"),
                "href": "/settings#broker",
                "detail": "Save encrypted API token. Live orders need Dhan static IP.",
            },
            {
                "id": "paper",
                "title": "Place a paper order",
                "done": (orders_count or 0) > 0,
                "href": "/orders",
                "detail": "No real money. Confirms the order path.",
            },
            {
                "id": "groww",
                "title": "Optional: Connect Groww",
                "done": broker_status.get("groww") not in (None, "not_connected"),
                "href": "/settings#broker",
                "detail": "Needs a Groww Trading API subscription.",
            },
        ],
    }
