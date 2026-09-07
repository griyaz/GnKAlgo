from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timezone

from app.brokers.factory import get_broker_adapter
from app.models import BrokerConnection, BrokerType, User


class PortfolioService:
    async def _active_connection(self, db: AsyncSession, user: User, broker: str) -> BrokerConnection | None:
        result = await db.execute(
            select(BrokerConnection).where(
                BrokerConnection.user_id == user.id,
                BrokerConnection.broker == BrokerType(broker),
                BrokerConnection.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none()

    async def funds(self, db: AsyncSession, user: User, broker: str = "dhan") -> dict:
        conn = await self._active_connection(db, user, broker)
        if not conn:
            return {"connected": False, "broker": broker, "data": None, "error": "Broker not connected"}
        try:
            adapter = get_broker_adapter(conn)
            raw = await adapter.get_funds()
            return {"connected": True, "broker": broker, "data": raw, "updated_at": None}
        except Exception as exc:
            return {"connected": True, "broker": broker, "data": None, "error": str(exc)}

    async def positions(self, db: AsyncSession, user: User, broker: str = "dhan") -> dict:
        conn = await self._active_connection(db, user, broker)
        if not conn:
            return {"connected": False, "broker": broker, "items": [], "error": "Broker not connected"}
        try:
            adapter = get_broker_adapter(conn)
            items = await adapter.get_positions()
            return {"connected": True, "broker": broker, "items": items}
        except Exception as exc:
            return {"connected": True, "broker": broker, "items": [], "error": str(exc)}

    async def holdings(self, db: AsyncSession, user: User, broker: str = "dhan") -> dict:
        conn = await self._active_connection(db, user, broker)
        if not conn:
            return {"connected": False, "broker": broker, "items": [], "error": "Broker not connected"}
        try:
            adapter = get_broker_adapter(conn)
            items = await adapter.get_holdings()
            return {"connected": True, "broker": broker, "items": items}
        except Exception as exc:
            return {"connected": True, "broker": broker, "items": [], "error": str(exc)}

    async def broker_orders(self, db: AsyncSession, user: User, broker: str = "dhan") -> dict:
        conn = await self._active_connection(db, user, broker)
        if not conn:
            return {"connected": False, "broker": broker, "items": [], "error": "Broker not connected"}
        try:
            adapter = get_broker_adapter(conn)
            items = await adapter.get_orders()
            return {"connected": True, "broker": broker, "items": items}
        except Exception as exc:
            return {"connected": True, "broker": broker, "items": [], "error": str(exc)}

    async def broker_status(self, db: AsyncSession, user: User, broker: str = "dhan") -> dict:
        conn = await self._active_connection(db, user, broker)
        if not conn:
            return {
                "broker": broker,
                "status": "disconnected",
                "client_id": None,
                "health_status": "not_connected",
                "last_health_check": None,
            }
        healthy = False
        error = None
        try:
            adapter = get_broker_adapter(conn)
            healthy = await adapter.health_check()
        except Exception as exc:
            error = str(exc)
        conn.last_health_check = datetime.now(timezone.utc)
        conn.health_status = "connected" if healthy else "error"
        return {
            "broker": broker,
            "status": "connected" if healthy else "error",
            "client_id": conn.client_id,
            "health_status": conn.health_status,
            "last_health_check": conn.last_health_check,
            "error": error,
        }


portfolio_service = PortfolioService()
