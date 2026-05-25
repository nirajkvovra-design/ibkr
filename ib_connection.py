from ibapi.contract import Contract
from ibapi.order import Order

from core.ib_broker import IBBrokerConnection as _IBBrokerConnection
from core.models import OrderRequest, OrderSide, OrderType


class InteractiveBrokersConnection(_IBBrokerConnection):
    """Compatibility wrapper exposing legacy IBKR connection behavior."""

    def _build_order_request(self, symbol_or_request, action=None, quantity=None, order_type="LMT", limit_price=None, metadata=None):
        if isinstance(symbol_or_request, OrderRequest):
            return symbol_or_request

        return OrderRequest(
            symbol=symbol_or_request,
            action=OrderSide(action) if not isinstance(action, OrderSide) else action,
            quantity=float(quantity) if isinstance(quantity, (int, float)) else quantity,
            order_type=OrderType(order_type) if not isinstance(order_type, OrderType) else order_type,
            limit_price=limit_price,
            metadata=metadata or {},
        )

    def place_order(self, symbol=None, action=None, quantity=None, order_type="LMT", limit_price=None, metadata=None, **kwargs):
        request = self._build_order_request(symbol, action, quantity, order_type, limit_price, metadata)
        return super().place_order(request)

    def place_order_with_confirmation(
        self,
        symbol=None,
        action=None,
        quantity=None,
        order_type="LMT",
        limit_price=None,
        metadata=None,
        timeout=None,
        retry=None,
        fallback_to_market=None,
        **kwargs,
    ):
        if isinstance(symbol, OrderRequest):
            request = symbol
        else:
            request = self._build_order_request(symbol, action, quantity, order_type, limit_price, metadata)

        return super().place_order_with_confirmation(
            request,
            timeout=timeout,
            retry=retry,
            fallback_to_market=fallback_to_market,
        )

__all__ = ["InteractiveBrokersConnection", "Order", "Contract"]
