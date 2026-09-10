import os
import uuid

os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test_gnkalgo_strategies.db"
os.environ["STRATEGY_SCHEDULER_TICK_SECONDS"] = "1"

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.main import app


def _register_login(client: TestClient, email: str) -> str:
    password = "SecurePass1!"
    res = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": password,
            "full_name": "Trader",
            "phone": f"98{uuid.uuid4().int % 10**8:08d}",
        },
    )
    token = res.json()["message"].split("token=")[-1]
    client.post("/api/v1/auth/verify-email", json={"token": token})
    login = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    return login.json()["access_token"]


def test_strategy_builder_and_update():
    with TestClient(app) as client:
        access = _register_login(client, f"strat-{uuid.uuid4().hex[:8]}@gnkalgo.com")
        auth = {"Authorization": f"Bearer {access}"}
        created = client.post(
            "/api/v1/strategies/",
            headers=auth,
            json={
                "name": "Sell test",
                "symbol": "TCS",
                "action": "SELL",
                "qty": 3,
                "paper_mode": True,
                "schedule_enabled": True,
                "interval_minutes": 5,
            },
        )
        assert created.status_code == 200
        body = created.json()
        assert body["symbol"] == "TCS"
        assert body["schedule_enabled"] is True
        assert body["interval_minutes"] == 5
        assert '"action":"SELL"' in body["rules_json"].replace(" ", "")

        sid = body["id"]
        updated = client.put(
            f"/api/v1/strategies/{sid}",
            headers=auth,
            json={"action": "BUY", "qty": 2, "interval_minutes": 10},
        )
        assert updated.status_code == 200
        assert '"action":"BUY"' in updated.json()["rules_json"].replace(" ", "")
        assert updated.json()["interval_minutes"] == 10

        run = client.post(f"/api/v1/strategies/{sid}/run", headers=auth)
        assert run.status_code == 200
        assert "Order" in run.json()["notes"]


def test_scheduled_runner_executes():
    from sqlalchemy import select

    from app.database import AsyncSessionLocal
    from app.models import Strategy
    from app.services.strategy_service import strategy_service

    with TestClient(app) as client:
        access = _register_login(client, f"sched-{uuid.uuid4().hex[:8]}@gnkalgo.com")
        auth = {"Authorization": f"Bearer {access}"}
        created = client.post(
            "/api/v1/strategies/",
            headers=auth,
            json={
                "name": "Auto",
                "symbol": "INFY",
                "action": "BUY",
                "qty": 1,
                "paper_mode": True,
                "schedule_enabled": True,
                "interval_minutes": 1,
            },
        )
        sid = created.json()["id"]
        strategy_uuid = uuid.UUID(sid)

        async def force_due():
            async with AsyncSessionLocal() as session:
                result = await session.execute(select(Strategy).where(Strategy.id == strategy_uuid))
                strategy = result.scalar_one()
                strategy.last_scheduled_run_at = datetime(2020, 1, 1, tzinfo=timezone.utc)
                await session.commit()

        import asyncio

        asyncio.run(force_due())

        async def run_scheduler():
            async with AsyncSessionLocal() as session:
                ran = await strategy_service.run_due_scheduled(session)
                await session.commit()
                return ran

        ran = asyncio.run(run_scheduler())
        assert ran == 1

        async def check_last_run():
            async with AsyncSessionLocal() as session:
                result = await session.execute(select(Strategy).where(Strategy.id == strategy_uuid))
                return result.scalar_one().last_scheduled_run_at

        last = asyncio.run(check_last_run())
        assert last is not None


def test_create_rejects_invalid_rules_json():
    with TestClient(app) as client:
        access = _register_login(client, f"badrules-{uuid.uuid4().hex[:8]}@gnkalgo.com")
        created = client.post(
            "/api/v1/strategies/",
            headers={"Authorization": f"Bearer {access}"},
            json={"name": "Corrupt", "rules_json": "not-json", "paper_mode": True},
        )
        assert created.status_code == 400
        assert "rules_json" in created.json()["detail"]


