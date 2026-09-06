import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Literal

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Order, Strategy, StrategyRun, User

logger = logging.getLogger(__name__)
from app.schemas.trading import (
    PlaceOrderRequest,
    SmcIntradayRules,
    StrategyCreateRequest,
    StrategyRules,
    StrategyUpdateRequest,
)
from app.services import billing_service
from app.services.candle_service import BASE_PRICES, candle_service
from app.services.order_service import order_service
from app.services.strategy_evaluators.smc_intraday import evaluate_smc_intraday

ParsedRules = StrategyRules | SmcIntradayRules


def _rules_from_create(data: StrategyCreateRequest) -> dict:
    if data.strategy_type == "smc_intraday":
        return SmcIntradayRules(
            timeframe=data.timeframe or "15m",
            entry=data.entry_mode or "fvg",
            action=data.action or "AUTO",
            qty=data.qty or 1,
            stop_loss_buffer_pct=data.stop_loss_buffer_pct or 0.1,
            target_rr=data.target_rr or 2.0,
        ).model_dump()
    action = data.action if data.action in ("BUY", "SELL") else "BUY"
    return StrategyRules(action=action, qty=data.qty or 1).model_dump()


def _merge_update_rules(data: StrategyUpdateRequest, existing: str) -> dict:
    base = json.loads(existing or "{}")
    strategy_type = data.strategy_type or base.get("type", "simple")

    if strategy_type == "smc_intraday":
        merged = {
            "type": "smc_intraday",
            "timeframe": data.timeframe or base.get("timeframe", "15m"),
            "entry": data.entry_mode or base.get("entry", "fvg"),
            "action": data.action or base.get("action", "AUTO"),
            "qty": data.qty if data.qty is not None else base.get("qty", 1),
            "stop_loss_buffer_pct": (
                data.stop_loss_buffer_pct
                if data.stop_loss_buffer_pct is not None
                else base.get("stop_loss_buffer_pct", 0.1)
            ),
            "target_rr": data.target_rr if data.target_rr is not None else base.get("target_rr", 2.0),
            "swing_lookback": base.get("swing_lookback", 5),
        }
        return SmcIntradayRules(**merged).model_dump()

    merged = {
        "type": "simple",
        "action": data.action or base.get("action", "BUY"),
        "qty": data.qty if data.qty is not None else base.get("qty", 1),
    }
    if merged["action"] not in ("BUY", "SELL"):
        merged["action"] = "BUY"
    return StrategyRules(**merged).model_dump()


def build_rules_json(data: StrategyCreateRequest | StrategyUpdateRequest, existing: str | None = None) -> str:
    if data.rules_json:
        try:
            parse_rules(data.rules_json)
        except (ValueError, TypeError, json.JSONDecodeError, ValidationError, KeyError) as exc:
            raise ValueError(f"Invalid rules_json: {exc}") from exc
        return data.rules_json
    if isinstance(data, StrategyCreateRequest):
        return json.dumps(_rules_from_create(data))
    if any(
        v is not None
        for v in (
            data.action,
            data.qty,
            data.strategy_type,
            data.timeframe,
            data.entry_mode,
            data.stop_loss_buffer_pct,
            data.target_rr,
        )
    ):
        return json.dumps(_merge_update_rules(data, existing or "{}"))
    return existing or json.dumps({"type": "simple", "action": "BUY", "qty": 1})


def parse_rules(rules_json: str) -> ParsedRules:
    raw = json.loads(rules_json or "{}")
    if not isinstance(raw, dict):
        raise ValueError("rules_json must be a JSON object")
    if raw.get("type") == "smc_intraday":
        return SmcIntradayRules(**raw)
    action = raw.get("action", "BUY")
    if action not in ("BUY", "SELL"):
        action = "BUY"
    try:
        qty = int(raw.get("qty") or 1)
    except (TypeError, ValueError) as exc:
        raise ValueError("qty must be an integer") from exc
    if qty < 1:
        raise ValueError("qty must be greater than zero")
    return StrategyRules(action=action, qty=qty)


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


