from sqlalchemy import (
    Column, Integer, String, Boolean, Numeric, DateTime, UniqueConstraint, Index
)
from sqlalchemy.sql import func
from backend.app.db.base import Base

class Instrument(Base):
    __tablename__ = "instruments"
    id = Column(Integer, primary_key=True, index=True)
    exchange = Column(String(32), nullable=False)           # e.g., NSE, BSE
    segment = Column(String(32), nullable=True)             # INDEX, EQ, F&O etc.
    symbol = Column(String(128), nullable=False)            # GnKAlgo internal symbol (canonical)
    trading_symbol = Column(String(128), nullable=True)     # human readable/trade ticker
    display_name = Column(String(256), nullable=True)
    instrument_type = Column(String(64), nullable=True)     # INDEX, EQ, FUT, OPT
    index_name = Column(String(128), nullable=True)
    isin = Column(String(32), nullable=True)
    broker = Column(String(64), nullable=True)              # which broker adapter (optional)
    broker_symbol = Column(String(128), nullable=True)      # broker's string symbol
    broker_token = Column(String(128), nullable=True, index=True)  # numeric/opaque token
    tick_size = Column(Numeric(18, 8), nullable=True)
    lot_size = Column(Integer, nullable=True)
    active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("exchange", "symbol", name="uq_instruments_exchange_symbol"),
        Index("ix_instruments_broker_token", "broker_token"),
    )
