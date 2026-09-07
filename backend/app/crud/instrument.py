from sqlalchemy.orm import Session
from typing import List, Optional
from backend.app.db.models.instrument import Instrument
from backend.app.schemas.instrument import InstrumentCreate, InstrumentUpdate


def get_instrument(db: Session, instrument_id: int) -> Optional[Instrument]:
    return db.query(Instrument).filter(Instrument.id == instrument_id).first()


def get_instrument_by_exchange_symbol(db: Session, exchange: str, symbol: str) -> Optional[Instrument]:
    return db.query(Instrument).filter(Instrument.exchange == exchange, Instrument.symbol == symbol).first()


def list_instruments(db: Session, skip: int = 0, limit: int = 100) -> List[Instrument]:
    return db.query(Instrument).offset(skip).limit(limit).all()


def create_instrument(db: Session, payload: InstrumentCreate) -> Instrument:
    obj = Instrument(**payload.dict())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


def update_instrument(db: Session, db_obj: Instrument, payload: InstrumentUpdate) -> Instrument:
    data = payload.dict(exclude_unset=True)
    for k, v in data.items():
        setattr(db_obj, k, v)
    db.add(db_obj)
    db.commit()
    db.refresh(db_obj)
    return db_obj


def deactivate_instrument(db: Session, db_obj: Instrument) -> Instrument:
    db_obj.active = False
    db.add(db_obj)
    db.commit()
    db.refresh(db_obj)
    return db_obj
