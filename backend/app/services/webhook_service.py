import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.security import generate_secure_token, hash_token
from app.models import Order, User, Webhook, WebhookLog
from app.schemas.trading import InboundWebhookPayload, PlaceOrderRequest, WebhookCreateRequest
from app.services import billing_service
from app.services.order_service import order_service

# TradingView and similar senders retry on timeout after the first POST already
# placed a live order. Identical payloads within this window reuse the order.
WEBHOOK_RETRY_WINDOW = timedelta(minutes=2)


def webhook_idempotency_key(webhook_id, raw_body: bytes) -> str:
    return hashlib.sha256(str(webhook_id).encode("utf-8") + b"\0" + raw_body).hexdigest()[:32]


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


class WebhookService:
    async def list_webhooks(self, db: AsyncSession, user: User) -> list[Webhook]:
        result = await db.execute(select(Webhook).where(Webhook.user_id == user.id))
        return list(result.scalars().all())

    async def create(self, db: AsyncSession, user: User, data: WebhookCreateRequest) -> tuple[Webhook, str]:
        sub = await billing_service.active_subscription(db, user)
        if not sub:
            raise ValueError("Active subscription required to create webhooks")
        raw_secret = generate_secure_token()
        webhook = Webhook(
            user_id=user.id,
            name=data.name,
            direction=data.direction,
            token=generate_secure_token()[:24],
            secret_hash=hash_token(raw_secret),
            target_url=data.target_url,
        )
        db.add(webhook)
        await db.flush()
        return webhook, raw_secret

    def inbound_url(self, token: str) -> str:
        return f"{settings.backend_public_url}/api/v1/webhooks/in/{token}"

    def verify_signature(self, secret: str, body: bytes, provided: str | None) -> bool:
        if not provided:
            return False
        expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        if len(provided) != len(expected):
            return False
        return hmac.compare_digest(expected, provided)

    async def handle_inbound(
        self,
        db: AsyncSession,
        token: str,
        payload: InboundWebhookPayload,
        request: Request,
        raw_body: bytes,
        signature: str | None,
        raw_secret: str | None,
    ) -> WebhookLog:
        result = await db.execute(
            select(Webhook)
            .where(Webhook.token == token, Webhook.is_active.is_(True), Webhook.direction == "INBOUND")
            .with_for_update()
        )
        webhook = result.scalar_one_or_none()
        if not webhook:
            raise ValueError("Webhook not found")

        if not raw_secret:
            raise ValueError("Webhook secret required")
        if not hmac.compare_digest(hash_token(raw_secret), webhook.secret_hash):
            raise ValueError("Invalid webhook secret")
        if not signature or not self.verify_signature(raw_secret, raw_body, signature):
            raise ValueError("HMAC signature required")

        user_result = await db.execute(select(User).where(User.id == webhook.user_id))
        user = user_result.scalar_one()
        if not user.is_active:
            raise ValueError("Webhook owner inactive")

        idempotency_key = webhook_idempotency_key(webhook.id, raw_body)
        prior = await self._recent_order(db, webhook.id, idempotency_key)
        if prior:
            log = WebhookLog(
                webhook_id=webhook.id,
                payload=json.dumps(payload.model_dump()),
                response=json.dumps(
                    {"order_id": str(prior.id), "status": prior.status, "idempotent": True}
                ),
                status_code=202,
            )
            db.add(log)
            await db.flush()
            return log

        order = await order_service.place_order(
            db,
            user,
            PlaceOrderRequest(
                symbol=payload.symbol,
                side=payload.action,
                quantity=payload.qty,
                price=payload.price,
                paper_mode=payload.paper_mode,
                broker="paper" if payload.paper_mode else "dhan",
                correlation_id=idempotency_key,
            ),
            request=request,
            source="webhook",
            webhook_id=webhook.id,
        )
        log = WebhookLog(
            webhook_id=webhook.id,
            payload=json.dumps(payload.model_dump()),
            response=json.dumps({"order_id": str(order.id), "status": order.status}),
            status_code=202,
        )
        db.add(log)
        await db.flush()
        return log

    async def _recent_order(self, db: AsyncSession, webhook_id, idempotency_key: str) -> Order | None:
        result = await db.execute(
            select(Order)
            .where(Order.webhook_id == webhook_id, Order.correlation_id == idempotency_key)
            .order_by(Order.created_at.desc())
            .limit(8)
        )
        cutoff = datetime.now(timezone.utc) - WEBHOOK_RETRY_WINDOW
        for order in result.scalars():
            created = _aware(order.created_at)
            if created is not None and created >= cutoff:
                return order
        return None


webhook_service = WebhookService()
