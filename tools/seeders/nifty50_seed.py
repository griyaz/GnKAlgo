"""Simple seeder for NIFTY50 constituents.

This script expects a CSV file at data/nifty50.csv with columns:
symbol,trading_symbol,display_name

It uses backend.app.api.deps.get_db to obtain a DB session and inserts instruments.
"""
import csv
import os
from backend.app.api.deps import SessionLocal
from backend.app.db.models.instrument import Instrument

THIS_DIR = os.path.dirname(__file__)
CSV_PATH = os.path.join(THIS_DIR, "../../data/nifty50.csv")


def seed():
    engine = SessionLocal().get_bind()
    # Simple manual insert using SQLAlchemy ORM session
    session = SessionLocal()
    with open(CSV_PATH, "r") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            inst = Instrument(
                exchange="NSE",
                symbol=row["symbol"].strip(),
                trading_symbol=row.get("trading_symbol") or row["symbol"].strip(),
                display_name=row.get("display_name") or row["symbol"].strip(),
                instrument_type="EQ",
                active=True,
            )
            session.add(inst)
        session.commit()
        session.close()

if __name__ == "__main__":
    seed()
