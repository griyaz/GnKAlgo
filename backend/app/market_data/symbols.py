"""Index universe and provider-specific symbol mapping.

All symbol mappings live here (and in ``MARKET_DATA_SYMBOL_OVERRIDES``) instead
of being scattered through provider code. Each internal index id maps to a
provider-specific identifier:

* FYERS API v3 uses string symbols like ``NSE:NIFTY50-INDEX``.
* Dhan uses ``<exchange_segment>:<security_id>`` (segment ``IDX_I`` for indices).
* Upstox Market Data Feed V3 uses instrument keys like ``NSE_INDEX|Nifty 50``.

IMPORTANT: the default provider identifiers below are best-effort and MUST be
verified against your live provider account/SDK. When a mapping cannot be
confirmed, override it (do not guess silently) via the JSON env var
``MARKET_DATA_SYMBOL_OVERRIDES``. See docs/LIVE_MARKET_TICKER.md.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, replace

from app.config import settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class IndexSymbol:
    id: str  # internal id, stable across providers
    display_name: str
    exchange: str
    # FYERS API v3 symbol (verify against your account).
    fyers: str
    # Dhan feed identity: exchange segment + numeric security id (verify).
    dhan_segment: str
    dhan_security_id: str
    # Upstox Market Data Feed V3 instrument key (verify).
    upstox: str

    @property
    def dhan_key(self) -> str:
        return f"{self.dhan_segment}:{self.dhan_security_id}"


# Phase 4 index set. Provider ids are defaults and are overridable.
DEFAULT_INDEX_UNIVERSE: tuple[IndexSymbol, ...] = (
    IndexSymbol("NIFTY50", "NIFTY 50", "NSE", "NSE:NIFTY50-INDEX", "IDX_I", "13", "NSE_INDEX|Nifty 50"),
    IndexSymbol("BANKNIFTY", "NIFTY BANK", "NSE", "NSE:NIFTYBANK-INDEX", "IDX_I", "25", "NSE_INDEX|Nifty Bank"),
    IndexSymbol("MIDCAP100", "NIFTY MIDCAP 100", "NSE", "NSE:NIFTYMIDCAP100-INDEX", "IDX_I", "38", "NSE_INDEX|NIFTY MIDCAP 100"),
    IndexSymbol("SMALLCAP100", "NIFTY SMALLCAP 100", "NSE", "NSE:NIFTYSMLCAP100-INDEX", "IDX_I", "39", "NSE_INDEX|NIFTY SMLCAP 100"),
    IndexSymbol("NIFTYIT", "NIFTY IT", "NSE", "NSE:NIFTYIT-INDEX", "IDX_I", "29", "NSE_INDEX|Nifty IT"),
    IndexSymbol("NIFTYAUTO", "NIFTY AUTO", "NSE", "NSE:NIFTYAUTO-INDEX", "IDX_I", "34", "NSE_INDEX|Nifty Auto"),
    IndexSymbol("NIFTYFMCG", "NIFTY FMCG", "NSE", "NSE:NIFTYFMCG-INDEX", "IDX_I", "31", "NSE_INDEX|Nifty FMCG"),
    IndexSymbol("INDIAVIX", "INDIA VIX", "NSE", "NSE:INDIAVIX-INDEX", "IDX_I", "21", "NSE_INDEX|India VIX"),
)

# Overridable provider field names.
_OVERRIDE_FIELDS = ("fyers", "dhan_segment", "dhan_security_id", "upstox", "display_name", "exchange")


def _apply_overrides(universe: tuple[IndexSymbol, ...]) -> tuple[IndexSymbol, ...]:
    raw = (settings.market_data_symbol_overrides or "").strip()
    if not raw:
        return universe
    try:
        overrides = json.loads(raw)
    except (json.JSONDecodeError, TypeError) as exc:
        logger.warning("market_data.symbols.override_parse_failed error=%s", exc)
        return universe
    if not isinstance(overrides, dict):
        return universe

    result: list[IndexSymbol] = []
    for sym in universe:
        patch = overrides.get(sym.id)
        if not isinstance(patch, dict):
            result.append(sym)
            continue
        changes: dict[str, str] = {}
        # Allow a compact "dhan": "IDX_I:13" form as well as split fields.
        if isinstance(patch.get("dhan"), str) and ":" in patch["dhan"]:
            seg, _, sid = patch["dhan"].partition(":")
            changes["dhan_segment"] = seg
            changes["dhan_security_id"] = sid
        for fieldname in _OVERRIDE_FIELDS:
            if isinstance(patch.get(fieldname), str) and patch[fieldname]:
                changes[fieldname] = patch[fieldname]
        result.append(replace(sym, **changes) if changes else sym)
    return tuple(result)


def get_index_universe() -> tuple[IndexSymbol, ...]:
    """Active index universe with env overrides applied."""
    return _apply_overrides(DEFAULT_INDEX_UNIVERSE)


def fyers_symbols() -> list[str]:
    return [s.fyers for s in get_index_universe()]


def dhan_instruments() -> list[tuple[str, str]]:
    return [(s.dhan_segment, s.dhan_security_id) for s in get_index_universe()]


def upstox_instrument_keys() -> list[str]:
    return [s.upstox for s in get_index_universe()]


def by_fyers_symbol(symbol: str) -> IndexSymbol | None:
    for s in get_index_universe():
        if s.fyers == symbol:
            return s
    return None


def by_dhan_key(exchange_segment: str, security_id: str) -> IndexSymbol | None:
    key = f"{exchange_segment}:{security_id}"
    for s in get_index_universe():
        if s.dhan_key == key:
            return s
    return None


def by_upstox_key(instrument_key: str) -> IndexSymbol | None:
    for s in get_index_universe():
        if s.upstox == instrument_key:
            return s
    return None


def by_id(index_id: str) -> IndexSymbol | None:
    for s in get_index_universe():
        if s.id == index_id:
            return s
    return None
