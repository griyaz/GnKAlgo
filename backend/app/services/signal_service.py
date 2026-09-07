import json

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import Signal, User


class SignalService:
    async def fetch_and_store(self, db: AsyncSession, user: User, symbols: str = "RELIANCE,TCS,INFY,HDFCBANK") -> list[Signal]:
        async with httpx.AsyncClient(timeout=20.0) as client:
            try:
                headers = {}
                if settings.ml_service_token:
                    headers["X-ML-Service-Token"] = settings.ml_service_token
                response = await client.get(
                    f"{settings.ml_service_url}/ml/v1/signals/batch",
                    params={"symbols": symbols},
                    headers=headers,
                )
                response.raise_for_status()
                payload = response.json()
            except Exception:
                payload = {
                    "signals": [
                        {"symbol": "RELIANCE", "action": "HOLD", "confidence": 0.0, "price": 0, "features": {}},
                    ]
                }

        stored: list[Signal] = []
        for item in payload.get("signals", []):
            signal = Signal(
                user_id=user.id,
                symbol=item.get("symbol", ""),
                exchange=item.get("exchange", "NSE"),
                action=item.get("action", "HOLD"),
                confidence=float(item.get("confidence") or 0),
                price=item.get("price"),
                entry_min=item.get("entry_min", item.get("entry")),
                entry_max=item.get("entry_max", item.get("entry")),
                stop_loss=item.get("stop_loss"),
                target_1=item.get("target_1", item.get("target")),
                target_2=item.get("target_2"),
                timeframe=item.get("timeframe", "15m"),
                status=item.get("status", "ACTIVE"),
                explanation=item.get("explanation") or item.get("reason"),
                strategy_source=item.get("strategy_source") or item.get("strategy"),
                model_source=item.get("model_source") or "ml-service",
                execution_mode="PAPER",
                model_version=item.get("model_version", "rf-v1"),
                features_json=json.dumps(item.get("features") or {}),
            )
            db.add(signal)
            stored.append(signal)
        await db.flush()
        return stored


signal_service = SignalService()