class StrategyService:
    async def list_strategies(self, db: AsyncSession, user: User) -> list[Strategy]:
        result = await db.execute(select(Strategy).where(Strategy.user_id == user.id))
        return list(result.scalars().all())

    def _status_for_mode(self, paper_mode: bool, schedule_enabled: bool) -> str:
        if not schedule_enabled:
            return "DRAFT"
        return "PAPER" if paper_mode else "LIVE"

    async def create(self, db: AsyncSession, user: User, data: StrategyCreateRequest) -> Strategy:
        if not data.paper_mode:
            sub = await billing_service.active_subscription(db, user)
            if not sub:
                raise ValueError("Active subscription required for live strategies")
        rules_json = build_rules_json(data)
        status = self._status_for_mode(data.paper_mode, data.schedule_enabled)
        strategy = Strategy(
            user_id=user.id,
            name=data.name,
            description=data.description,
            symbol=data.symbol.upper(),
            rules_json=rules_json,
            paper_mode=data.paper_mode,
            max_quantity=data.max_quantity,
            max_daily_loss=data.max_daily_loss,
            schedule_enabled=data.schedule_enabled,
            interval_minutes=data.interval_minutes if data.schedule_enabled else 0,
            status=status,
            last_scheduled_run_at=datetime.now(timezone.utc) if data.schedule_enabled else None,
        )
        db.add(strategy)
        await db.flush()
        return strategy

    async def update(
        self, db: AsyncSession, user: User, strategy_id: uuid.UUID, data: StrategyUpdateRequest
    ) -> Strategy:
        result = await db.execute(
            select(Strategy).where(Strategy.id == strategy_id, Strategy.user_id == user.id)
        )
        strategy = result.scalar_one_or_none()
        if not strategy:
            raise ValueError("Strategy not found")

        if data.name is not None:
            strategy.name = data.name
        if data.description is not None:
            strategy.description = data.description
        if data.symbol is not None:
            strategy.symbol = data.symbol.upper()
        if data.paper_mode is not None:
            strategy.paper_mode = data.paper_mode
            if not strategy.paper_mode:
                sub = await billing_service.active_subscription(db, user)
                if not sub:
                    raise ValueError("Active subscription required for live strategies")
        if data.max_quantity is not None:
            strategy.max_quantity = data.max_quantity
        if data.max_daily_loss is not None:
            strategy.max_daily_loss = data.max_daily_loss

        if any(
            v is not None
            for v in (
                data.rules_json,
                data.action,
                data.qty,
                data.strategy_type,
                data.timeframe,
                data.entry_mode,
                data.stop_loss_buffer_pct,
                data.target_rr,
            )
        ):
            strategy.rules_json = build_rules_json(data, strategy.rules_json)

        schedule_was_off = not strategy.schedule_enabled
        if data.schedule_enabled is not None:
            strategy.schedule_enabled = data.schedule_enabled
        if data.interval_minutes is not None:
            strategy.interval_minutes = data.interval_minutes
        if data.schedule_enabled and strategy.interval_minutes < 1:
            raise ValueError("interval_minutes must be at least 1 when schedule is enabled")
        if not strategy.schedule_enabled:
            strategy.interval_minutes = 0

        if data.status is not None:
            strategy.status = data.status
        elif data.schedule_enabled is not None or data.paper_mode is not None:
            if strategy.status != "PAUSED":
                strategy.status = self._status_for_mode(strategy.paper_mode, strategy.schedule_enabled)

        if data.schedule_enabled and schedule_was_off:
            strategy.last_scheduled_run_at = datetime.now(timezone.utc)

        return strategy

    async def set_status(self, db: AsyncSession, user: User, strategy_id: uuid.UUID, status: str) -> Strategy:
        result = await db.execute(
            select(Strategy).where(Strategy.id == strategy_id, Strategy.user_id == user.id)
        )
        strategy = result.scalar_one_or_none()
        if not strategy:
            raise ValueError("Strategy not found")
        strategy.status = status
        return strategy

    def is_due(self, strategy: Strategy, now: datetime) -> bool:
        if not strategy.schedule_enabled or strategy.interval_minutes < 1:
            return False
        if strategy.status == "PAUSED":
            return False
        last = _aware(strategy.last_scheduled_run_at)
        if last is None:
            return True
        return last + timedelta(minutes=strategy.interval_minutes) <= now

    async def _daily_loss(self, db: AsyncSession, strategy: Strategy) -> float:
        from zoneinfo import ZoneInfo

        ist = ZoneInfo("Asia/Kolkata")
        now = datetime.now(ist)
        start = datetime.combine(now.date(), datetime.min.time(), tzinfo=ist).astimezone(timezone.utc)
        result = await db.execute(
            select(Order).where(
                Order.strategy_id == strategy.id,
                Order.created_at >= start,
                Order.status.in_(("FILLED", "PAPER_FILLED")),
            )
        )
        cashflow = 0.0
        for order in result.scalars():
            px = float(order.price or BASE_PRICES.get(order.symbol, 0) or 0)
            notional = order.quantity * px
            cashflow += -notional if order.side == "BUY" else notional
        return -cashflow if cashflow < 0 else 0.0

    async def _live_blocked(self, db: AsyncSession, user: User, strategy: Strategy) -> str | None:
        if strategy.paper_mode:
            return None
        sub = await billing_service.active_subscription(db, user)
        if not sub:
            return "Active subscription required for live strategies"
        return None

    async def _place_strategy_order(
        self,
        db: AsyncSession,
        user: User,
        strategy: Strategy,
        side: Literal["BUY", "SELL"],
        qty: int,
        scheduled: bool,
    ):
        blocked = await self._live_blocked(db, user, strategy)
        if blocked:
            raise ValueError(blocked)
        if await self._daily_loss(db, strategy) >= strategy.max_daily_loss:
            raise ValueError(f"Max daily loss {strategy.max_daily_loss} reached")
        return await order_service.place_order(
            db,
            user,
            PlaceOrderRequest(
                symbol=strategy.symbol,
                side=side,
                quantity=qty,
                paper_mode=strategy.paper_mode,
                broker="paper" if strategy.paper_mode else "dhan",
                product_type="INTRADAY",
            ),
            source="strategy_scheduler" if scheduled else "strategy",
            strategy_id=strategy.id,
        )

    async def _run_smc_intraday(
        self,
        db: AsyncSession,
        user: User,
        strategy: Strategy,
        rules: SmcIntradayRules,
        run: StrategyRun,
        scheduled: bool,
    ) -> StrategyRun:
        try:
            candle_data = await candle_service.get_candles(
                db,
                strategy.symbol,
                "NSE",
                rules.timeframe,
                count=120,
            )
            candles = candle_data.get("candles", [])
            signal = evaluate_smc_intraday(
                candles,
                entry_mode=rules.entry,
                side_mode=rules.action,
                buffer_pct=rules.stop_loss_buffer_pct,
                target_rr=rules.target_rr,
                swing_lookback=rules.swing_lookback,
            )
        except Exception as exc:
            run.status = "FAILED"
            run.notes = f"SMC evaluation failed: {exc}"
            if scheduled:
                strategy.last_scheduled_run_at = datetime.now(timezone.utc)
            return run
        if not signal.should_trade or not signal.side:
            run.status = "SKIPPED"
            run.notes = f"SMC no trade: {signal.reason}"
            if scheduled:
                strategy.last_scheduled_run_at = datetime.now(timezone.utc)
            return run

        qty = min(rules.qty, strategy.max_quantity)
        try:
            order = await self._place_strategy_order(db, user, strategy, signal.side, qty, scheduled)
        except ValueError as exc:
            run.status = "FAILED"
            run.notes = str(exc)
            if scheduled:
                strategy.last_scheduled_run_at = datetime.now(timezone.utc)
            return run
        run.status = "COMPLETED" if order.status in ("PAPER_FILLED", "FILLED", "PENDING") else "FAILED"
        run.notes = (
            f"Order {order.id} status={order.status}; "
            f"entry={signal.entry} sl={signal.stop_loss} target={signal.target} ({signal.reason})"
        )
        if scheduled:
            strategy.last_scheduled_run_at = datetime.now(timezone.utc)
        return run

    async def run_once(
        self, db: AsyncSession, user: User, strategy_id: uuid.UUID, scheduled: bool = False
    ) -> StrategyRun:
        result = await db.execute(
            select(Strategy).where(Strategy.id == strategy_id, Strategy.user_id == user.id)
        )
        strategy = result.scalar_one_or_none()
        if not strategy:
            raise ValueError("Strategy not found")

        run = StrategyRun(strategy_id=strategy.id, status="RUNNING")
        db.add(run)
        await db.flush()

        try:
            rules = parse_rules(strategy.rules_json)
        except (ValueError, TypeError, json.JSONDecodeError, ValidationError, KeyError) as exc:
            run.status = "FAILED"
            run.notes = f"Invalid strategy rules: {exc}"
            if scheduled:
                strategy.last_scheduled_run_at = datetime.now(timezone.utc)
            return run

        if isinstance(rules, SmcIntradayRules):
            return await self._run_smc_intraday(db, user, strategy, rules, run, scheduled)

        if scheduled:
            run.status = "SKIPPED"
            run.notes = "Simple strategies do not auto-trade on a schedule. Use SMC or Run once."
            strategy.last_scheduled_run_at = datetime.now(timezone.utc)
            return run

        side: Literal["BUY", "SELL"] = rules.action
        qty = min(rules.qty, strategy.max_quantity)
        try:
            order = await self._place_strategy_order(db, user, strategy, side, qty, scheduled)
        except ValueError as exc:
            run.status = "FAILED"
            run.notes = str(exc)
            return run
        run.status = "COMPLETED" if order.status in ("PAPER_FILLED", "FILLED", "PENDING") else "FAILED"
        run.notes = f"Order {order.id} status={order.status}"
        if scheduled:
            strategy.last_scheduled_run_at = datetime.now(timezone.utc)
        return run

    async def run_due_scheduled(self, db: AsyncSession) -> int:
        now = datetime.now(timezone.utc)
        result = await db.execute(
            select(Strategy.id).where(
                Strategy.schedule_enabled.is_(True),
                Strategy.interval_minutes >= 1,
                Strategy.status != "PAUSED",
            ).order_by(Strategy.created_at, Strategy.id)
        )
        strategy_ids = list(result.scalars().all())
        ran = 0
        for strategy_id in strategy_ids:
            strategy = await db.get(Strategy, strategy_id)
            if not strategy or not self.is_due(strategy, now):
                continue
            user_result = await db.execute(select(User).where(User.id == strategy.user_id))
            user = user_result.scalar_one_or_none()
            if not user or not user.is_active:
                continue
            try:
                await self.run_once(db, user, strategy_id, scheduled=True)
                await db.commit()
                ran += 1
            except Exception:
                # A later crash must not roll back orders already sent to the broker
                # for earlier strategies in this tick.
                logger.exception(
                    "Scheduled strategy %s crashed; isolating from the rest of the tick",
                    strategy_id,
                )
                await db.rollback()
                try:
                    crashed = await db.get(Strategy, strategy_id)
                    if crashed:
                        crashed.last_scheduled_run_at = datetime.now(timezone.utc)
                        db.add(
                            StrategyRun(
                                strategy_id=strategy_id,
                                status="FAILED",
                                notes="Scheduled run crashed; isolated so other strategies keep trading",
                            )
                        )
                        await db.commit()
                    ran += 1
                except Exception:
                    logger.exception("Failed to record isolated crash for strategy %s", strategy_id)
                    await db.rollback()
        return ran


strategy_service = StrategyService()
