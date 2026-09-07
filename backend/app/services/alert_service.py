from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Alert, AlertEvent, User
from app.services.market_quote_cache import get_by_symbol


def _matches(value: float, operator: str, threshold: float) -> bool:
    return {
        ">": value > threshold,
        ">=": value >= threshold,
        "<": value < threshold,
        "<=": value <= threshold,
    }[operator]


class AlertService:
    async def list(self, db: AsyncSession, user: User) -> list[Alert]:
        result = await db.execute(
            select(Alert)
            .where(Alert.user_id == user.id)
            .order_by(Alert.created_at.desc())
            .limit(100)
        )
        return list(result.scalars().all())

    async def create(self, db: AsyncSession, user: User, data) -> Alert:
        alert = Alert(user_id=user.id, symbol=data.symbol.upper(), exchange=data.exchange.upper(),
                      condition=data.condition, operator=data.operator,
                      threshold=data.threshold, recurring=data.recurring)
        db.add(alert)
        await db.flush()
        return alert

    async def update(self, db: AsyncSession, user: User, alert_id, status: str | None) -> Alert:
        alert = await db.scalar(select(Alert).where(Alert.id == alert_id, Alert.user_id == user.id))
        if not alert:
            raise ValueError("Alert not found")
        if status:
            alert.status = status
        await db.flush()
        return alert

    async def evaluate_active(self, db: AsyncSession) -> int:
        result = await db.execute(select(Alert).where(Alert.status == "ACTIVE"))
        triggered = 0
        now = datetime.now(timezone.utc)
        for alert in result.scalars():
            quote = get_by_symbol(alert.symbol)
            value = quote.get("ltp") if quote else None
            if value is None or not _matches(float(value), alert.operator, alert.threshold):
                continue
            if alert.recurring and alert.triggered_at:
                last_trigger = alert.triggered_at
                if last_trigger.tzinfo is None:
                    last_trigger = last_trigger.replace(tzinfo=timezone.utc)
                if now - last_trigger < timedelta(minutes=1):
                    continue
            db.add(AlertEvent(alert_id=alert.id, value=float(value)))
            alert.triggered_at = now
            triggered += 1
            if not alert.recurring:
                alert.status = "TRIGGERED"
        return triggered


alert_service = AlertService()
