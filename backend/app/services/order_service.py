import uuid
from datetime import datetime, timezone

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.brokers.base import OrderRequest as BrokerOrderRequest
from app.brokers.factory import get_broker_adapter
from app.core.deps import log_audit
from app.core.security import generate_secure_token
from app.models import BrokerConnection, BrokerType, Order, TradingControl, User
from app.config import settings
from app.schemas.trading import PlaceOrderRequest
from app.services import billing_service
from app.services.instrument_segments import dhan_exchange_segment
from app.services.instrument_service import instrument_service
from app.services.risk import RiskRejection, validate_order


class OrderService:
    async def list_orders(self, db: AsyncSession, user: User) -> list[Order]:
        result = await db.execute(
            select(Order).where(Order.user_id == user.id).order_by(Order.created_at.desc())
        )
        return list(result.scalars().all())

    async def _reject(
        self,
        db: AsyncSession,
        user: User,
        data: PlaceOrderRequest,
        reason: str,
        strategy_id: uuid.UUID | None,
        webhook_id: uuid.UUID | None,
        source: str,
    ) -> Order:
        order = Order(
            user_id=user.id,
            broker=data.broker,
            symbol=data.symbol.upper(),
            exchange=data.exchange,
            side=data.side,
            quantity=data.quantity,
            order_type=data.order_type,
            price=data.price,
            product_type=data.product_type,
            status="REJECTED",
            correlation_id=data.correlation_id or generate_secure_token()[:16],
            strategy_id=strategy_id,
            webhook_id=webhook_id,
            source=source,
            message=reason,
        )
        db.add(order)
        await db.flush()
        return order

    async def place_order(
        self,
        db: AsyncSession,
        user: User,
        data: PlaceOrderRequest,
        request: Request | None = None,
        source: str = "manual",
        strategy_id: uuid.UUID | None = None,
        webhook_id: uuid.UUID | None = None,
    ) -> Order:
        paper = data.paper_mode or data.broker == "paper"
        try:
            validate_order(quantity=data.quantity, paper_mode=paper)
        except RiskRejection as exc:
            return await self._reject(db, user, data, exc.reason, strategy_id, webhook_id, source)

        if not paper:
            control = await db.get(TradingControl, 1)
            if not control or control.kill_switch_active:
                return await self._reject(db, user, data, "Emergency kill switch is active", strategy_id, webhook_id, source)
            # Typed confirmation is a UI guard against accidental clicks. Webhooks and
            # scheduled strategies are already authorized by HMAC / strategy config.
            if source == "manual" and data.live_confirmation != "CONFIRM LIVE ORDER":
                return await self._reject(db, user, data, "Type CONFIRM LIVE ORDER to authorize this live order", strategy_id, webhook_id, source)
            if data.broker == "dhan" and not settings.dhan_static_ip.strip():
                return await self._reject(db, user, data, "Dhan static public IP is not configured and allowlisting is unverified", strategy_id, webhook_id, source)
            sub = await billing_service.active_subscription(db, user)
            if not sub:
                return await self._reject(
                    db, user, data, "Active subscription required for live trading",
                    strategy_id, webhook_id, source,
                )

        order = Order(
            user_id=user.id,
            broker=data.broker,
            symbol=data.symbol.upper(),
            exchange=data.exchange,
            side=data.side,
            quantity=data.quantity,
            order_type=data.order_type,
            price=data.price,
            product_type=data.product_type,
            status="PENDING",
            correlation_id=data.correlation_id or generate_secure_token()[:16],
            strategy_id=strategy_id,
            webhook_id=webhook_id,
            source=source,
        )
        db.add(order)
        await db.flush()

        if paper:
            order.status = "PAPER_FILLED"
            order.broker = "paper"
            order.message = "Paper fill — no live broker call"
            if request:
                await log_audit(db, "order.paper_filled", user.id, request, {"order_id": str(order.id)})
            return order

        if not user.mfa_enabled:
            order.status = "REJECTED"
            order.message = "Enable MFA in Settings before placing live orders"
            return order

        inst = await instrument_service.resolve(db, order.symbol, order.exchange)
        if not inst:
            inst = instrument_service.curated_fallback(order.symbol)
        if not inst or not inst.get("security_id"):
            order.status = "REJECTED"
            order.message = f"Unknown instrument {order.symbol} on {order.exchange}"
            return order

        conn_result = await db.execute(
            select(BrokerConnection).where(
                BrokerConnection.user_id == user.id,
                BrokerConnection.broker == BrokerType(data.broker),
                BrokerConnection.is_active.is_(True),
            )
        )
        connection = conn_result.scalar_one_or_none()
        if not connection:
            order.status = "REJECTED"
            order.message = f"No active {data.broker} connection"
            return order

        segment = inst.get("segment") or "EQUITY"
        exchange_segment = inst.get("exchange_segment") or dhan_exchange_segment(
            inst.get("exchange", order.exchange), segment
        )
        try:
            adapter = get_broker_adapter(connection)
            response = await adapter.place_order(
                BrokerOrderRequest(
                    symbol=order.symbol,
                    exchange=order.exchange,
                    side=order.side,
                    quantity=order.quantity,
                    order_type=order.order_type,
                    price=order.price,
                    product_type=order.product_type,
                    correlation_id=order.correlation_id,
                    security_id=str(inst["security_id"]),
                    exchange_segment=exchange_segment,
                )
            )
            order.broker_order_id = response.broker_order_id
            order.status = response.status or "PENDING"
            order.message = response.message
        except Exception as exc:
            order.status = "REJECTED"
            order.message = str(exc)

        if request:
            await log_audit(db, "order.placed", user.id, request, {"order_id": str(order.id), "status": order.status})
        return order


order_service = OrderService()
