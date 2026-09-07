from fastapi import APIRouter, Depends, HTTPException, status
from typing import List
from sqlalchemy.orm import Session

from backend.app.schemas.instrument import InstrumentCreate, InstrumentOut, InstrumentUpdate
from backend.app.crud.instrument import (
    create_instrument, get_instrument, list_instruments, get_instrument_by_exchange_symbol, update_instrument
)
from app.database import get_db

router = APIRouter()

@router.post("/", response_model=InstrumentOut, status_code=status.HTTP_201_CREATED)
def create(payload: InstrumentCreate, db: Session = Depends(get_db)):
    existing = get_instrument_by_exchange_symbol(db, payload.exchange, payload.symbol)
    if existing:
        raise HTTPException(status_code=409, detail="Instrument with exchange+symbol already exists")
    return create_instrument(db, payload)

@router.get("/", response_model=List[InstrumentOut])
def list_all(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return list_instruments(db, skip, limit)

@router.get("/{instrument_id}", response_model=InstrumentOut)
def get_one(instrument_id: int, db: Session = Depends(get_db)):
    obj = get_instrument(db, instrument_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Instrument not found")
    return obj

@router.put("/{instrument_id}", response_model=InstrumentOut)
def update(instrument_id: int, payload: InstrumentUpdate, db: Session = Depends(get_db)):
    obj = get_instrument(db, instrument_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Instrument not found")
    data = payload.dict(exclude_unset=True)
    for k, v in data.items():
        setattr(obj, k, v)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj
