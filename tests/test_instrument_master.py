import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.app.db.base import Base
from backend.app.db.models.instrument import Instrument
from backend.app.crud.instrument import create_instrument, get_instrument_by_exchange_symbol

DATABASE_URL = "sqlite:///:memory:"

@pytest.fixture(scope="function")
def db_session():
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


def test_create_and_get_instrument(db_session):
    payload = {
        "exchange": "NSE",
        "symbol": "RELIANCE",
        "trading_symbol": "RELIANCE",
        "display_name": "Reliance Industries",
        "instrument_type": "EQ",
        "tick_size": 0.05,
        "lot_size": 1,
        "broker": None,
        "broker_token": None,
    }
    # We adapt the create_instrument helper to accept a simple object with .dict()
    class P:
        def __init__(self, d):
            self._d = d
        def dict(self):
            return self._d

    inst = create_instrument(db_session, P(payload))
    assert inst.id is not None
    fetched = get_instrument_by_exchange_symbol(db_session, "NSE", "RELIANCE")
    assert fetched is not None
    assert fetched.symbol == "RELIANCE"
