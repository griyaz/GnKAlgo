import httpx
from datetime import datetime, timedelta
from urllib.parse import quote

from app.brokers.base import BrokerAdapter, OrderRequest, OrderResponse
from app.config import settings


class UpstoxExecutionAdapter(BrokerAdapter):
    """Upstox API v2 order-execution adapter (REST).

    Separate from the Upstox *market-data* V3 provider. Auth is a Bearer access
    token. Orders reference an ``instrument_token`` (e.g. ``NSE_EQ|INE848E01016``)
    passed via OrderRequest.security_id.
    """

    def __init__(self, access_token: str):
        self.access_token = access_token
        self.base_url = settings.upstox_api_base_url

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def _request(self, method: str, path: str, **kwargs) -> dict:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.request(
                method, f"{self.base_url}{path}", headers=self._headers(), **kwargs
            )
            if response.status_code >= 400:
                raise RuntimeError(f"Upstox API error {response.status_code}: {response.text}")
            return response.json() if response.content else {}

    async def authenticate(self, credentials: dict) -> bool:
        token = credentials.get("access_token") or credentials.get("api_key")
        if token:
            self.access_token = token
        await self.get_funds()
        return True

    async def get_funds(self) -> dict:
        data = await self._request("GET", "/user/get-funds-and-margin")
        return data.get("data", data)

    async def get_holdings(self) -> list[dict]:
        data = await self._request("GET", "/portfolio/long-term-holdings")
        return data.get("data", []) if isinstance(data, dict) else data

    async def get_positions(self) -> list[dict]:
        data = await self._request("GET", "/portfolio/short-term-positions")
        return data.get("data", []) if isinstance(data, dict) else data

    async def get_orders(self) -> list[dict]:
        data = await self._request("GET", "/order/retrieve-all")
        return data.get("data", []) if isinstance(data, dict) else data

    @staticmethod
    def order_payload(order: OrderRequest) -> dict:
        product = order.product_type.upper()
        if product in ("INTRADAY", "INTRA"):
            product = "I"
        elif product in ("CNC", "DELIVERY", "D"):
            product = "D"
        return {
            "quantity": order.quantity,
            "product": product,
            "validity": "DAY",
            "price": order.price or 0,
            "instrument_token": order.security_id or order.symbol,
            "order_type": order.order_type.upper(),
            "transaction_type": order.side.upper(),
            "disclosed_quantity": 0,
            "trigger_price": 0,
            "is_amo": False,
        }

    async def place_order(self, order: OrderRequest) -> OrderResponse:
        data = await self._request("POST", "/order/place", json=self.order_payload(order))
        payload = data.get("data", data) if isinstance(data, dict) else {}
        order_id = str(payload.get("order_id", ""))
        return OrderResponse(
            order_id=order_id,
            status=data.get("status", "PENDING").upper() if isinstance(data, dict) else "PENDING",
            broker_order_id=order_id,
        )

    async def modify_order(self, order_id: str, changes: dict) -> OrderResponse:
        payload = {"order_id": order_id, **changes}
        data = await self._request("PUT", "/order/modify", json=payload)
        return OrderResponse(order_id=order_id, status=data.get("status", "MODIFIED").upper())

    async def cancel_order(self, order_id: str) -> OrderResponse:
        await self._request("DELETE", f"/order/cancel?order_id={order_id}")
        return OrderResponse(order_id=order_id, status="CANCELLED")

    async def get_market_quote(self, symbols: list[str]) -> dict:
        joined = ",".join(symbols)
        return await self._request("GET", f"/market-quote/ltp?instrument_key={joined}")

    async def get_historical_candles(
        self,
        security_id: str,
        exchange: str,
        segment: str,
        interval: str,
    ) -> list[dict]:
        """Fetch normalized candles through Upstox's v2 historical endpoint.

        ``Instrument.instrument_token`` is preferred because Upstox expects an
        instrument key (for example ``NSE_EQ|INE...``), while the endpoint
        returns newest-first arrays. No data is fabricated when the provider
        is unavailable; CandleService can then apply its configured fallback.
        """
        unit_map = {
            "1m": ("minutes", "1"),
            "3m": ("minutes", "3"),
            "5m": ("minutes", "5"),
            "15m": ("minutes", "15"),
            "30m": ("minutes", "30"),
            "1H": ("hours", "1"),
            "4H": ("hours", "4"),
            "1D": ("days", "1"),
            "1W": ("weeks", "1"),
        }
        unit, multiplier = unit_map.get(interval, ("minutes", "15"))
        end = datetime.utcnow().date()
        days = 30 if unit in {"minutes", "hours"} else 3650
        start = end - timedelta(days=days)
        instrument_key = security_id if "|" in security_id else f"{exchange}_{segment}|{security_id}"
        path = (
            f"/historical-candle/{quote(instrument_key, safe='')}/{unit}/{multiplier}/"
            f"{end.isoformat()}/{start.isoformat()}"
        )
        data = await self._request("GET", path)
        candles = (data.get("data") or {}).get("candles", []) if isinstance(data, dict) else []
        normalized = []
        for row in reversed(candles):
            if len(row) < 5:
                continue
            timestamp = row[0]
            if isinstance(timestamp, str):
                timestamp = int(datetime.fromisoformat(timestamp.replace("Z", "+00:00")).timestamp())
            normalized.append({
                "time": int(timestamp / 1000) if int(timestamp) > 1_000_000_000_000 else int(timestamp),
                "open": float(row[1]),
                "high": float(row[2]),
                "low": float(row[3]),
                "close": float(row[4]),
                "volume": int(row[5]) if len(row) > 5 and row[5] is not None else None,
            })
        return normalized

    async def health_check(self) -> bool:
        try:
            await self.get_funds()
            return True
        except Exception:
            return False
