import asyncio
import logging

from app.config import settings
from app.database import AsyncSessionLocal
from app.services.alert_service import alert_service

logger = logging.getLogger(__name__)


async def alert_scheduler_loop() -> None:
    while True:
        try:
            async with AsyncSessionLocal() as session:
                count = await alert_service.evaluate_active(session)
                await session.commit()
                if count:
                    logger.info("Triggered %d alert(s)", count)
        except Exception:
            logger.exception("Alert scheduler tick failed")
        await asyncio.sleep(max(5, settings.market_data_stale_seconds))


def start_alert_scheduler() -> asyncio.Task:
    return asyncio.create_task(alert_scheduler_loop())
