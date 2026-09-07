"""Broker-independent paper execution with explicit risk limits."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Order, PaperFill, PaperPosition, PaperTradingRun, User
from app.schemas.trading import PaperOrderRequest


class PaperTradingService:
    async def start(self, db: AsyncSession, user: User, data) -> PaperTradingRun:
        run = PaperTradingRun(
            user_id=user.id,
            strategy_id=data.strategy_id,
            initial_cash=data.initial_cash,
            cash=data.initial_cash,
            max_daily_loss=data.max_daily_loss,
            max_position_qty=data.max_position_qty,
        )
        db.add(run)
        await db.flush()
        return run

    async def stop(self, db: AsyncSession, user: User, run_id: uuid.UUID) -> PaperTradingRun:
        run = await self._owned_run(db, user, run_id)
        if not run:
            raise ValueError("Paper run not found")
        run.status = "STOPPED"
        run.finished_at = datetime.now(timezone.utc)
        return run

    async def _owned_run(self, db, user, run_id):
        result = await db.execute(select(PaperTradingRun).where(PaperTradingRun.id == run_id, PaperTradingRun.user_id == user.id))
        return result.scalar_one_or_none()

    async def fill(
        self, db: AsyncSession, user: User, run_id: uuid.UUID, data: PaperOrderRequest
    ) -> tuple[PaperTradingRun, PaperFill, PaperPosition]:
        run = await self._owned_run(db, user, run_id)
        if not run:
            raise ValueError("Paper run not found")
        if run.status != "ACTIVE":
            raise ValueError("Paper run is not active")
        result = await db.execute(
            select(PaperPosition).where(PaperPosition.run_id == run.id, PaperPosition.symbol == data.symbol.upper())
        )
        position = result.scalar_one_or_none()
        if not position:
            position = PaperPosition(run_id=run.id, symbol=data.symbol.upper())
            db.add(position)
            await db.flush()

        current_qty = position.quantity
        signed_qty = data.quantity if data.side == "BUY" else -data.quantity
        next_qty = current_qty + signed_qty
        if abs(next_qty) > run.max_position_qty:
            raise ValueError("Paper position limit exceeded")
        notional = data.quantity * data.price
        fee = notional * 0.0001
        if data.side == "BUY" and run.cash < notional + fee:
            raise ValueError("Insufficient paper cash")

        if data.side == "BUY":
            run.cash -= notional + fee
            if current_qty >= 0:
                position.average_price = (
                    (current_qty * position.average_price + notional) / next_qty if next_qty else 0
                )
            else:
                close_qty = min(abs(current_qty), data.quantity)
                position.realized_pnl += close_qty * (position.average_price - data.price)
                if next_qty > 0:
                    position.average_price = data.price
        else:
            run.cash += notional - fee
            if current_qty > 0:
                close_qty = min(current_qty, data.quantity)
                position.realized_pnl += close_qty * (data.price - position.average_price)
                if next_qty < 0:
                    position.average_price = data.price
            elif current_qty < 0:
                position.average_price = (
                    (abs(current_qty) * position.average_price + notional) / abs(next_qty) if next_qty else 0
                )
            elif next_qty < 0:
                position.average_price = data.price
        position.quantity = next_qty
        position.last_price = data.price
        position.updated_at = datetime.now(timezone.utc)
        # Recalculate from persisted positions without relying on relationship state.
        positions = list((await db.execute(select(PaperPosition).where(PaperPosition.run_id == run.id))).scalars())
        run.realized_pnl = sum(row.realized_pnl for row in positions)
        run.unrealized_pnl = sum(
            row.quantity * ((row.last_price or row.average_price) - row.average_price)
            for row in positions
            if row.quantity
        )
        if run.realized_pnl + run.unrealized_pnl < -run.max_daily_loss:
            run.status = "STOPPED"
            run.finished_at = datetime.now(timezone.utc)
            raise ValueError("Paper max daily loss reached; run stopped")

        order = Order(
            user_id=user.id,
            broker="paper",
            symbol=data.symbol.upper(),
            exchange=data.exchange,
            side=data.side,
            quantity=data.quantity,
            order_type="MARKET",
            price=data.price,
            product_type="INTRADAY",
            status="PAPER_FILLED",
            source="paper_run",
            message=f"Simulated fill for run {run.id}",
        )
        db.add(order)
        await db.flush()
        fill = PaperFill(
            run_id=run.id,
            order_id=order.id,
            symbol=data.symbol.upper(),
            side=data.side,
            quantity=data.quantity,
            price=data.price,
            fee=fee,
        )
        db.add(fill)
        await db.flush()
        return run, fill, position


paper_service = PaperTradingService()
