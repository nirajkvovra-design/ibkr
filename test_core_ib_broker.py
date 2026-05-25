import unittest

from core.models import OrderRequest, OrderSide, OrderType
import core.ib_broker as ib_broker


class FakeWrapper:
    def __init__(self):
        self.next_order_id = 1
        self.pending_orders = {}
        self.order_status = {}


class FakeClient:
    def __init__(self):
        self.placed_orders = []

    def placeOrder(self, order_id, contract, order):
        self.placed_orders.append((order_id, contract, order))


class TestIBBrokerConnection(unittest.TestCase):
    def setUp(self):
        self.broker = ib_broker.IBBrokerConnection()
        self.broker.connected = True
        self.broker.wrapper = FakeWrapper()
        self.broker.client = FakeClient()
        # Bypass shadow mode interceptor for legacy tests
        if hasattr(self.broker, "safety_gate"):
            del self.broker.safety_gate
        # Ensure paper trading path is allowed for unit tests.
        self.original_paper = ib_broker.config.PAPER_TRADING
        self.original_live = ib_broker.config.ENABLE_LIVE_TRADING
        ib_broker.config.PAPER_TRADING = True
        ib_broker.config.ENABLE_LIVE_TRADING = False

    def tearDown(self):
        ib_broker.config.PAPER_TRADING = self.original_paper
        ib_broker.config.ENABLE_LIVE_TRADING = self.original_live

    def test_place_order_returns_order_id_and_records_order(self):
        request = OrderRequest(
            symbol="AAPL",
            action=OrderSide.BUY,
            quantity=1,
            order_type=OrderType.LMT,
            limit_price=150.0,
        )
        order_id = self.broker.place_order(request)
        self.assertEqual(order_id, 1)
        self.assertEqual(len(self.broker.client.placed_orders), 1)
        self.assertIn(order_id, self.broker.wrapper.pending_orders)
        self.assertIn(order_id, self.broker.order_history)

    def test_place_order_rejects_invalid_quantity(self):
        request = OrderRequest(
            symbol="AAPL",
            action=OrderSide.BUY,
            quantity=1,
            order_type=OrderType.LMT,
            limit_price=150.0,
        )
        request.quantity = 0
        order_id = self.broker.place_order(request)
        self.assertIsNone(order_id)

    def test_place_order_requires_limit_price_for_limit_orders(self):
        request = OrderRequest(
            symbol="AAPL",
            action=OrderSide.BUY,
            quantity=1,
            order_type=OrderType.LMT,
            limit_price=None,
        )
        order_id = self.broker.place_order(request)
        self.assertIsNone(order_id)

    def test_place_order_with_confirmation_returns_order_id(self):
        request = OrderRequest(
            symbol="AAPL",
            action=OrderSide.BUY,
            quantity=1,
            order_type=OrderType.LMT,
            limit_price=150.0,
        )
        # Simulate filled status when order status is checked
        self.broker.wrapper.order_status[1] = ib_broker.OrderStatusModel(order_id=1, status="Filled")
        order_id = self.broker.place_order_with_confirmation(request, timeout=0.1, retry=0, fallback_to_market=False)
        self.assertEqual(order_id, 1)


if __name__ == "__main__":
    unittest.main()