def test_scheduled_runner_isolates_crash_from_sibling_strategy():
    """A crash in strategy B must not roll back A after A already placed an order."""
    from datetime import datetime, timezone

    from sqlalchemy import select

    from app.database import AsyncSessionLocal
    from app.models import Strategy, StrategyRun
    from app.services.strategy_service import StrategyService, strategy_service

    with TestClient(app) as client:
        access = _register_login(client, f"iso-{uuid.uuid4().hex[:8]}@gnkalgo.com")
        auth = {"Authorization": f"Bearer {access}"}
        good = client.post(
            "/api/v1/strategies/",
            headers=auth,
            json={
                "name": "Good",
                "symbol": "TCS",
                "action": "BUY",
                "qty": 1,
                "paper_mode": True,
                "schedule_enabled": True,
                "interval_minutes": 1,
            },
        )
        bad = client.post(
            "/api/v1/strategies/",
            headers=auth,
            json={
                "name": "Bad",
                "symbol": "INFY",
                "action": "BUY",
                "qty": 1,
                "paper_mode": True,
                "schedule_enabled": True,
                "interval_minutes": 1,
            },
        )
        good_id = uuid.UUID(good.json()["id"])
        bad_id = uuid.UUID(bad.json()["id"])
        stale = datetime(2020, 1, 1, tzinfo=timezone.utc)

        async def force_due():
            async with AsyncSessionLocal() as session:
                for sid in (good_id, bad_id):
                    result = await session.execute(select(Strategy).where(Strategy.id == sid))
                    result.scalar_one().last_scheduled_run_at = stale
                await session.commit()

        import asyncio

        asyncio.run(force_due())

        original = StrategyService.run_once

        async def flaky(self, db, user, strategy_id, scheduled=False):
            if strategy_id == bad_id:
                raise RuntimeError("simulated scheduled-run crash")
            return await original(self, db, user, strategy_id, scheduled)

        StrategyService.run_once = flaky
        try:
            async def run_scheduler():
                async with AsyncSessionLocal() as session:
                    return await strategy_service.run_due_scheduled(session)

            ran = asyncio.run(run_scheduler())
        finally:
            StrategyService.run_once = original

        assert ran == 2

        async def load_state():
            async with AsyncSessionLocal() as session:
                good_row = (await session.execute(select(Strategy).where(Strategy.id == good_id))).scalar_one()
                bad_row = (await session.execute(select(Strategy).where(Strategy.id == bad_id))).scalar_one()
                runs = list(
                    (
                        await session.execute(
                            select(StrategyRun).where(StrategyRun.strategy_id.in_((good_id, bad_id)))
                        )
                    ).scalars()
                )
                return good_row.last_scheduled_run_at, bad_row.last_scheduled_run_at, runs

        good_last, bad_last, runs = asyncio.run(load_state())
        assert good_last is not None and good_last.year != 2020
        assert bad_last is not None and bad_last.year != 2020
        assert any(run.strategy_id == good_id for run in runs)
        assert any(run.strategy_id == bad_id and run.status == "FAILED" for run in runs)


