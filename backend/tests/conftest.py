import os
import asyncio
import tempfile
from pathlib import Path

os.environ["RATE_LIMIT_ENABLED"] = "false"
os.environ["APP_ENV"] = "test"
os.environ["SMTP_HOST"] = ""
os.environ["SMTP_FROM"] = ""
os.environ["EMAIL_VERIFICATION_REQUIRED"] = "false"
test_db = Path(tempfile.gettempdir()) / "gnkalgo-pytest.db"
test_db.unlink(missing_ok=True)
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{test_db.as_posix()}"

from app.database import Base, engine
from app.models import billing, instrument, trading, user  # noqa: E402,F401


def pytest_sessionstart(session):
    async def create_schema():
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    asyncio.run(create_schema())


def pytest_sessionfinish(session, exitstatus):
    asyncio.run(engine.dispose())
    try:
        test_db.unlink(missing_ok=True)
    except PermissionError:
        # Windows can retain the aiosqlite worker handle briefly at teardown.
        # Do not turn an otherwise successful test run into a failure.
        pass
