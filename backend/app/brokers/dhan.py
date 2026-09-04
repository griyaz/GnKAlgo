import httpx
from datetime import datetime, timedelta

from app.brokers.base import BrokerAdapter, OrderRequest, OrderResponse
from app.config import settings


class DhanAdapter(BrokerAdapter):
    """DhanHQ API v2 adapter. Order APIs require static IP whitelisting."""

    def __init__(self, access_token: str, client_id: str | None = None):
        self.access_token = access_token
        self.client_id = client_id
        self.base_url = settings.dhan_api_base_url

    def _headers(self) -> dict[str, str]:
        headers = {
            "access-token": self.access_token,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self.client_id:
            headers["client-id"] = self.client_id
        return headers

    async def get_market_ltp(self, segment_map: dict[str, list[str]]) -> dict:
        """segment_map e.g. {\"NSE_EQ\": [\"2885\"], \"IDX_I\": [\"13\"]}"""
        return await self._request("POST", "/marketfeed/ltp", json=segment_map)

    async def get_market_ohlc(self, segment_map: dict[str, list[str]]) -> dict:
        return await self._request("POST", "/marketfeed/ohlc", json=segment_map)

    async def get_market_quote(self, symbols: list[str], exchange_segment: str = "NSE_EQ") -> dict:
        return await self.get_market_ltp({exchange_segment: symbols})

    async def _request(self, method: str, path: str, **kwargs) -> dict:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.request(
                method,
                f"{self.base_url}{path}",
                headers=self._headers(),
                **kwargs,
            )
            if response.status_code >= 400:
                raise RuntimeError(f"Dhan API error {response.status_code}: {response.text}")
            return response.json() if response.content else {}

    async def authenticate(self, credentials: dict) -> bool:
        token = credentials.get("access_token") or credentials.get("api_key")
        if token:
            self.access_token = token
        await self.get_funds()
        return True

    async def get_funds(self) -> dict:
        return await self._request("GET", "/fundlimit")

    async def get_holdings(self) -> list[dict]:
        data = await self._request("GET", "/holdings")
        return data if isinstance(data, list) else data.get("data", [])

    async def get_positions(self) -> list[dict]:
        data = await self._request("GET", "/positions")
        return data if isinstance(data, list) else data.get("data", [])

    async def get_orders(self) -> list[dict]:
        data = await self._request("GET", "/orders")
        return data if isinstance(data, list) else data.get("data", [])

    @staticmethod
    def order_payload(order: OrderRequest) -> dict:
        product = order.product_type.upper()
        # DhanHQ v2 wire values are CNC / INTRADAY / MARGIN / MTF / CO / BO.
        # The official SDK constant is named INTRA but serializes as "INTRADAY".
        if product in ("INTRADAY", "INTRA"):
            product = "INTRADAY"
        elif product in ("CNC", "DELIVERY"):
            product = "CNC"
        return {
            "dhanClientId": None,
            "transactionType": order.side,
            "exchangeSegment": order.exchange_segment or "NSE_EQ",
            "productType": product,
            "orderType": order.order_type,
            "validity": "DAY",
            "securityId": str(order.security_id or ""),
            "quantity": order.quantity,
            "price": order.price or 0,
            "correlationId": order.correlation_id,
        }

    async def place_order(self, order: OrderRequest) -> OrderResponse:
        if not order.security_id:
            raise RuntimeError("Dhan orders require a numeric securityId")
        payload = self.order_payload(order)
        payload["dhanClientId"] = self.client_id
        data = await self._request("POST", "/orders", json=payload)
        return OrderResponse(
            order_id=str(data.get("orderId", "")),
            status=data.get("orderStatus", "PENDING"),
            broker_order_id=str(data.get("orderId", "")),
        )

    async def modify_order(self, order_id: str, changes: dict) -> OrderResponse:
        data = await self._request("PUT", f"/orders/{order_id}", json=changes)
        return OrderResponse(order_id=order_id, status=data.get("orderStatus", "MODIFIED"))

    async def cancel_order(self, order_id: str) -> OrderResponse:
        await self._request("DELETE", f"/orders/{order_id}")
        return OrderResponse(order_id=order_id, status="CANCELLED")

    async def get_market_quote_for_instrument(
        self,
        security_id: str,
        exchange: str,
        segment: str,
    ) -> dict | None:
        from app.services.instrument_segments import dhan_exchange_segment

        seg = dhan_exchange_segment(exchange, segment)
        try:
            ohlc = await self.get_market_ohlc({seg: [str(security_id)]})
            data = ohlc.get("data", {}).get(seg, {}).get(str(security_id))
            if data:
                return data
            ltp = await self.get_market_ltp({seg: [str(security_id)]})
            return ltp.get("data", {}).get(seg, {}).get(str(security_id))
        except Exception:
            return None

    async def get_historical_candles(
        self,
        security_id: str,
        exchange: str,
        segment: str,
        interval: str,
    ) -> list[dict]:
        """Fetch historical OHLC from Dhan charts API."""
        seg_map = {
            "INDEX": "IDX_I",
            "EQUITY": "NSE_EQ",
        }
        exchange_segment = seg_map.get(segment, "NSE_EQ")
        if exchange == "BSE":
            exchange_segment = "BSE_EQ" if segment == "EQUITY" else "IDX_I"

        days = 5 if interval in ("1m", "3m", "5m", "15m", "30m", "1H", "4H") else 365
        end = datetime.now()
        start = end - timedelta(days=days)

        payload = {
            "securityId": str(security_id),
            "exchangeSegment": exchange_segment,
            "instrument": "INDEX" if segment == "INDEX" else "EQUITY",
            "expiryCode": 0,
            "oi": False,
            "fromDate": start.strftime("%Y-%m-%d"),
            "toDate": end.strftime("%Y-%m-%d"),
        }
        data = await self._request("POST", "/charts/historical", json=payload)
        opens = data.get("open", []) or []
        highs = data.get("high", []) or []
        lows = data.get("low", []) or []
        closes = data.get("close", []) or []
        volumes = data.get("volume", []) or []
        times = data.get("timestamp", []) or data.get("start_Time", []) or []

        candles = []
        for i in range(min(len(closes), len(times))):
            ts = times[i]
            if isinstance(ts, str):
                ts = int(datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp())
            elif ts > 1e12:
                ts = int(ts / 1000)
            vol = volumes[i] if i < len(volumes) else None
            candles.append({
                "time": int(ts),
                "open": float(opens[i]) if i < len(opens) else float(closes[i]),
                "high": float(highs[i]) if i < len(highs) else float(closes[i]),
                "low": float(lows[i]) if i < len(lows) else float(closes[i]),
                "close": float(closes[i]),
                "volume": int(vol) if vol is not None else None,
            })
        return candles

    async def health_check(self) -> bool:
        try:
            await self.get_funds()
            return True
        except Exception:
            return False
