import unittest

from core.models import OrderRequest, OrderSide, OrderType, OrderStatusModel
from core.order_manager import OrderManager
from core.broker_interface import BrokerConnection


class DummyBroker(BrokerConnection):
    def __init__(self):
        self.place_order_called = False
        self.confirm_called = False
        self.cancel_stale_called = False
        self.order_status_requests = {}
        self.active_symbols = set()

    def connect(self, retry: bool = True, timeout: float = 10.0) -> bool:
        return True

    def disconnect(self) -> None:
        pass

    def refresh_account_data(self) -> None:
        pass

    def place_order(self, request: OrderRequest) -> int:
        self.place_order_called = True
        return 42

    def place_order_with_confirmation(
        self,
        request: OrderRequest,
        timeout: float = 10.0,
        retry: int = 0,
        fallback_to_market: bool = False,
    ) -> int:
        self.confirm_called = True
        return 42

    def cancel_order(self, order_id: int) -> None:
        pass

    def cancel_stale_orders(self, timeout: float = 10.0) -> None:
        self.cancel_stale_called = True

    def get_order_status(self, order_id: int) -> OrderStatusModel:
        return OrderStatusModel(order_id=order_id, status="Filled")

    def get_positions(self) -> dict:
        return {}

    def get_account_value(self) -> float:
        return 100000.0

    def get_cash(self) -> float:
        return 100000.0

    def get_account_snapshot(self):
        return {}

    def get_available_funds_for_buys(self) -> float:
        return 100000.0

    def has_active_order(self, symbol: str, action: str = None) -> bool:
        return symbol in self.active_symbols

    def has_pending_orders(self) -> bool:
        return False

    def wait_for_pending_orders(self, timeout: float = 10.0) -> bool:
        return True


class TestOrderManager(unittest.TestCase):
    def setUp(self):
        self.broker = DummyBroker()
        self.order_manager = OrderManager(self.broker)

    def test_submit_order_records_order(self):
        request = OrderRequest(
            symbol="AAPL",
            action=OrderSide.BUY,
            quantity=1,
            order_type=OrderType.LMT,
            limit_price=150.0,
        )
        order_id = self.order_manager.submit_order(request)
        self.assertEqual(order_id, 42)
        self.assertTrue(self.broker.place_order_called)
        self.assertIn(42, self.order_manager.submitted_orders)

    def test_submit_order_with_confirmation(self):
        request = OrderRequest(
            symbol="AAPL",
            action=OrderSide.SELL,
            quantity=1,
            order_type=OrderType.LMT,
            limit_price=145.0,
        )
        order_id = self.order_manager.submit_order_with_confirmation(request)
        self.assertEqual(order_id, 42)
        self.assertTrue(self.broker.confirm_called)

    def test_cancel_stale_orders_forwards_to_broker(self):
        self.order_manager.cancel_stale_orders(timeout=5.0)
        self.assertTrue(self.broker.cancel_stale_called)

    def test_get_order_status_returns_broker_response(self):
        response = self.order_manager.get_order_status(42)
        self.assertIsNotNone(response)
        self.assertEqual(response.order_id, 42)
        self.assertEqual(response.status, "Filled")

    def test_get_active_orders_filters_using_broker(self):
        request = OrderRequest(
            symbol="AAPL",
            action=OrderSide.BUY,
            quantity=1,
            order_type=OrderType.LMT,
            limit_price=150.0,
        )
        self.order_manager.submitted_orders[42] = {"request": request, "submitted_at": None}
        self.broker.active_symbols.add("AAPL")
        active = self.order_manager.get_active_orders()
        self.assertIn(42, active)
        self.assertEqual(active[42]["request"].symbol, "AAPL")


if __name__ == "__main__":
    unittest.main()
