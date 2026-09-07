from datetime import datetime
from pydantic import BaseModel, Field
from typing import Optional

class InstrumentBase(BaseModel):
    exchange: str = Field(..., example="NSE")
    symbol: str = Field(..., example="RELIANCE")
    segment: Optional[str] = None
    trading_symbol: Optional[str] = None
    display_name: Optional[str] = None
    instrument_type: Optional[str] = None
    index_name: Optional[str] = None
    isin: Optional[str] = None
    broker: Optional[str] = None
    broker_symbol: Optional[str] = None
    broker_token: Optional[str] = None
    tick_size: Optional[float] = None
    lot_size: Optional[int] = None
    active: Optional[bool] = True

class InstrumentCreate(InstrumentBase):
    pass

class InstrumentUpdate(InstrumentBase):
    pass

class InstrumentOut(InstrumentBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True
