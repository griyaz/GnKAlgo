"""Central live-trading deployment gates.

Every live order enters this module, regardless of whether it came from the
manual API, a signal, a strategy scheduler, or an authenticated webhook.
Paper orders intentionally do not call this module.
"""

from __future__ import annotations

import ipaddress
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.brokers.factory import get_broker_adapter
from app.config import settings
from app.core.security import decrypt_data
from app.models import BrokerConnection, BrokerType, Order, TradingControl, User
from app.services import billing_service
from app.services.order_status import DEPLOYED_ORDER_STATUSES


@dataclass(frozen=True)
class LiveGateResult:
    allowed: bool
    reason: str | None = None


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def _credential_errors(broker: BrokerType, connection: BrokerConnection) -> list[str]:
    try:
        credentials = json.loads(decrypt_data(connection.encrypted_credentials))
    except Exception:
        return ["Broker credentials cannot be decrypted"]
    if not isinstance(credentials, dict):
        return ["Broker credentials are invalid"]

    token = str(credentials.get("access_token") or credentials.get("api_key") or "").strip()
    errors: list[str] = []
    if not token:
        errors.append("Broker access token is not configured")
    if broker in {BrokerType.DHAN, BrokerType.FYERS} and not (
        credentials.get("client_id") or connection.client_id
    ):
        errors.append(f"{broker.value.upper()} client ID is required")
    if broker is BrokerType.DHAN:
        if not settings.dhan_static_ip.strip():
            errors.append("Dhan static public IP is not configured")
        else:
            try:
                ipaddress.ip_address(settings.dhan_static_ip.strip())
            except ValueError:
                errors.append("Dhan static public IP is invalid")
    if broker is BrokerType.FYERS and not settings.fyers_api_base_url.startswith("https://"):
        errors.append("FYERS API base URL must use HTTPS")
    if broker is BrokerType.UPSTOX and not settings.upstox_api_base_url.startswith("https://"):
        errors.append("Upstox API base URL must use HTTPS")
    if broker is BrokerType.DHAN and not settings.dhan_api_base_url.startswith("https://"):
        errors.append("Dhan API base URL must use HTTPS")
    return errors


async def _connection_health(
    db: AsyncSession, connection: BrokerConnection
) -> str | None:
    """Refresh stale connection health, without exposing broker credentials."""
    checked = _aware(connection.last_health_check)
    now = datetime.now(timezone.utc)
    stale = checked is None or now - checked > timedelta(seconds=settings.broker_health_max_age_seconds)
    if connection.health_status != "connected" or stale:
        try:
            adapter = get_broker_adapter(connection)
            healthy = await adapter.health_check()
        except Exception:
            healthy = False
        connection.last_health_check = now
        connection.health_status = "connected" if healthy else "error"
        if not healthy:
            return "Broker connection health check failed"
    return None


async def check_live_trading_gates(
    db: AsyncSession,
    user: User,
    broker: str,
    *,
    quantity: int,
    side: str | None = None,
    price: float | None = None,
) -> LiveGateResult:
    """Evaluate all non-order-specific gates before a broker call is possible."""
    if not user.is_active:
        return LiveGateResult(False, "Account is inactive")
    if settings.app_env.strip().lower() in {"production", "prod"}:
        if not settings.live_trading_enabled:
            return LiveGateResult(False, "Live trading is disabled by deployment configuration")
        if settings.production_config_errors:
            return LiveGateResult(False, "Production deployment configuration is incomplete")
    if quantity > settings.live_max_order_quantity:
        return LiveGateResult(False, f"Quantity exceeds live risk limit ({settings.live_max_order_quantity})")

    control = await db.get(TradingControl, 1)
    if not control or control.kill_switch_active:
        return LiveGateResult(False, "Emergency kill switch is active")
    if not await billing_service.active_subscription(db, user):
        return LiveGateResult(False, "Active subscription required for live trading")
    if not user.mfa_enabled:
        return LiveGateResult(False, "Enable MFA in Settings before placing live orders")

    try:
        broker_enum = BrokerType(broker)
    except ValueError:
        return LiveGateResult(False, f"Unsupported live broker: {broker}")
    result = await db.execute(
        select(BrokerConnection).where(
            BrokerConnection.user_id == user.id,
            BrokerConnection.broker == broker_enum,
            BrokerConnection.is_active.is_(True),
        )
    )
    connection = result.scalar_one_or_none()
    if not connection:
        return LiveGateResult(False, f"No active {broker} connection")
    credential_errors = _credential_errors(broker_enum, connection)
    if credential_errors:
        return LiveGateResult(False, "; ".join(credential_errors))
    health_error = await _connection_health(db, connection)
    if health_error:
        return LiveGateResult(False, health_error)

    # A conservative daily loss guard protects direct orders as well as
    # strategies.  Unknown market prices are not invented here; the quantity
    # and per-order limits still apply.
    from zoneinfo import ZoneInfo

    now_ist = datetime.now(ZoneInfo("Asia/Kolkata"))
    start = datetime.combine(now_ist.date(), datetime.min.time(), tzinfo=ZoneInfo("Asia/Kolkata")).astimezone(
        timezone.utc
    )
    orders = await db.execute(
        select(Order).where(
            Order.user_id == user.id,
            Order.created_at >= start,
            Order.status.in_(DEPLOYED_ORDER_STATUSES),
        )
    )
    daily_loss = 0.0
    for order in orders.scalars():
        if order.price:
            cashflow = float(order.price) * order.quantity
            daily_loss += cashflow if order.side == "BUY" else -cashflow
    projected_loss = daily_loss
    if price:
        projected_loss += float(price) * quantity if side == "BUY" else -float(price) * quantity
    if projected_loss >= settings.live_daily_loss_limit:
        return LiveGateResult(False, f"Daily live risk limit {settings.live_daily_loss_limit:g} reached")
    return LiveGateResult(True)
