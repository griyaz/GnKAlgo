import httpx

from app.brokers.base import BrokerAdapter, OrderRequest, OrderResponse
from app.config import settings


class GrowwAdapter(BrokerAdapter):
    """Groww Trading API adapter. Requires active API subscription."""

    def __init__(self, access_token: str):
        self.access_token = access_token
        self.base_url = settings.groww_api_base_url

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def _request(self, method: str, path: str, **kwargs) -> dict:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.request(
                method,
                f"{self.base_url}{path}",
                headers=self._headers(),
                **kwargs,
            )
            if response.status_code >= 400:
                raise RuntimeError(f"Groww API error {response.status_code}: {response.text}")
            return response.json() if response.content else {}

    async def authenticate(self, credentials: dict) -> bool:
        token = credentials.get("access_token") or credentials.get("api_key")
        if token:
            self.access_token = token
        await self.get_funds()
        return True

    async def get_funds(self) -> dict:
        return await self._request("GET", "/v1/margin/user")

    async def get_holdings(self) -> list[dict]:
        data = await self._request("GET", "/v1/holdings/user")
        return data.get("holdings", data if isinstance(data, list) else [])

    async def get_positions(self) -> list[dict]:
        data = await self._request("GET", "/v1/positions/user")
        return data.get("positions", data if isinstance(data, list) else [])

    async def get_orders(self) -> list[dict]:
        data = await self._request("GET", "/v1/orders")
        return data.get("orders", data if isinstance(data, list) else [])

    async def place_order(self, order: OrderRequest) -> OrderResponse:
        payload = {
            "trading_symbol": order.symbol,
            "exchange": order.exchange,
            "transaction_type": order.side,
            "order_type": order.order_type,
            "quantity": order.quantity,
            "price": order.price,
            "trigger_price": order.trigger_price,
            "product": order.product_type,
            "validity": "DAY",
            "order_reference_id": order.correlation_id,
        }
        data = await self._request("POST", "/v1/order/create", json=payload)
        return OrderResponse(
            order_id=str(data.get("groww_order_id", "")),
            status=data.get("order_status", "PENDING"),
            broker_order_id=str(data.get("groww_order_id", "")),
        )

    async def modify_order(self, order_id: str, changes: dict) -> OrderResponse:
        data = await self._request("PUT", f"/v1/order/{order_id}/modify", json=changes)
        return OrderResponse(order_id=order_id, status=data.get("order_status", "MODIFIED"))

    async def cancel_order(self, order_id: str) -> OrderResponse:
        await self._request("DELETE", f"/v1/order/{order_id}/cancel")
        return OrderResponse(order_id=order_id, status="CANCELLED")

    async def get_market_quote(self, symbols: list[str]) -> dict:
        return await self._request("POST", "/v1/live-data/quote", json={"symbols": symbols})

    async def health_check(self) -> bool:
        try:
            await self.get_funds()
            return True
        except Exception:
            return False