def test_scheduled_runner_continues_after_corrupt_rules():
    from datetime import datetime, timezone

    from sqlalchemy import select

    from app.database import AsyncSessionLocal
    from app.models import Strategy, StrategyRun
    from app.services.strategy_service import strategy_service

    with TestClient(app) as client:
        access = _register_login(client, f"corrupt-{uuid.uuid4().hex[:8]}@gnkalgo.com")
        auth = {"Authorization": f"Bearer {access}"}
        good = client.post(
            "/api/v1/strategies/",
            headers=auth,
            json={
                "name": "Healthy",
                "symbol": "TCS",
                "action": "BUY",
                "qty": 1,
                "paper_mode": True,
                "schedule_enabled": True,
                "interval_minutes": 1,
            },
        )
        bad = client.post(
            "/api/v1/strategies/",
            headers=auth,
            json={
                "name": "Poison",
                "symbol": "INFY",
                "action": "BUY",
                "qty": 1,
                "paper_mode": True,
                "schedule_enabled": True,
                "interval_minutes": 1,
            },
        )
        good_id = uuid.UUID(good.json()["id"])
        bad_id = uuid.UUID(bad.json()["id"])
        stale = datetime(2020, 1, 1, tzinfo=timezone.utc)

        async def poison_and_force_due():
            async with AsyncSessionLocal() as session:
                bad_row = (await session.execute(select(Strategy).where(Strategy.id == bad_id))).scalar_one()
                bad_row.rules_json = "not-json"
                for sid in (good_id, bad_id):
                    row = (await session.execute(select(Strategy).where(Strategy.id == sid))).scalar_one()
                    row.last_scheduled_run_at = stale
                await session.commit()

        import asyncio

        asyncio.run(poison_and_force_due())

        async def run_scheduler():
            async with AsyncSessionLocal() as session:
                return await strategy_service.run_due_scheduled(session)

        ran = asyncio.run(run_scheduler())
        assert ran == 2

        async def load_state():
            async with AsyncSessionLocal() as session:
                good_row = (await session.execute(select(Strategy).where(Strategy.id == good_id))).scalar_one()
                bad_row = (await session.execute(select(Strategy).where(Strategy.id == bad_id))).scalar_one()
                bad_runs = list(
                    (
                        await session.execute(select(StrategyRun).where(StrategyRun.strategy_id == bad_id))
                    ).scalars()
                )
                return good_row.last_scheduled_run_at, bad_row.last_scheduled_run_at, bad_runs

        good_last, bad_last, bad_runs = asyncio.run(load_state())
        assert good_last is not None and good_last.year != 2020
        assert bad_last is not None and bad_last.year != 2020
        assert any("Invalid strategy rules" in (run.notes or "") for run in bad_runs)


def _insert_strategy_order(strategy_id, user_id, status: str, price: float = 2500.0):
    from app.database import AsyncSessionLocal
    from app.models import Order

    async def _write():
        async with AsyncSessionLocal() as session:
            session.add(
                Order(
                    user_id=user_id,
                    broker="dhan",
                    symbol="RELIANCE",
                    exchange="NSE",
                    side="BUY",
                    quantity=1,
                    order_type="MARKET",
                    price=price,
                    product_type="INTRADAY",
                    status=status,
                    source="strategy",
                    strategy_id=strategy_id,
                )
            )
            await session.commit()

    import asyncio

    asyncio.run(_write())


def test_daily_loss_blocks_after_live_traded_or_pending_order():
    """Dhan stores TRADED/PENDING, not FILLED. Those fills must still trip max_daily_loss."""
    from sqlalchemy import select

    from app.database import AsyncSessionLocal
    from app.models import User

    with TestClient(app) as client:
        email = f"loss-{uuid.uuid4().hex[:8]}@gnkalgo.com"
        access = _register_login(client, email)
        auth = {"Authorization": f"Bearer {access}"}
        created = client.post(
            "/api/v1/strategies/",
            headers=auth,
            json={
                "name": "Loss cap",
                "symbol": "RELIANCE",
                "action": "BUY",
                "qty": 1,
                "paper_mode": True,
                "max_daily_loss": 1000,
            },
        )
        assert created.status_code == 200
        strategy_id = uuid.UUID(created.json()["id"])

        async def user_id():
            async with AsyncSessionLocal() as session:
                user = (await session.execute(select(User).where(User.email == email))).scalar_one()
                return user.id

        import asyncio

        _insert_strategy_order(strategy_id, asyncio.run(user_id()), "TRADED", price=2500)

        blocked = client.post(f"/api/v1/strategies/{strategy_id}/run", headers=auth)
        assert blocked.status_code == 200
        assert blocked.json()["status"] == "FAILED"
        assert "Max daily loss" in blocked.json()["notes"]


def test_daily_loss_ignores_rejected_orders():
    from sqlalchemy import select

    from app.database import AsyncSessionLocal
    from app.models import User

    with TestClient(app) as client:
        email = f"rejloss-{uuid.uuid4().hex[:8]}@gnkalgo.com"
        access = _register_login(client, email)
        auth = {"Authorization": f"Bearer {access}"}
        created = client.post(
            "/api/v1/strategies/",
            headers=auth,
            json={
                "name": "Reject skip",
                "symbol": "RELIANCE",
                "action": "BUY",
                "qty": 1,
                "paper_mode": True,
                "max_daily_loss": 1000,
            },
        )
        strategy_id = uuid.UUID(created.json()["id"])

        async def user_id():
            async with AsyncSessionLocal() as session:
                user = (await session.execute(select(User).where(User.email == email))).scalar_one()
                return user.id

        import asyncio

        _insert_strategy_order(strategy_id, asyncio.run(user_id()), "REJECTED", price=2500)

        ran = client.post(f"/api/v1/strategies/{strategy_id}/run", headers=auth)
        assert ran.status_code == 200
        assert "Order" in ran.json()["notes"]
        assert ran.json()["status"] == "COMPLETED"


def test_scheduler_skips_draft_live_strategy_and_places_no_order():
    """Scheduled SMC/live create lands in DRAFT; that must not call the broker."""
    from datetime import datetime, timezone

    from sqlalchemy import select

    from app.database import AsyncSessionLocal
    from app.models import Order, Strategy
    from app.services.strategy_service import strategy_service

    with TestClient(app) as client:
        access = _register_login(client, f"draftlive-{uuid.uuid4().hex[:8]}@gnkalgo.com")
        auth = {"Authorization": f"Bearer {access}"}
        created = client.post(
            "/api/v1/strategies/",
            headers=auth,
            json={
                "name": "Draft live SMC",
                "symbol": "RELIANCE",
                "strategy_type": "smc_intraday",
                "action": "AUTO",
                "qty": 1,
                "paper_mode": True,
                "schedule_enabled": True,
                "interval_minutes": 1,
            },
        )
        assert created.status_code == 200
        strategy_id = uuid.UUID(created.json()["id"])
        stale = datetime(2020, 1, 1, tzinfo=timezone.utc)

        async def make_draft_live():
            async with AsyncSessionLocal() as session:
                row = (await session.execute(select(Strategy).where(Strategy.id == strategy_id))).scalar_one()
                row.paper_mode = False
                row.status = "DRAFT"
                row.last_scheduled_run_at = stale
                await session.commit()

        import asyncio

        asyncio.run(make_draft_live())

        async def run_scheduler():
            async with AsyncSessionLocal() as session:
                return await strategy_service.run_due_scheduled(session)

        asyncio.run(run_scheduler())

        async def load_state():
            async with AsyncSessionLocal() as session:
                row = (await session.execute(select(Strategy).where(Strategy.id == strategy_id))).scalar_one()
                orders = list(
                    (await session.execute(select(Order).where(Order.strategy_id == strategy_id))).scalars()
                )
                return row.last_scheduled_run_at, orders

        last, orders = asyncio.run(load_state())
        assert last is not None and last.year == 2020
        assert orders == []


def test_run_once_rejects_live_orders_until_strategy_is_live():
    with TestClient(app) as client:
        access = _register_login(client, f"runlive-{uuid.uuid4().hex[:8]}@gnkalgo.com")
        auth = {"Authorization": f"Bearer {access}"}
        created = client.post(
            "/api/v1/strategies/",
            headers=auth,
            json={
                "name": "Draft live simple",
                "symbol": "TCS",
                "action": "BUY",
                "qty": 1,
                "paper_mode": True,
            },
        )
        assert created.status_code == 200
        strategy_id = uuid.UUID(created.json()["id"])

        from sqlalchemy import select

        from app.database import AsyncSessionLocal
        from app.models import Order, Strategy

        async def make_draft_live():
            async with AsyncSessionLocal() as session:
                row = (await session.execute(select(Strategy).where(Strategy.id == strategy_id))).scalar_one()
                row.paper_mode = False
                row.status = "DRAFT"
                await session.commit()

        import asyncio

        asyncio.run(make_draft_live())
        ran = client.post(f"/api/v1/strategies/{strategy_id}/run", headers=auth)
        assert ran.status_code == 200
        assert ran.json()["status"] == "FAILED"
        assert "LIVE" in ran.json()["notes"]

        async def load_orders():
            async with AsyncSessionLocal() as session:
                return list(
                    (await session.execute(select(Order).where(Order.strategy_id == strategy_id))).scalars()
                )

        assert asyncio.run(load_orders()) == []


