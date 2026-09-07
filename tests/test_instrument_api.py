from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.db.base import Base
from backend.app.db.models.instrument import Instrument
from backend.app.api.deps import get_db
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import pytest

# Setup in-memory SQLite for tests
SQLALCHEMY_TEST_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(SQLALCHEMY_TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(autouse=True)
def create_test_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)

# Override the get_db dependency
def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)

def test_create_instrument_api():
    payload = {
        "exchange": "NSE",
        "symbol": "TESTSYM",
        "trading_symbol": "TESTSYM",
        "display_name": "Test Symbol",
        "instrument_type": "EQ",
        "tick_size": 0.05,
        "lot_size": 1
    }
    resp = client.post("/api/v1/instruments/", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["symbol"] == "TESTSYM"

def test_duplicate_instrument_returns_409():
    payload = {"exchange": "NSE", "symbol": "DUPSYM"}
    r1 = client.post("/api/v1/instruments/", json=payload)
    assert r1.status_code == 201
    r2 = client.post("/api/v1/instruments/", json=payload)
    assert r2.status_code == 409

def test_get_and_update_instrument():
    payload = {"exchange": "NSE", "symbol": "UPDSYM", "display_name": "Before"}
    r = client.post("/api/v1/instruments/", json=payload)
    assert r.status_code == 201
    inst = r.json()
    inst_id = inst["id"]

    # Get by id
    rget = client.get(f"/api/v1/instruments/{inst_id}")
    assert rget.status_code == 200
    assert rget.json()["symbol"] == "UPDSYM"

    # Update
    rput = client.put(f"/api/v1/instruments/{inst_id}", json={"display_name": "After"})
    assert rput.status_code == 200
    assert rput.json()["display_name"] == "After"
