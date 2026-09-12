"""DB-backed instrument search and resolution."""

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.data.instrument_master import INSTRUMENTS, _SYMBOL_ALIASES
from app.models.instrument import Instrument

# Extra aliases for search/get (merged with CSV normalization)
SYMBOL_ALIASES: dict[str, str] = {
    **_SYMBOL_ALIASES,
    "NIFTY": "NIFTY50",
    "NIFTY 50": "NIFTY50",
    "BANK NIFTY": "BANKNIFTY",
    "NIFTY BANK": "BANKNIFTY",
}


def _to_dict(inst: Instrument) -> dict:
    return {
        "symbol": inst.symbol,
        "display_name": inst.display_name,
        "exchange": inst.exchange,
        "segment": inst.segment,
        "instrument_type": inst.instrument_type,
        "security_id": inst.security_id,
        "instrument_token": inst.instrument_token,
        "exchange_segment": inst.exchange_segment,
        "isin": inst.isin,
        "expiry": inst.expiry.isoformat() if inst.expiry else None,
        "strike": float(inst.strike) if inst.strike is not None else None,
        "option_type": inst.option_type,
        "underlying_symbol": inst.underlying_symbol,
        "lot_size": inst.lot_size,
        "tick_size": float(inst.tick_size) if inst.tick_size is not None else None,
        "trading_symbol": inst.trading_symbol,
    }


# Dhan's compact master reuses equity tickers for NCDs/warrants (MOTHERSON,
# CHOLAFIN, ELECTCAST). Cash shares are ES; curated seed uses EQUITY/INDEX.
_CASH_INSTRUMENT_TYPES = frozenset({"ES", "EQ", "EQUITY", "INDEX"})
_NON_CASH_INSTRUMENT_TYPES = frozenset({"DEB", "CB", "NCD", "W1"})


def _spot_rank(inst: Instrument) -> tuple[int, int, int, str]:
    """Lower is better. Prefer cash equity/index over debt, warrants, and F&O."""
    itype = (inst.instrument_type or "").upper()
    segment = (inst.segment or "").upper()
    non_cash = 0 if itype not in _NON_CASH_INSTRUMENT_TYPES else 1
    cash_type = 0 if itype in _CASH_INSTRUMENT_TYPES or segment == "INDEX" else 1
    derivatives = 0 if segment not in {"FNO", "FUTURES", "OPTIONS"} else 1
    return (non_cash, cash_type, derivatives, inst.security_id)


class InstrumentService:
    async def count(self, db: AsyncSession) -> int:
        result = await db.scalar(
            select(func.count()).select_from(Instrument).where(Instrument.is_active.is_(True))
        )
        return result or 0

    async def search(
        self,
        db: AsyncSession,
        q: str,
        limit: int = 20,
        exchange: str | None = None,
        segment: str | None = None,
    ) -> list[dict]:
        limit = min(max(limit, 1), 50)
        if not q or not q.strip():
            stmt = select(Instrument).where(Instrument.is_active.is_(True))
            if exchange:
                stmt = stmt.where(Instrument.exchange == exchange.upper())
            if segment:
                stmt = stmt.where(Instrument.segment == segment.upper())
            stmt = stmt.order_by(Instrument.symbol).limit(limit)
            result = await db.execute(stmt)
            return [_to_dict(i) for i in result.scalars()]

        raw = q.strip().upper()
        key = SYMBOL_ALIASES.get(raw, raw)
        pattern = f"%{key}%"

        stmt = select(Instrument).where(
            Instrument.is_active.is_(True),
            or_(
                Instrument.symbol == key,
                Instrument.symbol.startswith(key),
                Instrument.search_text.contains(key),
                Instrument.trading_symbol.ilike(pattern),
            ),
        )
        if exchange:
            stmt = stmt.where(Instrument.exchange == exchange.upper())
        if segment:
            stmt = stmt.where(Instrument.segment == segment.upper())

        stmt = stmt.order_by(
            (Instrument.symbol == key).desc(),
            Instrument.symbol.startswith(key).desc(),
            Instrument.symbol,
        ).limit(limit * 3)

        result = await db.execute(stmt)
        items = result.scalars().all()

        # Rank: exact > prefix > contains, cash equity/index before NCD/warrants
        def rank(inst: Instrument) -> tuple[int, int, int, int, str]:
            sym = inst.symbol
            if sym == key:
                match = 0
            elif sym.startswith(key):
                match = 1
            else:
                match = 2
            return (match, *_spot_rank(inst))

        ranked = sorted(items, key=rank)
        seen: set[str] = set()
        out: list[dict] = []
        for inst in ranked:
            dedupe = f"{inst.symbol}:{inst.exchange}:{inst.security_id}"
            if dedupe in seen:
                continue
            seen.add(dedupe)
            out.append(_to_dict(inst))
            if len(out) >= limit:
                break
        return out

    async def get(self, db: AsyncSession, symbol: str, exchange: str | None = None) -> dict | None:
        sym = symbol.strip().upper()
        sym = SYMBOL_ALIASES.get(sym, sym)
        stmt = select(Instrument).where(Instrument.is_active.is_(True), Instrument.symbol == sym)
        if exchange:
            stmt = stmt.where(Instrument.exchange == exchange.upper())
        stmt = stmt.order_by(Instrument.exchange)
        result = await db.execute(stmt)
        rows = list(result.scalars().all())
        if not rows:
            return None
        inst = min(rows, key=_spot_rank)
        return _to_dict(inst)

    async def get_by_security_id(
        self,
        db: AsyncSession,
        exchange_segment: str,
        security_id: str,
    ) -> dict | None:
        result = await db.execute(
            select(Instrument).where(
                Instrument.exchange_segment == exchange_segment,
                Instrument.security_id == str(security_id),
            )
        )
        inst = result.scalar_one_or_none()
        return _to_dict(inst) if inst else None

    async def resolve(self, db: AsyncSession, symbol: str, exchange: str = "NSE") -> dict | None:
        inst = await self.get(db, symbol, exchange)
        if inst:
            return inst
        return await self.get(db, symbol)

    def curated_fallback(self, symbol: str) -> dict | None:
        sym = symbol.strip().upper()
        sym = SYMBOL_ALIASES.get(sym, sym)
        for item in INSTRUMENTS:
            if item["symbol"] == sym:
                from app.services.instrument_segments import dhan_exchange_segment

                seg = dhan_exchange_segment(item["exchange"], item["segment"])
                return {
                    **item,
                    "exchange_segment": seg,
                    "instrument_type": item["segment"],
                }
        return None


instrument_service = InstrumentService()
