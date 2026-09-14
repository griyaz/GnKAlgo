import asyncio
import pathlib

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base
from app.services.instrument_csv_parser import parse_csv_row
from app.services.instrument_service import instrument_service
from app.services.instrument_sync_service import (
    deduplicate_feed_rows,
    incomplete_instrument_feed,
    instrument_sync_service,
)


def test_parse_csv_equity_row():
    row = {
        "SEM_EXM_EXCH_ID": "NSE",
        "SEM_SEGMENT": "E",
        "SEM_SMST_SECURITY_ID": "2885",
        "SEM_INSTRUMENT_NAME": "EQUITY",
        "SEM_TRADING_SYMBOL": "RELIANCE",
        "SEM_CUSTOM_SYMBOL": "Reliance Industries",
        "SEM_EXPIRY_DATE": "",
        "SEM_STRIKE_PRICE": "",
        "SEM_OPTION_TYPE": "XX",
        "SEM_LOT_UNITS": "1.0",
        "SEM_TICK_SIZE": "10.0000",
        "SEM_EXCH_INSTRUMENT_TYPE": "ES",
        "SM_SYMBOL_NAME": "RELIANCE INDUSTRIES LTD",
    }
    parsed = parse_csv_row(row)
    assert parsed is not None
    assert parsed["symbol"] == "RELIANCE"
    assert parsed["exchange_segment"] == "NSE_EQ"
    assert parsed["security_id"] == "2885"


def test_parse_csv_index_nifty_alias():
    row = {
        "SEM_EXM_EXCH_ID": "NSE",
        "SEM_SEGMENT": "I",
        "SEM_SMST_SECURITY_ID": "13",
        "SEM_INSTRUMENT_NAME": "INDEX",
        "SEM_TRADING_SYMBOL": "NIFTY",
        "SEM_CUSTOM_SYMBOL": "Nifty 50",
        "SEM_EXPIRY_DATE": "0001-01-01",
        "SEM_STRIKE_PRICE": "",
        "SEM_OPTION_TYPE": "XX",
        "SEM_LOT_UNITS": "1.0",
        "SEM_TICK_SIZE": "0.0500",
        "SEM_EXCH_INSTRUMENT_TYPE": "INDEX",
        "SM_SYMBOL_NAME": "NIFTY",
    }
    parsed = parse_csv_row(row)
    assert parsed is not None
    assert parsed["symbol"] == "NIFTY50"
    assert parsed["exchange_segment"] == "IDX_I"


def test_seed_and_search():
    async def _run():
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with factory() as session:
            await instrument_sync_service.seed_from_curated(session)
            items = await instrument_service.search(session, "RELIANCE", limit=5)
            assert any(i["symbol"] == "RELIANCE" for i in items)
        await engine.dispose()

    asyncio.run(_run())


FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "sample_instruments.csv"


def test_ingest_sample_csv():
    async def _run():
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with factory() as session:
            with open(FIXTURE, encoding="utf-8") as f:
                text = f.read()
            upserted, _ = await instrument_sync_service._ingest_csv(session, text)
            assert upserted >= 3
            inst = await instrument_service.get(session, "RELIANCE", "NSE")
            assert inst is not None
            assert inst["security_id"] == "2885"
            nifty = await instrument_service.get(session, "NIFTY50", "NSE")
            assert nifty is not None
        await engine.dispose()

    asyncio.run(_run())


def test_incomplete_instrument_feed_detects_truncated_scrip_master():
    assert incomplete_instrument_feed(
        parsed_count=200, active_count=50_000, stale_count=49_800, previous_success_count=50_000
    ) is True
    # Weekly F&O expiry can drop the file without being a truncated download.
    assert incomplete_instrument_feed(
        parsed_count=38_000, active_count=50_000, stale_count=12_000, previous_success_count=50_000
    ) is False
    assert incomplete_instrument_feed(parsed_count=4, active_count=4, stale_count=0) is False


def test_truncated_csv_does_not_deactivate_existing_instruments():
    """A short/partial Dhan CSV used to mark every unseen NSE/BSE row inactive."""
    truncated = (
        "SEM_EXM_EXCH_ID,SEM_SEGMENT,SEM_SMST_SECURITY_ID,SEM_INSTRUMENT_NAME,"
        "SEM_TRADING_SYMBOL,SEM_CUSTOM_SYMBOL,SEM_EXCH_INSTRUMENT_TYPE\n"
        "NSE,E,2885,EQUITY,RELIANCE,Reliance Industries,ES\n"
    )

    async def _run():
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with factory() as session:
            await instrument_sync_service.seed_from_curated(session)
            before = await instrument_service.get(session, "TCS", "NSE")
            assert before is not None
            try:
                await instrument_sync_service._ingest_csv(session, truncated)
            except RuntimeError as exc:
                assert "incomplete" in str(exc).lower()
            else:
                raise AssertionError("partial CSV must not mass-deactivate the instrument universe")
            after = await instrument_service.get(session, "TCS", "NSE")
            assert after is not None
            assert after["security_id"] == "11536"
        await engine.dispose()

    asyncio.run(_run())


def _equity_csv(symbols: list[tuple[str, str]]) -> str:
    header = (
        "SEM_EXM_EXCH_ID,SEM_SEGMENT,SEM_SMST_SECURITY_ID,SEM_INSTRUMENT_NAME,"
        "SEM_TRADING_SYMBOL,SEM_CUSTOM_SYMBOL,SEM_EXCH_INSTRUMENT_TYPE"
    )
    rows = [
        f"NSE,E,{sid},EQUITY,{sym},{sym},ES" for sid, sym in symbols
    ]
    return header + "\n" + "\n".join(rows) + "\n"


def test_complete_csv_still_deactivates_delisted_row():
    symbols = [(str(10_000 + i), f"SYM{i:03d}") for i in range(60)]

    async def _run():
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with factory() as session:
            upserted, deactivated = await instrument_sync_service._ingest_csv(
                session, _equity_csv(symbols)
            )
            assert upserted == 60
            assert deactivated == 0
            assert await instrument_service.get(session, "SYM059", "NSE") is not None
            upserted, deactivated = await instrument_sync_service._ingest_csv(
                session, _equity_csv(symbols[:-1])
            )
            assert upserted == 59
            assert deactivated == 1
            assert await instrument_service.get(session, "SYM059", "NSE") is None
            assert await instrument_service.get(session, "SYM000", "NSE") is not None
        await engine.dispose()

    asyncio.run(_run())


def test_curated_instrument_feed_keys_are_deduplicated_before_upsert():
    rows = [
        {"exchange": "NSE", "exchange_segment": "IDX_I", "security_id": "13", "symbol": "NIFTY50"},
        {"exchange": "NSE", "exchange_segment": "IDX_I", "security_id": "13", "symbol": "NIFTY"},
    ]
    unique = deduplicate_feed_rows(rows)
    assert [row["symbol"] for row in unique] == ["NIFTY50"]
