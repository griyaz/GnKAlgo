import httpx

from app.brokers.base import BrokerAdapter, OrderRequest, OrderResponse
from app.config import settings

# FYERS API v3 order-type / side / product wire values.
_ORDER_TYPE = {"MARKET": 2, "LIMIT": 1, "SL": 3, "SL-M": 4, "SLM": 4}
_SIDE = {"BUY": 1, "SELL": -1}


class FyersExecutionAdapter(BrokerAdapter):
    """FYERS API v3 order-execution adapter (REST).

    Separate from the FYERS *market-data* provider in app.market_data.providers.
    Credentials: client_id (app id, e.g. ABCD1234-100) + access_token. FYERS
    authenticates with an ``Authorization: {client_id}:{access_token}`` header.
    """

    def __init__(self, access_token: str, client_id: str | None = None):
        self.access_token = access_token
        self.client_id = client_id or ""
        self.base_url = settings.fyers_api_base_url

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"{self.client_id}:{self.access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def _request(self, method: str, path: str, **kwargs) -> dict:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.request(
                method, f"{self.base_url}{path}", headers=self._headers(), **kwargs
            )
            if response.status_code >= 400:
                raise RuntimeError(f"FYERS API error {response.status_code}: {response.text}")
            data = response.json() if response.content else {}
            if isinstance(data, dict) and data.get("s") == "error":
                raise RuntimeError(f"FYERS API error: {data.get('message', data)}")
            return data

    async def authenticate(self, credentials: dict) -> bool:
        token = credentials.get("access_token") or credentials.get("api_key")
        if token:
            self.access_token = token
        if credentials.get("client_id"):
            self.client_id = credentials["client_id"]
        await self.get_funds()
        return True

    async def get_funds(self) -> dict:
        return await self._request("GET", "/funds")

    async def get_holdings(self) -> list[dict]:
        data = await self._request("GET", "/holdings")
        return data.get("holdings", []) if isinstance(data, dict) else data

    async def get_positions(self) -> list[dict]:
        data = await self._request("GET", "/positions")
        return data.get("netPositions", []) if isinstance(data, dict) else data

    async def get_orders(self) -> list[dict]:
        data = await self._request("GET", "/orders")
        return data.get("orderBook", []) if isinstance(data, dict) else data

    @staticmethod
    def order_payload(order: OrderRequest) -> dict:
        product = order.product_type.upper()
        if product in ("INTRADAY", "INTRA"):
            product = "INTRADAY"
        elif product in ("CNC", "DELIVERY"):
            product = "CNC"
        order_type = _ORDER_TYPE.get(order.order_type.upper(), 2)
        return {
            "symbol": order.security_id or order.symbol,
            "qty": order.quantity,
            "type": order_type,
            "side": _SIDE.get(order.side.upper(), 1),
            "productType": product,
            "limitPrice": order.price or 0,
            "stopPrice": 0,
            "validity": "DAY",
            "disclosedQty": 0,
            "offlineOrder": False,
        }

    async def place_order(self, order: OrderRequest) -> OrderResponse:
        data = await self._request("POST", "/orders/sync", json=self.order_payload(order))
        return OrderResponse(
            order_id=str(data.get("id", "")),
            status=data.get("s", "PENDING").upper() if data.get("s") != "ok" else "PENDING",
            broker_order_id=str(data.get("id", "")),
            message=data.get("message"),
        )

    async def modify_order(self, order_id: str, changes: dict) -> OrderResponse:
        payload = {"id": order_id, **changes}
        data = await self._request("PATCH", "/orders/sync", json=payload)
        return OrderResponse(order_id=order_id, status=data.get("s", "MODIFIED").upper())

    async def cancel_order(self, order_id: str) -> OrderResponse:
        await self._request("DELETE", "/orders/sync", json={"id": order_id})
        return OrderResponse(order_id=order_id, status="CANCELLED")

    async def get_market_quote(self, symbols: list[str]) -> dict:
        joined = ",".join(symbols)
        return await self._request("GET", f"/data/quotes?symbols={joined}")

    async def health_check(self) -> bool:
        try:
            await self.get_funds()
            return True
        except Exception:
            return False
