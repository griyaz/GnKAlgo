import uuid

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.brokers.base import OrderRequest as BrokerOrderRequest
from app.brokers.factory import get_broker_adapter
from app.core.deps import log_audit
from app.core.security import generate_secure_token
from app.models import BrokerConnection, BrokerType, Order, User
from app.config import settings
from app.schemas.trading import PlaceOrderRequest
from app.services.instrument_segments import dhan_exchange_segment
from app.services.instrument_service import instrument_service
from app.services.order_status import normalize_broker_status
from app.services.live_trading import check_live_trading_gates
from app.services import billing_service
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
        request: Request | None = None,
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
        await log_audit(
            db,
            "order.rejected",
            user.id,
            request,
            {"order_id": str(order.id), "reason": reason, "source": source},
        )
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
        max_quantity: int | None = None,
    ) -> Order:
        paper = data.paper_mode or data.broker == "paper"
        try:
            order_max_quantity = (
                max_quantity
                if max_quantity is not None
                else (settings.live_max_order_quantity if not paper else 10000)
            )
            validate_order(
                quantity=data.quantity,
                max_quantity=order_max_quantity,
                paper_mode=paper,
            )
        except RiskRejection as exc:
            return await self._reject(db, user, data, exc.reason, strategy_id, webhook_id, source, request)

        if not paper:
            # Typed confirmation is a UI guard against accidental clicks. Webhooks and
            # scheduled strategies are already authorized by HMAC / strategy config.
            if source == "manual" and data.live_confirmation != "CONFIRM LIVE ORDER":
                confirmation_reason = "Type CONFIRM LIVE ORDER to authorize this live order"
                if not await billing_service.active_subscription(db, user):
                    confirmation_reason += "; Active subscription required for live trading"
                return await self._reject(db, user, data, confirmation_reason, strategy_id, webhook_id, source, request)
            gate = await check_live_trading_gates(
                db,
                user,
                data.broker,
                quantity=data.quantity,
                side=data.side,
                price=data.price,
            )
            if not gate.allowed:
                return await self._reject(
                    db, user, data, gate.reason or "Live trading gate rejected the order",
                    strategy_id, webhook_id, source, request,
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
            # This is retained as a defensive check for callers that construct
            # an order service request without going through the gate helper.
            order.status = "REJECTED"
            order.message = "Enable MFA in Settings before placing live orders"
            if request:
                await log_audit(db, "order.live_rejected", user.id, request, {"order_id": str(order.id), "reason": order.message})
            return order

        inst = await instrument_service.resolve(db, order.symbol, order.exchange)
        if not inst:
            inst = instrument_service.curated_fallback(order.symbol)
        if not inst or not inst.get("security_id"):
            order.status = "REJECTED"
            order.message = f"Unknown instrument {order.symbol} on {order.exchange}"
            await log_audit(db, "order.rejected", user.id, request, {"order_id": str(order.id), "reason": order.message, "source": source})
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
            await log_audit(db, "order.rejected", user.id, request, {"order_id": str(order.id), "reason": order.message, "source": source})
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
            # Dhan returns TRADED/TRANSIT/PENDING — persist a status the rest of
            # the platform (daily-loss, run completion) actually recognizes.
            order.status = normalize_broker_status(response.status)
            order.message = response.message
        except Exception as exc:
            order.status = "REJECTED"
            order.message = str(exc)

        if request:
            await log_audit(db, "order.placed", user.id, request, {"order_id": str(order.id), "status": order.status})
        return order


order_service = OrderService()