def test_daily_loss_counts_pending_live_orders():
    from sqlalchemy import select

    from app.database import AsyncSessionLocal
    from app.models import User

    with TestClient(app) as client:
        email = f"pendloss-{uuid.uuid4().hex[:8]}@gnkalgo.com"
        access = _register_login(client, email)
        auth = {"Authorization": f"Bearer {access}"}
        created = client.post(
            "/api/v1/strategies/",
            headers=auth,
            json={
                "name": "Pending cap",
                "symbol": "RELIANCE",
                "action": "BUY",
                "qty": 1,
                "paper_mode": True,
                "max_daily_loss": 1000,
            },
        )
        strategy_id = uuid.UUID(created.json()["id"])

        async def user_id():
            async with AsyncSessionLocal() as session:
                user = (await session.execute(select(User).where(User.email == email))).scalar_one()
                return user.id

        import asyncio

        _insert_strategy_order(strategy_id, asyncio.run(user_id()), "PENDING", price=2500)

        blocked = client.post(f"/api/v1/strategies/{strategy_id}/run", headers=auth)
        assert blocked.status_code == 200
        assert blocked.json()["status"] == "FAILED"
        assert "Max daily loss" in blocked.json()["notes"]


def test_smc_run_fetches_candles_through_dhan_adapter():
    """Production SMC used to call get_candles() with no adapter, so it always
    skipped with insufficient_candles once mock data was disabled."""
    import json as json_lib

    from sqlalchemy import select

    from app.core.security import encrypt_data
    from app.database import AsyncSessionLocal
    from app.models import BrokerConnection, BrokerType, User
    from app.services.candle_service import candle_service

    captured = {}

    async def fake_get_candles(db, symbol, exchange, interval, adapter=None, count=500):
        captured["adapter"] = adapter
        captured["interval"] = interval
        captured["count"] = count
        return {"candles": [], "source": "empty"}

    original = candle_service.get_candles
    candle_service.get_candles = fake_get_candles  # type: ignore[method-assign]
    try:
        with TestClient(app) as client:
            email = f"smccandle-{uuid.uuid4().hex[:8]}@gnkalgo.com"
            access = _register_login(client, email)
            auth = {"Authorization": f"Bearer {access}"}
            created = client.post(
                "/api/v1/strategies/",
                headers=auth,
                json={
                    "name": "SMC candles",
                    "symbol": "RELIANCE",
                    "strategy_type": "smc_intraday",
                    "timeframe": "5m",
                    "action": "AUTO",
                    "qty": 1,
                    "paper_mode": True,
                },
            )
            assert created.status_code == 200
            strategy_id = created.json()["id"]

            async def attach_dhan():
                async with AsyncSessionLocal() as session:
                    user = (await session.execute(select(User).where(User.email == email))).scalar_one()
                    session.add(
                        BrokerConnection(
                            user_id=user.id,
                            broker=BrokerType.DHAN,
                            encrypted_credentials=encrypt_data(
                                json_lib.dumps({"access_token": "tok", "client_id": "cid"})
                            ),
                            client_id="cid",
                            is_active=True,
                            health_status="connected",
                        )
                    )
                    await session.commit()

            import asyncio

            asyncio.run(attach_dhan())
            run = client.post(f"/api/v1/strategies/{strategy_id}/run", headers=auth)
            assert run.status_code == 200
            assert captured.get("adapter") is not None
            assert captured["adapter"].__class__.__name__ == "DhanAdapter"
            assert captured["interval"] == "5m"
            assert captured["count"] == 120
            assert run.json()["status"] == "SKIPPED"
    finally:
        candle_service.get_candles = original  # type: ignore[method-assign]
