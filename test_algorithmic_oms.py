#!/usr/bin/env python
"""
Unit tests for the Advanced Order Management System (OMS) algorithmic slicing
(TWAP/VWAP) and multi-leg Combo Bag contract generation.
"""

import unittest
from unittest.mock import MagicMock, patch
import asyncio

from core.models import OrderRequest, OrderSide, OrderType, ComboLegModel
from core.order_manager import OrderManager
from core.broker_interface import BrokerConnection
from core.ib_broker import IBBrokerConnection


class MockBroker(BrokerConnection):
    def __init__(self):
        self.submitted_requests = []
        self.order_id_counter = 1000

    def connect(self, retry: bool = True, timeout: float = 10.0) -> bool:
        return True

    def disconnect(self) -> None:
        pass

    def refresh_account_data(self) -> None:
        pass

    def place_order(self, request: OrderRequest) -> int:
        self.order_id_counter += 1
        self.submitted_requests.append(request)
        return self.order_id_counter

    def place_order_with_confirmation(
        self,
        request: OrderRequest,
        timeout: float = 10.0,
        retry: int = 0,
        fallback_to_market: bool = False,
    ) -> int:
        self.order_id_counter += 1
        self.submitted_requests.append(request)
        return self.order_id_counter

    def cancel_order(self, order_id: int) -> None:
        pass

    def cancel_stale_orders(self, timeout: float = 10.0) -> None:
        pass

    def get_order_status(self, order_id: int):
        from core.models import OrderStatusModel
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
        return False

    def has_pending_orders(self) -> bool:
        return False

    def wait_for_pending_orders(self, timeout: float = 10.0) -> bool:
        return True


class TestAlgorithmicOMS(unittest.TestCase):

    def setUp(self):
        self.broker = MockBroker()
        self.order_manager = OrderManager(self.broker)

    def test_twap_execution_slicing(self):
        # 1. Arrange a TWAP order for 100 shares over 3 intervals (interval=0.1s)
        request = OrderRequest(
            symbol="AAPL",
            action=OrderSide.BUY,
            quantity=100.0,
            order_type=OrderType.LMT,
            limit_price=150.0
        )

        # 2. Act
        order_ids = asyncio.run(self.order_manager.execute_twap(request, duration_seconds=0.3, interval_seconds=0.1))

        # 3. Assert
        self.assertEqual(len(order_ids), 3)
        self.assertEqual(len(self.broker.submitted_requests), 3)

        # Confirm equal slicing quantity: 100 / 3 = 33.3333 shares each
        qty_1 = self.broker.submitted_requests[0].quantity
        qty_2 = self.broker.submitted_requests[1].quantity
        qty_3 = self.broker.submitted_requests[2].quantity

        self.assertAlmostEqual(qty_1, 33.3333, places=3)
        self.assertAlmostEqual(qty_2, 33.3333, places=3)
        self.assertAlmostEqual(qty_3, 33.3334, places=3) # Final slice consumes residual
        self.assertAlmostEqual(qty_1 + qty_2 + qty_3, 100.0)

    def test_vwap_execution_slicing(self):
        # 1. Arrange a VWAP order for 100 shares over 3 intervals (interval=0.1s)
        # Should generate U-shaped curve weights:
        # t_coords = [0.0, 0.5, 1.0] -> unnormalized = [0.35, 0.1, 0.35] (sum = 0.8)
        # weights = [43.75%, 12.5%, 43.75%]
        request = OrderRequest(
            symbol="AAPL",
            action=OrderSide.BUY,
            quantity=100.0,
            order_type=OrderType.LMT,
            limit_price=150.0
        )

        # 2. Act
        order_ids = asyncio.run(self.order_manager.execute_vwap(request, duration_seconds=0.3, interval_seconds=0.1))

        # 3. Assert
        self.assertEqual(len(order_ids), 3)
        self.assertEqual(len(self.broker.submitted_requests), 3)

        qty_1 = self.broker.submitted_requests[0].quantity
        qty_2 = self.broker.submitted_requests[1].quantity
        qty_3 = self.broker.submitted_requests[2].quantity

        # Confirm U-shape properties: first & last are equal and greater than middle slice
        self.assertAlmostEqual(qty_1, 43.75, places=2)
        self.assertAlmostEqual(qty_2, 12.50, places=2)
        self.assertAlmostEqual(qty_3, 43.75, places=2)
        self.assertAlmostEqual(qty_1 + qty_2 + qty_3, 100.0)

    def test_combo_bag_contract_generation(self):
        # 1. Arrange: setup a real IBBrokerConnection
        broker_conn = IBBrokerConnection()

        # Build combo leg specifications (e.g. Bull Put spread)
        legs = [
            ComboLegModel(conId=123456, ratio=1, action="BUY"),
            ComboLegModel(conId=789012, ratio=1, action="SELL")
        ]

        request = OrderRequest(
            symbol="USD", # Symbol is ignored when ComboLegs are set
            action=OrderSide.BUY,
            quantity=1,
            order_type=OrderType.LMT,
            limit_price=1.50,
            combo_legs=legs
        )

        # 2. Act
        contract = broker_conn._build_contract("BAG", request=request)

        # 3. Assert
        self.assertIsNotNone(contract)
        self.assertEqual(contract.secType, "BAG")
        self.assertEqual(contract.exchange, "SMART")
        self.assertEqual(len(contract.comboLegs), 2)
        
        self.assertEqual(contract.comboLegs[0].conId, 123456)
        self.assertEqual(contract.comboLegs[0].ratio, 1)
        self.assertEqual(contract.comboLegs[0].action, "BUY")
        
        self.assertEqual(contract.comboLegs[1].conId, 789012)
        self.assertEqual(contract.comboLegs[1].ratio, 1)
        self.assertEqual(contract.comboLegs[1].action, "SELL")


if __name__ == "__main__":
    unittest.main()
